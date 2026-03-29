"""
FlowFactory - создание flow из БД.
"""

import copy
import re
from typing import Any, Dict, List, Optional

from apps.flows.src.runtime import Flow
from apps.flows.src.container import get_container
from apps.flows.src.db import FlowRepository
from apps.flows.src.models import FlowConfig, SkillConfig
from apps.flows.src.models.flow_config import Edge, FlowVariableConfig
from apps.flows.src.models.enums import MergeMode
from apps.flows.src.utils.merge import deep_merge
from apps.flows.src.variables import VariablesService
from core.variables import VarResolver
from core.compiler import GraphCompiler
from core.logging import get_logger

logger = get_logger(__name__)


class FlowFactory:
    _VAR_REF_PATTERN = re.compile(r"^@var:([a-zA-Z_][a-zA-Z0-9_.]*)$")
    _VAR_TOKEN_PATTERN = re.compile(r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)")

    """Фабрика для создания Flow из БД."""

    def __init__(
        self,
        flow_repository: FlowRepository,
        variables_service: VariablesService,
        graph_compiler: GraphCompiler,
    ):
        self.flow_repository = flow_repository
        self.variables_service = variables_service
        self.compiler = graph_compiler

    @staticmethod
    def _resource_map_to_plain(ref_map: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """ResourceReference и dict в плоский dict для ResourceResolver."""
        out: Dict[str, Any] = {}
        for key, value in (ref_map or {}).items():
            if hasattr(value, "model_dump"):
                out[key] = value.model_dump()
            elif isinstance(value, dict):
                out[key] = value
            else:
                raise TypeError(
                    f"resource '{key}': ожидается ResourceReference или dict, получен {type(value)}"
                )
        return out

    async def get_flow_config_snapshot(
        self, flow_id: str, config_version: Optional[str] = None
    ) -> Optional[FlowConfig]:
        """Снимок FlowConfig: конкретная версия или последняя в flows."""
        if config_version:
            return await self.flow_repository.get_version(flow_id, config_version)
        return await self.flow_repository.get(flow_id)

    async def get_flow(
        self,
        flow_id: str,
        skill_id: str = "default",
        config_version: Optional[str] = None,
    ) -> Optional[Flow]:
        """
        Загружает flow из БД и создаёт Flow.
        Применяет skill overrides если указан skill_id.

        Args:
            flow_id: ID flow
            skill_id: ID skill (по умолчанию "default")
            config_version: версия из flows_versions; None = последняя запись в flows

        Returns:
            Flow или None
        """
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' версия '{config_version}' не найдена в flows_versions"
                )
            logger.warning(f"Flow не найден: {flow_id}")
            return None

        return await self._create_flow(config, skill_id)

    async def get_resource_maps(
        self,
        flow_id: str,
        skill_id: str,
        config_version: Optional[str] = None,
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Ресурсы уровня flow и skill из БД (без inline state.flow_config).

        Returns:
            (flow_resources, skill_resources или None)
        """
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' версия '{config_version}' не найдена в flows_versions"
                )
            return {}, None

        flow_resources = self._resource_map_to_plain(config.resources)
        skill_resources: Optional[Dict[str, Any]] = None
        if skill_id and skill_id != "default" and config.skills and skill_id in config.skills:
            sk = config.skills[skill_id]
            raw_skill_res = sk.resources or {}
            if raw_skill_res:
                skill_resources = self._resource_map_to_plain(raw_skill_res)

        return flow_resources, skill_resources

    async def get_effective_nodes_map(
        self,
        flow_id: str,
        skill_id: str,
        config_version: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Ноды графа после применения skill (для evaluation и отладки)."""
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' версия '{config_version}' не найдена в flows_versions"
                )
            raise ValueError(f"Flow '{flow_id}' не найден")
        effective = self._apply_skill(config, skill_id)
        return effective["nodes"]

    async def _create_flow(self, config: FlowConfig, skill_id: str = "default") -> Flow:
        """
        Создаёт Flow из FlowConfig с применением skill.

        Zero-Guess: валидация графа через GraphCompiler перед созданием flow.

        Args:
            config: FlowConfig из БД
            skill_id: ID skill для применения

        Returns:
            Flow
        """
        effective = self._apply_skill(config, skill_id)

        # Валидация графа через GraphCompiler
        self.compiler.compile(config, skill_config=None, variables=effective["variables"])

        resolved_variables = await self._resolve_variables(effective["variables"])

        edges = [
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in effective["edges"]
        ]

        # Полный inline конфиг
        config_dict = config.model_dump()
        config_dict["resolved_variables"] = resolved_variables
        config_dict["entry"] = effective["entry"]
        config_dict["nodes"] = effective["nodes"]
        config_dict["edges"] = edges

        return await Flow.from_config(config_dict)

    def _apply_skill(self, config: FlowConfig, skill_id: str) -> Dict[str, Any]:
        """
        Применяет skill к конфигу flow.

        Args:
            config: FlowConfig
            skill_id: ID skill

        Returns:
            Dict с effective конфигом (entry, nodes, edges, variables)
        """
        # Извлекаем значения из FlowVariableConfig объектов
        variables_dict = {}
        for key, value in config.variables.items():
            if isinstance(value, FlowVariableConfig):
                variables_dict[key] = value.value
            else:
                variables_dict[key] = value
        
        result = {
            "entry": config.entry,
            "nodes": copy.deepcopy(config.nodes),
            "edges": list(config.edges),
            "variables": variables_dict,
        }

        # Если нет skills или запрошен default при пустых skills
        if not config.skills:
            return result

        skill = config.skills.get(skill_id)
        if skill is None:
            if skill_id != "default":
                logger.warning(f"Skill '{skill_id}' не найден во flow '{config.flow_id}'")
            return result

        # Entry (всегда replace)
        if skill.entry:
            result["entry"] = skill.entry

        # Nodes
        if skill.nodes is not None:
            if skill.nodes_mode == MergeMode.MERGE:
                self._merge_nodes(result["nodes"], skill.nodes)
            else:
                result["nodes"] = copy.deepcopy(skill.nodes)

        # Edges
        if skill.edges is not None:
            if skill.edges_mode == MergeMode.MERGE:
                self._merge_edges(result["edges"], skill.edges)
            else:
                result["edges"] = list(skill.edges)

        # Variables
        if skill.variables:
            # Извлекаем значения из FlowVariableConfig объектов
            skill_vars = {}
            for key, value in skill.variables.items():
                if isinstance(value, FlowVariableConfig):
                    skill_vars[key] = value.value
                else:
                    skill_vars[key] = value
            
            if skill.variables_mode == MergeMode.MERGE:
                result["variables"].update(skill_vars)
            else:
                result["variables"] = skill_vars

        return result

    def _merge_nodes(
        self, base_nodes: Dict[str, Dict[str, Any]], skill_nodes: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Мержит skill nodes в base nodes.
        Для существующих нод - deep merge конфига.
        Для новых нод - добавление.
        """
        for node_id, skill_node_config in skill_nodes.items():
            if node_id in base_nodes:
                base_nodes[node_id] = deep_merge(base_nodes[node_id], skill_node_config)
            else:
                base_nodes[node_id] = copy.deepcopy(skill_node_config)

    def _merge_edges(self, base_edges: List[Edge], skill_edges: List[Edge]) -> None:
        """
        Мержит skill edges в base edges.
        Edges с той же парой (from_node, to_node) заменяются, новые добавляются.
        """
        skill_edge_pairs = {(e.from_node, e.to_node) for e in skill_edges}

        filtered = [e for e in base_edges if (e.from_node, e.to_node) not in skill_edge_pairs]
        base_edges.clear()
        base_edges.extend(filtered)
        base_edges.extend(skill_edges)

    async def _resolve_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Резолвит @var:key ссылки в переменных и извлекает значения из FlowVariableConfig.

        Для flow-переменных допускается отложенный резолв:
        - если company variable существует, ссылка резолвится сразу;
        - если company variable отсутствует, ссылка сохраняется как @var:...
          и будет разрешена позже через runtime metadata/context.

        Args:
            variables: Словарь FlowVariableConfig объектов

        Returns:
            Словарь с резолвнутыми значениями (только values, без метаданных)
        """
        company_variables = await self.variables_service._get_company_variables_map()
        resolved = self._resolve_flow_variables_with_deferred_refs(
            value=variables,
            company_variables=company_variables,
        )
        
        # Извлекаем только значения из FlowVariableConfig объектов
        result = {}
        for key, value in resolved.items():
            if isinstance(value, dict) and "value" in value:
                result[key] = value["value"]
            else:
                result[key] = value
        
        return result

    def _resolve_flow_variables_with_deferred_refs(
        self,
        value: Any,
        company_variables: Dict[str, Any],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._resolve_flow_variables_with_deferred_refs(item, company_variables)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_flow_variables_with_deferred_refs(item, company_variables)
                for item in value
            ]
        if not isinstance(value, str):
            return value

        full_match = self._VAR_REF_PATTERN.match(value)
        if full_match is not None:
            path = full_match.group(1)
            root_key = path.split(".", 1)[0]
            if root_key not in company_variables:
                return value
            return VarResolver.resolve_ref(value, company_variables)

        if "@var:" not in value:
            return value

        def replace_var(match: re.Match[str]) -> str:
            path = match.group(1)
            root_key = path.split(".", 1)[0]
            if root_key not in company_variables:
                return f"@var:{path}"
            resolved_value = VarResolver.resolve_ref(f"@var:{path}", company_variables)
            return str(resolved_value)

        return self._VAR_TOKEN_PATTERN.sub(replace_var, value)

    async def create_flow(self, config: FlowConfig, skill_id: str = "default") -> Flow:
        """
        Сохраняет FlowConfig в БД и создаёт Flow.

        Args:
            config: FlowConfig
            skill_id: ID skill (по умолчанию "default")

        Returns:
            Flow
        """
        await self.flow_repository.set(config)
        logger.info(f"Flow сохранён: {config.flow_id}")
        return await self._create_flow(config, skill_id)

    async def delete_flow(self, flow_id: str) -> bool:
        """Удаляет flow из БД"""
        return await self.flow_repository.delete(flow_id)

    async def get_skills(self, flow_id: str) -> Dict[str, SkillConfig]:
        """
        Возвращает skills для flow.
        Если skills не заданы - возвращает default skill.

        Args:
            flow_id: ID агента

        Returns:
            Dict skill_id -> SkillConfig
        """
        config = await self.flow_repository.get(flow_id)
        if config is None:
            return {}

        if config.skills:
            return config.skills

        # Генерируем default skill из конфига flow
        return {
            "default": SkillConfig(
                name=config.name,
                description=config.description or "",
                tags=config.tags,
            )
        }

    async def _get_flow_structure(
        self, tools_list: list, max_depth: int = 3, visited: set = None
    ) -> tuple[list, list]:
        """
        Рекурсивно получает структуру flow: tools и вложенные flow (как tools).

        Args:
            tools_list: Список tools / вложенных flow
            max_depth: Максимальная глубина рекурсии
            visited: Множество уже посещённых flow_id (защита от циклов)

        Returns:
            (tools, subflows) — списки tool_id и вложенных flow с их структурой
        """
        if visited is None:
            visited = set()

        if max_depth <= 0:
            return [], []

        container = get_container()

        tools = []
        subflows = []

        for t in tools_list:
            tool_id = (
                t.tool_id
                if hasattr(t, "tool_id")
                else (t.get("tool_id") if isinstance(t, dict) else str(t))
            )

            # Защита от циклов
            if tool_id in visited:
                continue

            nested_flow_config = await container.flow_repository.get(tool_id)

            if nested_flow_config:
                visited.add(tool_id)

                sub_tools_list = nested_flow_config.tools if nested_flow_config.tools else []
                sub_tools, sub_subflows = await self._get_flow_structure(
                    sub_tools_list, max_depth=max_depth - 1, visited=visited
                )

                subflows.append(
                    {
                        "id": tool_id,
                        "name": nested_flow_config.name,
                        "tools": sub_tools[:10],
                        "subflows": sub_subflows[:10],
                    }
                )
            else:
                tools.append(tool_id)

        return tools, subflows

    async def get_flow_schema(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает схему flow для всех skills (для визуализации).

        Args:
            flow_id: ID flow

        Returns:
            Dict с метаданными flow и схемами для каждого skill
        """
        config = await self.flow_repository.get(flow_id)
        if config is None:
            return None

        # Определяем список skills
        if config.skills:
            skill_ids = ["default"] + list(config.skills.keys())
        else:
            skill_ids = ["default"]

        skills_schema = {}
        for skill_id in skill_ids:
            effective = self._apply_skill(config, skill_id)

            # Конвертируем edges в простой формат (могут быть Edge или dict)
            edges = []
            for e in effective["edges"]:
                if isinstance(e, Edge):
                    edge_dict = {"from": e.from_node, "to": e.to_node}
                    if e.condition:
                        edge_dict["condition"] = e.condition
                else:
                    # dict формат
                    edge_dict = {"from": e.get("from"), "to": e.get("to")}
                    if e.get("condition"):
                        edge_dict["condition"] = e["condition"]
                edges.append(edge_dict)

            # Упрощаем nodes для визуализации и добавляем tools / вложенные flow
            nodes = {}
            for node_id, node_config in effective["nodes"].items():
                node_info = {
                    "type": node_config.get("type", "unknown"),
                    "flow_id": node_config.get("flow_id"),
                    "name": node_id,
                    "tools": [],
                    "subflows": [],
                }

                tools_list = node_config.get("tools", [])

                if node_config.get("flow_id"):
                    container = get_container()
                    flow_config = await container.flow_repository.get(node_config["flow_id"])
                    if flow_config:
                        node_info["name"] = flow_config.name
                        if flow_config.tools:
                            tools_list = flow_config.tools

                tools, nested_flows = await self._get_flow_structure(tools_list, max_depth=3)
                node_info["tools"] = tools
                node_info["subflows"] = nested_flows

                nodes[node_id] = node_info

            # Получаем метаданные skill
            skill_config = config.skills.get(skill_id) if config.skills else None
            skill_name = skill_config.name if skill_config else config.name
            skill_desc = skill_config.description if skill_config else (config.description or "")

            skills_schema[skill_id] = {
                "name": skill_name,
                "description": skill_desc,
                "entry": effective["entry"],
                "nodes": nodes,
                "edges": edges,
            }

        return {
            "flow_id": config.flow_id,
            "name": config.name,
            "description": config.description or "",
            "skills": skills_schema,
        }
