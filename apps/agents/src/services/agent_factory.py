"""
AgentFactory - фабрика агентов.
"""

import copy
from typing import Any, Dict, List, Optional

from apps.agents.src.agent import Agent
from apps.agents.src.container import get_container
from apps.agents.src.db import AgentRepository
from apps.agents.src.models import AgentConfig, SkillConfig
from apps.agents.src.models.agent_config import Edge, AgentVariableConfig
from apps.agents.src.models.enums import MergeMode
from apps.agents.src.utils.merge import deep_merge
from apps.agents.src.variables import VariablesService
from core.compiler import GraphCompiler
from core.logging import get_logger

logger = get_logger(__name__)


class AgentFactory:
    """Фабрика для создания Agent из БД."""

    def __init__(
        self,
        agent_repository: AgentRepository,
        variables_service: VariablesService,
        graph_compiler: GraphCompiler,
    ):
        self.agent_repository = agent_repository
        self.variables_service = variables_service
        self.compiler = graph_compiler

    async def get_flow(self, agent_id: str, skill_id: str = "default") -> Optional[Agent]:
        """
        Загружает агента из БД и создаёт Agent.
        Применяет skill overrides если указан skill_id.

        Args:
            agent_id: ID агента
            skill_id: ID skill (по умолчанию "default")

        Returns:
            Agent или None
        """
        config = await self.agent_repository.get(agent_id)
        if config is None:
            logger.warning(f"Agent не найден: {agent_id}")
            return None

        return await self._create_flow(config, skill_id)

    async def _create_flow(self, config: AgentConfig, skill_id: str = "default") -> Agent:
        """
        Создает Agent из AgentConfig с применением skill.

        Zero-Guess: валидация графа через GraphCompiler перед созданием агента.

        Args:
            config: AgentConfig из БД
            skill_id: ID skill для применения

        Returns:
            Agent
        """
        effective = self._apply_skill(config, skill_id)

        # Валидация графа через GraphCompiler
        self.compiler.compile(config, skill_config=None, variables=effective["variables"])

        resolved_variables = await self._resolve_variables(effective["variables"])

        edges = [
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in effective["edges"]
        ]

        return await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "description": config.description or "",
                "tags": config.tags,
                "entry": effective["entry"],
                "nodes": effective["nodes"],
                "edges": edges,
            },
            variables=resolved_variables,
        )

    def _apply_skill(self, config: AgentConfig, skill_id: str) -> Dict[str, Any]:
        """
        Применяет skill к конфигу агента.

        Args:
            config: AgentConfig
            skill_id: ID skill

        Returns:
            Dict с effective конфигом (entry, nodes, edges, variables)
        """
        # Извлекаем значения из AgentVariableConfig объектов
        variables_dict = {}
        for key, value in config.variables.items():
            if isinstance(value, AgentVariableConfig):
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
                logger.warning(f"Skill '{skill_id}' не найден в агенте '{config.agent_id}'")
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
            # Извлекаем значения из AgentVariableConfig объектов
            skill_vars = {}
            for key, value in skill.variables.items():
                if isinstance(value, AgentVariableConfig):
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
        Резолвит @var:key ссылки в переменных и извлекает значения из AgentVariableConfig.

        Args:
            variables: Словарь AgentVariableConfig объектов

        Returns:
            Словарь с резолвнутыми значениями (только values, без метаданных)
        """
        resolved = await self.variables_service.resolve(variables)
        
        # Извлекаем только значения из AgentVariableConfig объектов
        result = {}
        for key, value in resolved.items():
            if isinstance(value, dict) and "value" in value:
                result[key] = value["value"]
            else:
                result[key] = value
        
        return result

    async def create_flow(self, config: AgentConfig, skill_id: str = "default") -> Agent:
        """
        Сохраняет AgentConfig в БД и создает Agent.

        Args:
            config: AgentConfig
            skill_id: ID skill (по умолчанию "default")

        Returns:
            Agent
        """
        await self.agent_repository.set(config)
        logger.info(f"Agent сохранён: {config.agent_id}")
        return await self._create_flow(config, skill_id)

    async def delete_flow(self, agent_id: str) -> bool:
        """Удаляет агента из БД"""
        return await self.agent_repository.delete(agent_id)

    async def get_skills(self, agent_id: str) -> Dict[str, SkillConfig]:
        """
        Возвращает skills для агента.
        Если skills не заданы - возвращает default skill.

        Args:
            agent_id: ID агента

        Returns:
            Dict skill_id -> SkillConfig
        """
        config = await self.agent_repository.get(agent_id)
        if config is None:
            return {}

        if config.skills:
            return config.skills

        # Генерируем default skill из конфига агента
        return {
            "default": SkillConfig(
                name=config.name,
                description=config.description or "",
                tags=config.tags,
            )
        }

    async def _get_agent_structure(
        self, tools_list: list, max_depth: int = 3, visited: set = None
    ) -> tuple[list, list]:
        """
        Рекурсивно получает структуру агента: tools и субагенты.

        Args:
            tools_list: Список tools/субагентов
            max_depth: Максимальная глубина рекурсии
            visited: Множество уже посещенных агентов (защита от циклов)

        Returns:
            (tools, subagents) - списки tools и субагентов с их структурой
        """
        if visited is None:
            visited = set()

        if max_depth <= 0:
            return [], []

        container = get_container()

        tools = []
        subagents = []

        for t in tools_list:
            tool_id = (
                t.tool_id
                if hasattr(t, "tool_id")
                else (t.get("tool_id") if isinstance(t, dict) else str(t))
            )

            # Защита от циклов
            if tool_id in visited:
                continue

            # Проверяем - это агент или tool
            subagent_config = await container.agent_repository.get(tool_id)

            if subagent_config:
                # Это субагент - рекурсивно получаем его структуру
                visited.add(tool_id)

                sub_tools_list = subagent_config.tools if subagent_config.tools else []
                sub_tools, sub_subagents = await self._get_agent_structure(
                    sub_tools_list, max_depth=max_depth - 1, visited=visited
                )

                subagents.append(
                    {
                        "id": tool_id,
                        "name": subagent_config.name,
                        "tools": sub_tools[:10],  # Лимит для читаемости
                        "subagents": sub_subagents[:10],  # Лимит вложенных
                    }
                )
            else:
                tools.append(tool_id)

        return tools, subagents

    async def get_flow_schema(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает схему агента для всех skills (для визуализации).

        Args:
            agent_id: ID агента

        Returns:
            Dict с метаданными агента и схемами для каждого skill
        """
        config = await self.agent_repository.get(agent_id)
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

            # Упрощаем nodes для визуализации и добавляем tools/субагенты
            nodes = {}
            for node_id, node_config in effective["nodes"].items():
                node_info = {
                    "type": node_config.get("type", "unknown"),
                    "agent_id": node_config.get("agent_id"),
                    "name": node_id,  # По умолчанию - ID ноды
                    "tools": [],
                    "subagents": [],
                }

                # Получаем tools из конфига ноды или из agent_id
                tools_list = node_config.get("tools", [])

                # Если есть agent_id - загружаем конфиг агента
                if node_config.get("agent_id"):
                    container = get_container()
                    agent_config = await container.agent_repository.get(node_config["agent_id"])
                    if agent_config:
                        node_info["name"] = agent_config.name  # Имя агента
                        if agent_config.tools:
                            tools_list = agent_config.tools

                # Рекурсивно получаем структуру агента
                tools, subagents = await self._get_agent_structure(tools_list, max_depth=3)
                node_info["tools"] = tools
                node_info["subagents"] = subagents

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
            "agent_id": config.agent_id,
            "name": config.name,
            "description": config.description or "",
            "skills": skills_schema,
        }
