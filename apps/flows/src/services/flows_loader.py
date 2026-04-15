"""
Загрузчик flows (bundles) и nodes в БД flows-сервиса.

Читает ``apps/flows/registry.yaml``, для каждого id из секции ``flows`` подгружает
каталог ``apps/flows/bundles/<bundle_id>/`` с ``flow.json`` и при необходимости
``nodes.json`` (устаревшее имя файла — ``agents.json``). Инлайнит tools через ``tool_repository``.

Конфигурация тулов по пути в репозитории: ``apps/flows/tools/``.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Type

import yaml
from pydantic import BaseModel

from apps.flows.src.db import NodeRepository, FlowRepository, ToolRepository
from core.context import get_context
from core.logging import get_logger
from apps.flows.src.models import NodeConfig, FlowConfig, ToolReference
from apps.flows.src.models.node_config import NodeLLMOverride
from apps.flows.src.models.tool_reference import CallParameter
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.src.tools.json_schema_parameters import (
    call_parameters_to_parameters_schema,
    pydantic_model_to_parameters_schema,
)
from apps.flows.src.eval.inline_tool_sanitize import strip_forbidden_platform_import_lines

logger = get_logger(__name__)


def _call_parameters_from_pydantic_model(model: Type[BaseModel]) -> Dict[str, CallParameter]:
    """Собирает CallParameter из JSON Schema Pydantic-модели (для tool_repository при load_tools_to_db)."""

    schema = model.model_json_schema()
    properties = schema.get("properties") or {}
    required_names = set(schema.get("required") or [])

    def prop_type(info: dict[str, Any]) -> str:
        t = info.get("type")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            if len(non_null) == 1:
                t = non_null[0]
            else:
                return "string"
        if t == "integer":
            return "integer"
        if t == "number":
            return "number"
        if t == "boolean":
            return "boolean"
        if t == "array":
            return "array"
        if t == "object":
            return "object"
        any_of = info.get("anyOf")
        if isinstance(any_of, list):
            for br in any_of:
                if isinstance(br, dict) and br.get("type") not in (None, "null"):
                    return prop_type(br)
        return "string"

    out: Dict[str, CallParameter] = {}
    for name, raw in properties.items():
        if not isinstance(raw, dict):
            continue
        desc = raw.get("description", "")
        if not isinstance(desc, str):
            desc = str(desc)
        out[name] = CallParameter(
            type=prop_type(raw),
            description=desc,
            required=name in required_names,
        )
    return out


class FlowsLoader:
    """Загружает bundles (flows) и связанные nodes из корня каталога bundles в БД."""

    def __init__(
        self,
        bundles_dir: Path,
        flow_repository: FlowRepository,
        node_repository: NodeRepository,
        tool_repository: ToolRepository,
        registry_path: Path | None = None,
    ):
        self.bundles_dir = bundles_dir
        self.flow_repository = flow_repository
        self.node_repository = node_repository
        self.tool_repository = tool_repository
        self.registry_path = registry_path or (bundles_dir / "registry.yaml")
        self._registry: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = {}
        self._loaded_nodes: List[str] = []
        self._tools_cache: Dict[str, ToolReference] = {}  # Кеш tools для инлайнинга
        self._nodes_cache: Dict[str, NodeConfig] = {}  # Кеш nodes для инлайнинга

    async def load_all(self) -> tuple[List[str], List[str]]:
        """
        Загружает flows из ``registry.yaml`` (секция ``flows``) и связанные nodes в БД.

        Returns:
            Кортеж (список загруженных flow_id, список загруженных node_id)
        """
        # Загружаем кеши для инлайнинга
        await self._load_tools_cache()
        await self._load_nodes_cache()

        if not self.registry_path.exists():
            logger.warning(f"Registry не найден: {self.registry_path}")
            return [], []

        with open(self.registry_path, "r", encoding="utf-8") as f:
            self._registry = yaml.safe_load(f) or {}

        self._defaults = self._registry.get("defaults", {})
        registry_entries = self._registry.get("flows", [])
        
        # Если старый формат (список строк), конвертируем в новый
        bundle_ids: list[str] = []
        for entry in registry_entries:
            if isinstance(entry, str):
                bundle_ids.append(entry)
            elif isinstance(entry, dict):
                bundle_ids.append(entry["id"])
        
        logger.info(f"Загрузка {len(bundle_ids)} flow из registry в БД")

        # Фаза 1: все nodes.json в кеш (для кросс-ссылок при инлайне tools)
        for bundle_id in bundle_ids:
            await self._preload_nodes_to_cache(bundle_id)

        # Фаза 2: загрузка flow с инлайнингом
        loaded_flow_ids: list[str] = []
        failed_bundle_ids: list[str] = []
        for bundle_id in bundle_ids:
            try:
                flow_id = await self._load_flow_bundle(bundle_id)
                if flow_id:
                    loaded_flow_ids.append(flow_id)
                else:
                    failed_bundle_ids.append(bundle_id)
            except Exception as e:
                logger.error(f"Ошибка загрузки bundle {bundle_id}: {e}", exc_info=True)
                failed_bundle_ids.append(bundle_id)

        logger.info(f"Загружено {len(loaded_flow_ids)} flow в БД: {loaded_flow_ids}")
        if failed_bundle_ids:
            logger.warning(f"Не удалось загрузить {len(failed_bundle_ids)} bundle: {failed_bundle_ids}")
        logger.info(f"Загружено {len(self._loaded_nodes)} nodes в БД")
        return loaded_flow_ids, self._loaded_nodes

    async def _preload_nodes_to_cache(self, bundle_id: str) -> None:
        """Предзагрузка nodes из каталога bundle в кеш (без сохранения flow в БД)."""
        bundle_dir = self.bundles_dir / bundle_id
        
        nodes_path = bundle_dir / "nodes.json"
        if not nodes_path.exists():
            nodes_path = bundle_dir / "agents.json"
        
        if not nodes_path.exists():
            return
        
        await self._load_nodes(bundle_dir, nodes_path)

    async def _load_tools_cache(self) -> None:
        """Загружает inline tools из БД в кеш. MCP-тулы пропускаются — они проксируются через MCP-сервер."""
        tools = await self.tool_repository.list(limit=10000)
        for tool in tools:
            if tool.tool_id.startswith("mcp:"):
                continue
            if not tool.code:
                raise ValueError(
                    f"Tool '{tool.tool_id}' в БД не имеет code. "
                    f"Все tools должны иметь inline code для изоляции flow."
                )
            self._tools_cache[tool.tool_id] = tool

        logger.info(f"Загружен кеш из {len(self._tools_cache)} inline tools")

    async def _load_nodes_cache(self) -> None:
        """Загружает все nodes из БД в кеш для инлайнинга."""
        nodes = await self.node_repository.list(limit=10000)
        for node in nodes:
            self._nodes_cache[node.node_id] = node
        logger.info(f"Загружен кеш из {len(self._nodes_cache)} nodes")

    async def _load_flow_bundle(self, bundle_id: str) -> str | None:
        """Один каталог bundle -> FlowConfig в БД. Nodes предзагружены в _preload_nodes_to_cache."""
        flow_config = await self.build_flow_bundle_config(bundle_id)
        if flow_config is None:
            return None

        # Сохраняем в БД
        await self.flow_repository.set(flow_config)

        logger.info(f"  {bundle_id}: {flow_config.name}")
        return flow_config.flow_id

    async def build_flow_bundle_config(self, bundle_id: str) -> FlowConfig | None:
        """Собирает FlowConfig из bundle без сохранения в БД."""
        bundle_dir = self.bundles_dir / bundle_id
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            logger.warning(f"flow.json не найден: {bundle_dir}")
            return None

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        nodes = await self._load_nodes_with_prompts(bundle_dir, raw_config)
        nodes = self._apply_defaults(nodes)
        nodes = self._inline_tools_in_nodes(nodes)

        edges = raw_config.get("edges", [])
        skills = await self._load_skills_with_prompts(bundle_dir, raw_config)
        skills = self._inline_tools_in_skills(skills)

        evaluation = raw_config.get("evaluation")
        if evaluation:
            evaluation = {k: v for k, v in evaluation.items() if not k.startswith("_")}

        return FlowConfig(
            flow_id=raw_config.get("flow_id") or raw_config.get("id"),
            name=raw_config.get("name", ""),
            description=raw_config.get("description", ""),
            tags=raw_config.get("tags", []),
            entry=raw_config.get("entry", "main"),
            nodes=nodes,
            edges=edges,
            variables=raw_config.get("variables", {}),
            skills=skills,
            evaluation=evaluation,
            source="file",
        )

    async def _load_nodes(self, bundle_dir: Path, nodes_path: Path) -> None:
        """Загружает ноды из nodes.json в БД."""
        with open(nodes_path, "r", encoding="utf-8") as f:
            nodes_list = json.load(f)

        if not isinstance(nodes_list, list):
            logger.warning(f"nodes.json должен быть массивом: {nodes_path}")
            return

        for raw_node in nodes_list:
            node_id = raw_node.get("id")
            if not node_id:
                logger.warning(f"Нода без id в {nodes_path}")
                continue

            # Инлайним промпт из файла
            self._inline_prompt_from_file(raw_node, bundle_dir)

            # Конвертируем tools в List[ToolReference]
            tools = self._convert_tools(raw_node.get("tools", []))

            # Создаём NodeLLMOverride
            llm_override = None
            if "llm" in raw_node:
                llm_data = {**self._defaults.get("llm", {}), **raw_node["llm"]}
                llm_override = NodeLLMOverride(**llm_data)
            elif self._defaults.get("llm"):
                llm_override = NodeLLMOverride(**self._defaults["llm"])

            node_type = raw_node.get("type")
            if not node_type:
                raise ValueError(f"Node '{node_id}' in {nodes_path} requires 'type' field")

            node_config = NodeConfig(
                node_id=node_id,
                type=node_type,
                name=raw_node.get("name", node_id),
                description=raw_node.get("description"),
                prompt=raw_node.get("prompt", ""),
                tools=tools,
                llm_override=llm_override,
                code=raw_node.get("code"),
                files=raw_node.get("files", []),
                local_variables=raw_node.get("variables", {}),
                source="file",
            )

            await self.node_repository.set(node_config)
            # Добавляем в кеш для инлайнинга в flows
            self._nodes_cache[node_id] = node_config
            self._loaded_nodes.append(node_id)
            logger.info(f"    node: {node_id}")

    def _convert_tools(self, tools_list: List[Any]) -> List[ToolReference]:
        """Конвертирует список tools в List[ToolReference]."""
        result = []
        for tool in tools_list:
            if isinstance(tool, str):
                result.append(ToolReference(tool_id=tool))
            elif isinstance(tool, dict):
                tool_data = dict(tool)
                if "args_schema" in tool_data:
                    args_schema = tool_data.pop("args_schema")
                    tool_data["args_schema"] = {
                        k: CallParameter(
                            type=v.get("type", "string"),
                            description=v.get("description", ""),
                            required=v.get("required", True),
                        )
                        for k, v in args_schema.items()
                    }
                result.append(ToolReference(**tool_data))
        return result

    async def _load_nodes_with_prompts(
        self, bundle_dir: Path, config: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Загружает ноды и встраивает промпты из файлов.
        
        Если нода содержит node_id - мержит с данными из nodes.json (через _nodes_cache).
        """
        nodes = {}

        for node_id, node_config in config.get("nodes", {}).items():
            node = dict(node_config)

            # Если нода ссылается на node_id из nodes.json - мержим с данными из кеша
            ref_node_id = node.get("node_id")
            if ref_node_id:
                node = self._merge_node_with_cache(node, ref_node_id, bundle_dir)

            # Инлайним промпт из .md файла если prompt - это путь к файлу
            node = self._inline_prompt_from_file(node, bundle_dir)
            node = self._inline_output_schema_file(node, bundle_dir)

            # Инлайним function -> code
            self._inline_function_to_code(node, node_id)
            
            # Устанавливаем name по умолчанию если не указан
            if "name" not in node:
                node["name"] = node_id

            nodes[node_id] = node

        return nodes

    def _inline_prompt_from_file(
        self, node: Dict[str, Any], bundle_dir: Path
    ) -> Dict[str, Any]:
        """
        Инлайнит промпт из файла.
        
        Поддерживает два формата:
        1. prompt: "prompts/file.md" - автодетект по расширению .md
        2. prompt_file: "prompts/file.md" - явное указание (legacy)
        
        После обработки prompt содержит текст, prompt_file удаляется.
        """
        # Конвертируем prompt_file в prompt (legacy поддержка)
        if "prompt_file" in node:
            if not node.get("prompt"):
                node["prompt"] = node["prompt_file"]
            del node["prompt_file"]
        
        prompt = node.get("prompt")
        if not prompt or not isinstance(prompt, str):
            return node
        
        if not prompt.endswith(".md"):
            return node
        
        prompt_path = bundle_dir / prompt
        if not prompt_path.exists():
            raise ValueError(f"Prompt file not found: {prompt_path}")
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            node["prompt"] = f.read()
        
        return node

    def _inline_output_schema_file(
        self, node: Dict[str, Any], bundle_dir: Path
    ) -> Dict[str, Any]:
        """
        Подставляет output_schema из JSON рядом с flow (как промпт из .md).
        Поле output_schema_file удаляется после загрузки.
        """
        ref = node.get("output_schema_file")
        if not ref or not isinstance(ref, str):
            return node
        if node.get("output_schema") is not None:
            del node["output_schema_file"]
            return node
        schema_path = bundle_dir / ref
        if not schema_path.exists():
            raise ValueError(f"output_schema file not found: {schema_path}")
        with open(schema_path, "r", encoding="utf-8") as f:
            node["output_schema"] = json.load(f)
        del node["output_schema_file"]
        return node

    def _merge_node_with_cache(
        self, node_config: Dict[str, Any], ref_node_id: str, bundle_dir: Path
    ) -> Dict[str, Any]:
        """
        Мержит ноду из flow.json (inline в bundle) с данными из nodes.json (через _nodes_cache).

        Поля из flow.json имеют приоритет над данными из nodes.json.
        """
        cached_node = self._nodes_cache.get(ref_node_id)
        if not cached_node:
            raise ValueError(f"Node '{ref_node_id}' not found in nodes.json")
        
        # Базовые данные из nodes.json
        merged = {
            "type": cached_node.type,
            "name": cached_node.name,
            "description": cached_node.description,
            "prompt": cached_node.prompt,
            "llm": cached_node.llm_override.model_dump() if cached_node.llm_override else {},
            "code": cached_node.code,
        }
        
        # Tools из cached_node (exclude_none чтобы не было code=None)
        if cached_node.tools:
            merged["tools"] = [
                t.model_dump(exclude_none=True) if hasattr(t, "model_dump") else t
                for t in cached_node.tools
            ]
        
        # Переопределения из flow.json имеют приоритет
        for key, value in node_config.items():
            if value is not None and key != "node_id":
                if key == "tools" and value:
                    merged["tools"] = value
                elif key == "llm" and value:
                    merged["llm"] = {**merged.get("llm", {}), **value}
                else:
                    merged[key] = value
        
        # Инлайним prompt из файла если это путь к .md
        merged = self._inline_prompt_from_file(merged, bundle_dir)
        return self._inline_output_schema_file(merged, bundle_dir)

    def _inline_function_to_code(self, node: Dict[str, Any], node_id: str) -> None:
        """
        Если нода имеет 'function' (путь к функции), загружает исходный код.
        Записывает в 'code' и удаляет 'function'.
        """
        function_path = node.get("function")
        if not function_path or node.get("code"):
            return  # Уже есть code или нет function
        
        try:
            # Импортируем функцию по пути
            module_path, func_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            
            # Получаем исходный код функции
            source = inspect.getsource(func)
            node["code"] = source
            del node["function"]
            
            logger.debug(f"Node '{node_id}': инлайнен код из {function_path}")
        except Exception as e:
            logger.error(f"Node '{node_id}': не удалось загрузить код из {function_path}: {e}")

    async def _load_skills_with_prompts(
        self, bundle_dir: Path, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Загружает skills и встраивает промпты для нод в каждом skill."""
        raw_skills = config.get("skills", {})
        if not raw_skills:
            return {}

        skills = {}
        for skill_id, skill_config in raw_skills.items():
            skill = dict(skill_config)

            # Загружаем промпты и инлайним function для нод в skill
            skill_nodes = skill.get("nodes", {})
            if skill_nodes:
                processed_nodes = {}
                for node_id, node_config in skill_nodes.items():
                    node = dict(node_config)
                    
                    # Если нода ссылается на node_id из nodes.json - мержим с данными из кеша
                    ref_node_id = node.get("node_id")
                    if ref_node_id:
                        node = self._merge_node_with_cache(node, ref_node_id, bundle_dir)
                    
                    # Инлайним промпт из файла
                    node = self._inline_prompt_from_file(node, bundle_dir)
                    node = self._inline_output_schema_file(node, bundle_dir)

                    # Инлайним function -> code
                    self._inline_function_to_code(node, f"{skill_id}.{node_id}")
                    processed_nodes[node_id] = node
                
                skill["nodes"] = processed_nodes

            skills[skill_id] = skill

        return skills

    def _apply_defaults(self, nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Применяет defaults из registry к нодам.
        Не применяет дефолтные llm если нода ссылается на node_id - там llm уже определен в nodes.json.
        """
        default_llm = self._defaults.get("llm", {})

        for node_id, node_config in nodes.items():
            if node_config.get("type") == "llm_node":
                # Не применяем дефолтные llm если нода ссылается на node_id
                # В этом случае llm уже замержен в _merge_node_with_cache
                if node_config.get("node_id"):
                    continue
                node_llm = node_config.get("llm", {})
                node_config["llm"] = {**default_llm, **node_llm}

        return nodes

    def _inline_tools_in_nodes(self, nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Рекурсивно инлайнит tools в nodes агента.
        
        Для каждой ноды:
        1. Заменяет tool_id на полные конфиги с кодом
        2. Валидирует уникальность reason/exit tools по react_role
        3. Для нод типа tool с tool_id инлайнит код из tools_cache
        """
        for node_id, node_config in nodes.items():
            node_type = node_config.get("type")
            
            # Для нод типа code с tool_id - инлайним код
            if node_type == "code":
                tool_id = node_config.get("tool_id")
                if tool_id and not node_config.get("code"):
                    tool_ref = self._tools_cache.get(tool_id)
                    if tool_ref and tool_ref.code:
                        node_config["code"] = tool_ref.code
                        if tool_ref.description and not node_config.get("description"):
                            node_config["description"] = tool_ref.description
                        if tool_ref.args_schema and not node_config.get("args_schema"):
                            node_config["args_schema"] = {
                                k: {"type": v.type, "description": v.description}
                                for k, v in tool_ref.args_schema.items()
                            }
                        if tool_ref.parameters_schema and not node_config.get(
                            "parameters_schema"
                        ):
                            node_config["parameters_schema"] = tool_ref.parameters_schema
                        logger.debug(f"Node '{node_id}': инлайнен код tool '{tool_id}'")
                    else:
                        raise ValueError(
                            f"Node '{node_id}' type=tool references tool_id='{tool_id}' "
                            f"which was not found in tools_cache"
                        )
            
            # Инлайним tools внутри llm_node
            inlined_tools = self._inline_tools_recursive(
                node_config.get("tools", []),
                context=f"node '{node_id}'"
            )
            node_config["tools"] = inlined_tools
            
            # Валидируем уникальность reason/exit tools
            if node_type == "llm_node":
                self._validate_llm_node_tools(node_id, inlined_tools)
        
        return nodes

    def _inline_tools_recursive(
        self, tools: List[Any], context: str, depth: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Рекурсивно инлайнит список tools.
        
        Args:
            tools: Список tools (строки или dict)
            context: Контекст для логирования
            depth: Глубина рекурсии (защита от бесконечной рекурсии)
        """
        if depth > 10:
            logger.error(f"{context}: превышена глубина рекурсии инлайнинга")
            return tools

        inlined = []
        for tool in tools:
            inlined_tool = self._inline_single_tool(tool, context, depth)
            if inlined_tool:
                inlined.append(inlined_tool)
        return inlined

    def _inline_single_tool(
        self, tool: Any, context: str, depth: int
    ) -> Dict[str, Any] | None:
        """
        Инлайнит один tool рекурсивно.
        
        Если tool — llm_node (вложенный flow как tool), рекурсивно инлайнит его tools.
        """
        if isinstance(tool, str):
            # Строка - это ID (может быть tool_id или node_id)
            # Сначала ищем в tools_cache
            tool_ref = self._tools_cache.get(tool)
            if tool_ref:
                result = tool_ref.model_dump(exclude_none=True)
                logger.debug(f"{context}: инлайнен tool '{tool}'")
                return result
            
            # Если не нашли как tool - ищем в nodes_cache (node используется как tool)
            node_config = self._get_node_from_cache(tool)
            if node_config:
                return self._inline_node_as_tool(node_config, context, depth)
            
            raise ValueError(f"{context}: ID '{tool}' не найден ни в tools_cache ни в nodes_cache")

        elif isinstance(tool, dict):
            tool_id = tool.get("tool_id")
            exec_kind = tool.get("type")
            
            # Если это llm_node (агент как инструмент) - рекурсивно инлайним его tools
            if exec_kind == "llm_node" or tool.get("prompt"):
                return self._inline_llm_node_tool(tool, context, depth)
            
            # Tool с tool_id без code - ищем в caches
            # Полностью определённые inline tools (не требуют поиска в кэшах)
            inline_node_types = {
                "channel",
                "flow",
                "mcp",
                "external_api",
                "remote_flow",
                "code",
            }
            if exec_kind in inline_node_types:
                logger.debug(f"{context}: inline tool '{tool_id}' с type='{exec_kind}'")
                return tool
            
            if tool_id and not tool.get("code"):
                # Сначала в tools_cache
                tool_ref = self._tools_cache.get(tool_id)
                if tool_ref and tool_ref.code:
                    merged = tool_ref.model_dump(exclude_none=True)
                    # Переопределения из tool - только непустые значения
                    for key, value in tool.items():
                        if value is not None and value != {} and value != []:
                            merged[key] = value
                    logger.debug(f"{context}: инлайнен код для tool '{tool_id}'")
                    return merged
                
                # Если не нашли как tool - ищем в nodes_cache (node как tool)
                node_config = self._get_node_from_cache(tool_id)
                if node_config:
                    return self._inline_node_as_tool(node_config, context, depth)
                
                raise ValueError(f"{context}: tool '{tool_id}' не найден ни в tools_cache ни в nodes_cache")
            
            if not tool.get("code") and not tool.get("prompt"):
                raise ValueError(f"{context}: inline tool требует 'type', 'code' или 'prompt': {tool}")
            
            return tool
        
        raise ValueError(f"{context}: неизвестный формат tool: {type(tool)}")

    def _inline_llm_node_tool(
        self, node_config: Dict[str, Any], context: str, depth: int
    ) -> Dict[str, Any]:
        """
        Инлайнит llm_node который используется как tool.
        Рекурсивно инлайнит все его tools и валидирует уникальность reason/exit.
        """
        result = dict(node_config)
        node_id = result.get("tool_id") or result.get("node_id", "unknown")
        
        # Рекурсивно инлайним tools этой ноды
        if "tools" in result:
            inlined_tools = self._inline_tools_recursive(
                result["tools"],
                context=f"{context} → llm_node '{node_id}'",
                depth=depth + 1
            )
            result["tools"] = inlined_tools
            
            # Валидируем уникальность reason/exit tools
            self._validate_llm_node_tools(node_id, inlined_tools)
        
        logger.debug(f"{context}: инлайнен llm_node '{node_id}' (depth={depth})")
        return result

    def _inline_node_as_tool(
        self, node_config: NodeConfig, context: str, depth: int
    ) -> Dict[str, Any]:
        """
        Конвертирует NodeConfig в inline tool и рекурсивно инлайнит его tools.
        """
        result = {
            "tool_id": node_config.node_id,
            "type": node_config.type,
            "name": node_config.name,
            "description": node_config.description,
            "prompt": node_config.prompt,
        }
        
        if node_config.llm_override:
            result["llm"] = node_config.llm_override.model_dump()
        
        if node_config.code:
            result["code"] = node_config.code
        
        # Собираем tools для инлайнинга
        tools_list = []
        if node_config.tools:
            tools_list = [
                t.model_dump(exclude_none=True) if hasattr(t, "model_dump") else t
                for t in node_config.tools
            ]
        
        # Рекурсивно инлайним tools
        if tools_list:
            inlined_tools = self._inline_tools_recursive(
                tools_list,
                context=f"{context} → node '{node_config.node_id}'",
                depth=depth + 1
            )
            result["tools"] = inlined_tools
            
            # Валидируем уникальность reason/exit tools
            if node_config.type == "llm_node":
                self._validate_llm_node_tools(node_config.node_id, inlined_tools)
        
        logger.debug(f"{context}: инлайнен node '{node_config.node_id}' as tool")
        return result

    def _get_node_from_cache(self, node_id: str) -> NodeConfig | None:
        """Получает node из кеша загруженных nodes."""
        return self._nodes_cache.get(node_id)

    def _validate_llm_node_tools(self, node_id: str, tools: List[Dict[str, Any]]) -> None:
        """
        Валидирует что в llm_node только 1 reasoning и только 1 exit tool.
        
        Args:
            node_id: ID ноды для сообщения об ошибке
            tools: Список инлайненных tools
        
        Raises:
            ValueError: Если найдено более 1 reasoning или exit tool
        """
        reason_tools = [t for t in tools if t.get("react_role") == "reason"]
        exit_tools = [t for t in tools if t.get("react_role") == "exit"]
        
        if len(reason_tools) > 1:
            names = [t.get("tool_id") or t.get("name") for t in reason_tools]
            raise ValueError(
                f"Node '{node_id}': только 1 reasoning tool разрешён, "
                f"найдено {len(reason_tools)}: {names}"
            )
        
        if len(exit_tools) > 1:
            names = [t.get("tool_id") or t.get("name") for t in exit_tools]
            raise ValueError(
                f"Node '{node_id}': только 1 exit tool разрешён, "
                f"найдено {len(exit_tools)}: {names}"
            )

    def _inline_tools_in_skills(self, skills: Dict[str, Any]) -> Dict[str, Any]:
        """
        Рекурсивно инлайнит tools в nodes внутри skills.
        """
        for skill_id, skill_config in skills.items():
            skill_nodes = skill_config.get("nodes", {})
            if skill_nodes:
                skill_config["nodes"] = self._inline_tools_in_nodes(skill_nodes)
        return skills

    async def load_all_for_company(
        self, 
        company_id: str,
        filter_public: bool = True
    ) -> Dict[str, int]:
        """
        Универсальный метод загрузки для любой компании.
        
        Если company_id == "system" или filter_public == False:
            - Загружает ВСЕ агенты и тулы из registry
            
        Иначе (обычная компания с filter_public == True):
            - Загружает ТОЛЬКО PUBLIC агенты со ВСЕМИ зависимостями
            - Загружает ТОЛЬКО PUBLIC тулы
        
        Args:
            company_id: "system" или ID компании
            filter_public: Фильтровать ли по public флагу
            
        Returns:
            {"flows": count, "tools": count, "nodes": count}
        """
        # Загружаем кеши для инлайнинга
        await self._load_tools_cache()
        await self._load_nodes_cache()

        if not self.registry_path.exists():
            logger.warning(f"Registry не найден: {self.registry_path}")
            return {"flows": 0, "tools": 0, "nodes": 0}

        with open(self.registry_path, "r", encoding="utf-8") as f:
            self._registry = yaml.safe_load(f) or {}

        self._defaults = self._registry.get("defaults", {})
        registry_flow_entries = self._registry.get("flows", [])
        
        # Определяем нужно ли фильтровать
        should_filter = filter_public and company_id != "system"
        
        bundles_to_load: list[str] = []
        for entry in registry_flow_entries:
            if isinstance(entry, str):
                if not should_filter:
                    bundles_to_load.append(entry)
            elif isinstance(entry, dict):
                entry_flow_id = entry["id"]
                is_public = entry.get("public", False)
                
                if not should_filter or is_public:
                    bundles_to_load.append(entry_flow_id)
        
        logger.info(
            f"Загрузка {len(bundles_to_load)} flow для company:{company_id} "
            f"(фильтр public: {should_filter})"
        )
        
        for bundle_id in bundles_to_load:
            await self._preload_nodes_to_cache(bundle_id)
        
        loaded_flow_ids: list[str] = []
        failed_bundle_ids: list[str] = []
        for bundle_id in bundles_to_load:
            try:
                flow_id = await self._load_flow_bundle(bundle_id)
                if flow_id:
                    loaded_flow_ids.append(flow_id)
                else:
                    failed_bundle_ids.append(bundle_id)
            except Exception as e:
                logger.error(f"Ошибка загрузки bundle {bundle_id}: {e}", exc_info=True)
                failed_bundle_ids.append(bundle_id)
        
        logger.info(f"Загружено {len(loaded_flow_ids)} flow в company:{company_id}")
        if failed_bundle_ids:
            logger.warning(f"Не удалось загрузить {len(failed_bundle_ids)} bundle: {failed_bundle_ids}")
        
        # Возвращаем статистику
        stats = {
            "flows": len(loaded_flow_ids),
            "tools": 0,  # TODO: если нужна отдельная загрузка tools
            "nodes": len(self._loaded_nodes)
        }
        
        return stats

    async def reload_flow_bundle(self, bundle_id: str) -> str:
        """
        Перезаписывает один flow и связанные nodes из каталога ``bundles/<bundle_id>/`` в БД.

        Использует тот же путь, что и полная загрузка registry: кеш tools/nodes, defaults из registry.
        """
        await self._load_tools_cache()
        await self._load_nodes_cache()

        if not self.registry_path.exists():
            raise ValueError(f"Registry не найден: {self.registry_path}")

        with open(self.registry_path, "r", encoding="utf-8") as f:
            self._registry = yaml.safe_load(f) or {}
        self._defaults = self._registry.get("defaults", {})

        bundle_dir = self.bundles_dir / bundle_id
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            raise ValueError(
                f"Каталог bundle '{bundle_id}' не найден или в нём нет flow.json: {bundle_dir}"
            )

        await self._preload_nodes_to_cache(bundle_id)
        loaded_flow_id = await self._load_flow_bundle(bundle_id)
        if not loaded_flow_id:
            raise ValueError(f"Не удалось загрузить bundle '{bundle_id}' в БД")
        return loaded_flow_id


async def load_flows_to_db(
    flow_repository: FlowRepository,
    node_repository: NodeRepository,
    tool_repository: ToolRepository,
    bundles_dir: Path | None = None,
) -> tuple[List[str], List[str]]:
    """
    Загружает flows и nodes в БД из каталога с bundle-подпапками и registry.yaml.

    Для каждого id из registry читается ``{bundles_dir}/{bundle_id}/flow.json`` (и nodes),
    tools подтягиваются из ``tool_repository`` и инлайнятся в конфиг.

    Args:
        flow_repository: сохранение FlowConfig
        node_repository: сохранение NodeConfig из nodes.json (или устаревшего agents.json)
        tool_repository: чтение tools для инлайнинга
        bundles_dir: корень каталога с подпапками bundle (``{bundle_id}/flow.json``).
            По умолчанию: ``apps/flows/bundles``, реестр: ``apps/flows/registry.yaml``.
            Если ``bundles_dir`` задан явно: реестр ``{bundles_dir}/registry.yaml``.

    Returns:
        (список загруженных flow_id, список загруженных node_id)
    """
    if bundles_dir is None:
        # __file__ = .../apps/flows/src/services/flows_loader.py
        # parent.parent.parent = .../apps/flows/
        base_dir = Path(__file__).parent.parent.parent
        bundles_dir = base_dir / "bundles"
        registry_path = base_dir / "registry.yaml"
    else:
        registry_path = None  # будет использован bundles_dir / "registry.yaml"

    loader = FlowsLoader(bundles_dir, flow_repository, node_repository, tool_repository, registry_path=registry_path)
    return await loader.load_all()


async def load_tools_to_db(
    tool_repository: ToolRepository,
    modules: List[str] | None = None,
) -> List[str]:
    """
    Загружает tools из Python модулей в БД.
    
    Поддерживает:
    - FunctionTool (созданные через @tool декоратор) - извлекается код функции
    - BaseTool классы - извлекается код класса

    Args:
        tool_repository: ToolRepository для сохранения
        modules: Список модулей для загрузки

    Returns:
        Список загруженных tool_id
    """
    if modules is None:
        modules = ["apps.flows.tools", "apps.flows.src.tools.base"]

    loaded = []

    for module_path in modules:
        module = importlib.import_module(module_path)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            # FunctionTool (декоратор @tool) - инстанс, не класс
            if isinstance(attr, FunctionTool):
                tool_instance = attr
                tool_id = tool_instance.name
                
                # Извлекаем код функции БЕЗ декоратора
                full_source = inspect.getsource(tool_instance._func)
                # Убираем декоратор @tool(...) - ищем начало функции
                lines = full_source.split("\n")
                func_start = 0
                for i, line in enumerate(lines):
                    stripped = line.lstrip()
                    if stripped.startswith("async def ") or stripped.startswith("def "):
                        func_start = i
                        break
                source_code = strip_forbidden_platform_import_lines("\n".join(lines[func_start:]))
                
                if tool_instance.args_schema is not None:
                    args_schema_dict = _call_parameters_from_pydantic_model(tool_instance.args_schema)
                    parameters_schema_full = pydantic_model_to_parameters_schema(
                        tool_instance.args_schema
                    )
                else:
                    args_schema_dict = dict(tool_instance._parameters)
                    parameters_schema_full = (
                        call_parameters_to_parameters_schema(args_schema_dict)
                        if args_schema_dict
                        else None
                    )

                # mock_response
                mock_map = None
                if tool_instance._mock_response is not None:
                    if callable(tool_instance._mock_response):
                        mock_map = {"default_response": "callable_mock"}
                    else:
                        mock_map = {"default_response": tool_instance._mock_response}
                
                tool_ref = ToolReference(
                    tool_id=tool_id,
                    title=tool_id,
                    description=tool_instance.description,
                    code=source_code,
                    parameters_schema=parameters_schema_full,
                    args_schema=args_schema_dict,
                    mock_map=mock_map,
                    tags=tool_instance.tags,
                    react_role=tool_instance.react_role,
                )

                await tool_repository.set(tool_ref)
                loaded.append(tool_id)
                logger.info(f"  {tool_id}: FunctionTool")
                continue
            
            # BaseTool класс
            if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                tool_class = attr
                tool_id = tool_class.name

                # Извлекаем исходный код класса
                source_code = inspect.getsource(tool_class)

                args_schema_dict: Dict[str, CallParameter] = {}
                parameters_schema_full = None
                if tool_class.args_schema:
                    args_schema_dict = _call_parameters_from_pydantic_model(tool_class.args_schema)
                    parameters_schema_full = pydantic_model_to_parameters_schema(
                        tool_class.args_schema
                    )

                mock_map = None
                if hasattr(tool_class, "mock_response"):
                    mock_map = {"default_response": tool_class.mock_response}

                tags = getattr(tool_class, "tags", [])
                react_role = getattr(tool_class, "react_role", ReactToolRole.STANDARD)

                tool_ref = ToolReference(
                    tool_id=tool_id,
                    title=tool_class.__name__,
                    description=tool_class.description,
                    code=source_code,
                    parameters_schema=parameters_schema_full,
                    args_schema=args_schema_dict,
                    mock_map=mock_map,
                    tags=tags,
                    react_role=react_role,
                )

                await tool_repository.set(tool_ref)
                loaded.append(tool_id)
                logger.info(f"  {tool_id}: {tool_class.__name__}")

    logger.info(f"Загружено {len(loaded)} tools в БД")
    return loaded


async def get_all_flows(flow_repository: FlowRepository) -> Dict[str, FlowConfig]:
    """
    Все flow из БД.

    Args:
        flow_repository: FlowRepository для чтения

    Returns:
        Словарь {flow_id: FlowConfig}
    """
    rows = await flow_repository.list(limit=10000)
    return {fc.flow_id: fc for fc in rows}
