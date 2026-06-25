"""
Загрузчик flows (bundles) и nodes в БД flows-сервиса.

Читает ``apps/flows/registry.yaml``, для каждого id из секции ``flows`` подгружает
каталог ``apps/flows/bundles/<bundle_id>/`` с ``flow.json`` и при необходимости
``nodes.json``. Резолвит tool refs через ``tool_repository``.

Конфигурация тулов по пути в репозитории: ``apps/flows/tools/``.
"""

from __future__ import annotations

import importlib
import inspect
import json
import mimetypes
from pathlib import Path
from types import FunctionType
from typing import cast
from urllib.parse import urlparse

import yaml

from apps.flows.src.db import FlowRepository, NodeRepository, ToolRepository
from apps.flows.src.models import CodeMode, FlowConfig, NodeConfig, ToolReference, TriggerConfig
from apps.flows.src.models.bundle_registry import FlowBundleRegistry
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.src.tools.json_schema_parameters import pydantic_model_to_parameters_schema
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.context import get_context
from core.files.create_spec import FileSourceKind
from core.files.default_storage import get_default_storage
from core.files.file_ref import FileRef
from core.files.models import FileRecord
from core.files.reader import FileReader, ReadOptions
from core.files.registry import default_retention_for_source
from core.files.storage import retention_fields_from_spec
from core.llm_context import LLMContextPatch
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

def _function_tool_template_code(tool_instance: FunctionTool) -> str:
    """Маркер platform builtin для материализации FunctionTool в ToolRegistry."""
    tool_name = tool_instance.name
    return (
        f"# platform:tool-capability:{tool_name}\n"
        f"async def {tool_name}(args, state):\n"
        f"    return await tools.call({tool_name!r}, **dict(args))\n"
    )


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
        self.bundles_dir: Path = bundles_dir
        self.flow_repository: FlowRepository = flow_repository
        self.node_repository: NodeRepository = node_repository
        self.tool_repository: ToolRepository = tool_repository
        self.registry_path: Path = registry_path or (bundles_dir / "registry.yaml")
        self._registry: JsonObject = {}
        self._bundle_registry: FlowBundleRegistry = FlowBundleRegistry()
        self._defaults: JsonObject = {}
        self._loaded_nodes: list[str] = []
        self._tools_cache: dict[str, ToolReference] = {}  # Кеш tool refs для сборки flow config
        self._nodes_cache: dict[str, NodeConfig] = {}  # Кеш nodes для инлайнинга
        self._target_company_id: str | None = None

    def load_registry_yaml(self) -> None:
        """Загружает ``registry.yaml`` в ``_registry`` и ``_defaults`` (секция ``defaults``)."""
        if not self.registry_path.exists():
            logger.warning("Registry не найден: %s", self.registry_path)
            self._registry = {}
            self._bundle_registry = FlowBundleRegistry()
            self._defaults = {}
            return
        with open(self.registry_path, "r", encoding="utf-8") as f:
            self._registry = require_json_object(yaml.safe_load(f) or {}, "registry.yaml")
        self._bundle_registry = FlowBundleRegistry.model_validate(self._registry)
        self._defaults = self._bundle_registry.defaults

    async def load_all(self) -> tuple[list[str], list[str]]:
        """
        Загружает flows из ``registry.yaml`` (секция ``flows``) и связанные nodes в БД.

        Возвращает:
            Кортеж (список загруженных flow_id, список загруженных node_id)
        """
        self._target_company_id = "system"
        # Загружаем кеши для инлайнинга
        await self.load_tools_cache()
        await self.load_nodes_cache()

        if not self.registry_path.exists():
            logger.warning(f"Registry не найден: {self.registry_path}")
            return [], []

        self.load_registry_yaml()
        bundle_ids = [entry.id for entry in self._bundle_registry.flows]

        logger.info(f"Загрузка {len(bundle_ids)} flow из registry в БД")

        # Фаза 1: все nodes.json в кеш (для кросс-ссылок при инлайне tools)
        for bundle_id in bundle_ids:
            await self.preload_nodes_to_cache(bundle_id)

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
            logger.warning(
                f"Не удалось загрузить {len(failed_bundle_ids)} bundle: {failed_bundle_ids}"
            )
        logger.info(f"Загружено {len(self._loaded_nodes)} nodes в БД")
        return loaded_flow_ids, self._loaded_nodes

    async def preload_nodes_to_cache(self, bundle_id: str) -> None:
        """Предзагрузка nodes из каталога bundle в кеш (без сохранения flow в БД)."""
        bundle_dir = self.bundles_dir / bundle_id

        nodes_path = bundle_dir / "nodes.json"
        if not nodes_path.exists():
            return

        await self._load_nodes(bundle_dir, nodes_path)

    async def load_tools_cache(self) -> None:
        """Загружает tool refs из БД в кеш. MCP-тулы пропускаются — они проксируются через MCP-сервер."""
        tools = await self.tool_repository.list(limit=10000)
        for tool in tools:
            if tool.tool_id.startswith("mcp:"):
                continue
            if not tool.code:
                raise ValueError(
                    f"Tool '{tool.tool_id}' в БД не имеет code. Пользовательские code tools должны иметь inline code для isolated runner."
                )
            self._tools_cache[tool.tool_id] = tool

        logger.info(f"Загружен кеш из {len(self._tools_cache)} tool refs")

    async def load_nodes_cache(self) -> None:
        """Загружает все nodes из БД в кеш для инлайнинга."""
        nodes = await self.node_repository.list(limit=10000)
        for node in nodes:
            self._nodes_cache[node.node_id] = node
        logger.info(f"Загружен кеш из {len(self._nodes_cache)} nodes")

    async def _load_flow_bundle(self, bundle_id: str) -> str | None:
        """Один каталог bundle -> FlowConfig в БД. Nodes предзагружены в preload_nodes_to_cache."""
        flow_config = await self.build_flow_bundle_config(bundle_id)
        if flow_config is None:
            return None

        # Сохраняем в БД
        _ = await self.flow_repository.set(flow_config)

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
            raw_config = require_json_object(cast(JsonValue, json.load(f)), "flow.json")

        nodes = await self._load_nodes_with_prompts(bundle_dir, raw_config)
        nodes = self._apply_defaults(nodes)
        nodes = self._inline_tools_in_nodes(nodes)

        edges = require_json_array(raw_config.get("edges", []), "flow.edges")
        branches = await self._load_branches_with_prompts(bundle_dir, raw_config)
        branches = self._inline_tools_in_branches(branches)

        triggers: dict[str, TriggerConfig] = {}
        raw_triggers = raw_config.get("triggers")
        if raw_triggers is not None:
            if not isinstance(raw_triggers, dict):
                msg = "flow.json: поле triggers должно быть объектом {trigger_id: ...}"
                raise ValueError(msg)
            for trigger_key, trigger_obj in raw_triggers.items():
                if not trigger_key.strip():
                    msg = "flow.json: ключ в triggers должен быть непустой строкой (trigger_id)"
                    raise ValueError(msg)
                if not isinstance(trigger_obj, dict):
                    msg = f"flow.json: triggers['{trigger_key}'] должен быть объектом TriggerConfig"
                    raise ValueError(msg)
                triggers[trigger_key] = TriggerConfig.model_validate(trigger_obj)

        store_card_image_url = await self._resolve_store_card_image_url(raw_config, bundle_dir)
        raw_flow_id = raw_config.get("flow_id")
        if not isinstance(raw_flow_id, str) or not raw_flow_id.strip():
            raise ValueError("flow.json: поле flow_id обязательно и должно быть непустой строкой")
        raw_name = raw_config.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("flow.json: поле name обязательно и должно быть непустой строкой")
        raw_entry = raw_config.get("entry")
        if not isinstance(raw_entry, str) or not raw_entry.strip():
            raise ValueError("flow.json: поле entry обязательно и должно быть непустой строкой")

        return FlowConfig.model_validate(
            {
                "flow_id": raw_flow_id,
                "name": raw_name,
                "description": raw_config.get("description", ""),
                "tags": raw_config.get("tags", []),
                "entry": raw_entry,
                "nodes": nodes,
                "edges": edges,
                "variables": raw_config.get("variables", {}),
                "branches": branches,
                "triggers": triggers,
                "source": "file",
                "store_card_image_url": store_card_image_url,
            }
        )

    async def _resolve_store_card_image_url(
        self,
        raw_config: JsonObject,
        bundle_dir: Path,
    ) -> str | None:
        """
        Поле bundle-only ``store_card_image``: путь к файлу относительно каталога bundle или URL (http/https).
        Файл загружается в S3 (публичный объект), в FlowConfig попадает ``store_card_image_url`` (download URL).

        Если в JSON задано ``store_card_image_url`` и путь к файлу не задан — используется как есть.
        """
        raw_path = raw_config.get("store_card_image")
        if isinstance(raw_path, str) and raw_path.strip():
            s = raw_path.strip()
            if s.startswith(("http://", "https://")):
                return s
            local_path = Path(s)
            if not local_path.is_absolute():
                local_path = bundle_dir / s
            if not local_path.is_file():
                msg = f"store_card_image: файл не найден: {local_path}"
                raise ValueError(msg)
            data = local_path.read_bytes()
            original_name = local_path.name
            guessed = mimetypes.guess_type(original_name)[0]
            content_type = (
                guessed if isinstance(guessed, str) and guessed else "application/octet-stream"
            )
            company_id = self._resolve_target_company_id()
            record = await self._upload_flow_asset_file(
                data=data,
                original_name=original_name,
                content_type=content_type,
                company_id=company_id,
                is_public=True,
            )
            url = record.download_url
            if not isinstance(url, str) or not url.strip():
                msg = "store_card_image: после загрузки в хранилище отсутствует download_url"
                raise ValueError(msg)
            return url.strip()

        raw_url = raw_config.get("store_card_image_url")
        if isinstance(raw_url, str) and raw_url.strip():
            return raw_url.strip()
        return None

    async def _load_nodes(self, bundle_dir: Path, nodes_path: Path) -> None:
        """Загружает ноды из nodes.json в БД."""
        with open(nodes_path, "r", encoding="utf-8") as f:
            nodes_list = require_json_array(cast(JsonValue, json.load(f)), "nodes.json")

        for raw_node in nodes_list:
            if not isinstance(raw_node, dict):
                logger.warning(f"Нода должна быть объектом в {nodes_path}")
                continue
            node_id = raw_node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                logger.warning(f"Нода без id в {nodes_path}")
                continue

            # Инлайним промпт из файла
            raw_node = self._inline_prompt_from_file(raw_node, bundle_dir)
            raw_node = await self._materialize_node_files(raw_node, node_id)

            # Конвертируем tools в List[ToolReference]
            tools = self._convert_tools(
                require_json_array(raw_node.get("tools", []), f"nodes.{node_id}.tools")
            )

            llm_config = None
            if "llm" in raw_node:
                default_llm = require_json_object(
                    self._defaults.get("llm", {}), "registry.defaults.llm"
                )
                node_llm = require_json_object(raw_node["llm"], f"nodes.{node_id}.llm")
                llm_data = {**default_llm, **node_llm}
                llm_config = NodeLLMConfig.model_validate(llm_data)
            elif self._defaults.get("llm"):
                llm_config = NodeLLMConfig.model_validate(
                    require_json_object(self._defaults["llm"], "registry.defaults.llm")
                )

            llm_context = None
            if "llm_context" in raw_node:
                llm_context = LLMContextPatch.model_validate(raw_node["llm_context"])

            node_type = raw_node.get("type")
            if not isinstance(node_type, str) or not node_type.strip():
                raise ValueError(f"Node '{node_id}' in {nodes_path} requires 'type' field")

            node_config = NodeConfig.model_validate(
                {
                    "node_id": node_id,
                    "type": node_type,
                    "name": raw_node.get("name", node_id),
                    "description": str(raw_node.get("description") or ""),
                    "prompt": raw_node.get("prompt", ""),
                    "tools": tools,
                    "llm": llm_config,
                    "llm_context": llm_context,
                    "llm_context_resource_key": raw_node.get("llm_context_resource_key"),
                    "react": raw_node.get("react"),
                    "code": raw_node.get("code"),
                    "parameters_schema": raw_node.get("parameters_schema"),
                    "files": raw_node.get("files", []),
                    "local_variables": raw_node.get("variables", {}),
                    "source": "file",
                }
            )

            _ = await self.node_repository.set(node_config)
            # Добавляем в кеш для инлайнинга в flows
            self._nodes_cache[node_id] = node_config
            self._loaded_nodes.append(node_id)
            logger.info(f"    node: {node_id}")

    def _resolve_target_company_id(self) -> str:
        context = get_context()
        if context and context.active_company and context.active_company.company_id:
            return context.active_company.company_id
        if self._target_company_id:
            return self._target_company_id
        raise ValueError("Не удалось определить company_id для материализации файлов bundle")

    async def _upload_flow_asset_file(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        company_id: str,
        is_public: bool,
    ) -> FileRecord:
        retention = default_retention_for_source(FileSourceKind.FLOW_ASSET)
        retention_kind, ttl_seconds = retention_fields_from_spec(retention)
        storage = get_default_storage()
        record = await storage.upload_bytes(
            data=data,
            original_name=original_name,
            content_type=content_type,
            uploaded_by=None,
            company_id=company_id,
            is_public=is_public,
            retention_kind=retention_kind,
            ttl_seconds=ttl_seconds,
            metadata={"source_kind": FileSourceKind.FLOW_ASSET.value},
        )
        return record

    def _map_source_to_local_static(self, source: str) -> Path | None:
        parsed = urlparse(source)
        if parsed.scheme not in ("http", "https"):
            return None
        host = (parsed.hostname or "").strip().lower()
        if host not in {"localhost", "127.0.0.1"}:
            return None
        path = parsed.path.strip()
        if not path.startswith("/static/"):
            return None
        local_candidate = self.bundles_dir.parent / path.lstrip("/")
        if local_candidate.is_file():
            return local_candidate
        return None

    def _resolve_file_source(
        self,
        entry: JsonObject,
        node_id: str,
        index: int,
    ) -> str | Path:
        url_value = entry.get("url")
        if isinstance(url_value, str) and url_value.strip():
            url_str = url_value.strip()
            local_from_http = self._map_source_to_local_static(url_str)
            if local_from_http is not None:
                return local_from_http
            return url_str

        raise ValueError(f"Node '{node_id}': files[{index}] должен содержать url")

    async def _materialize_node_files(
        self,
        node: JsonObject,
        node_id: str,
    ) -> JsonObject:
        files = node.get("files")
        if not files:
            return node
        if not isinstance(files, list):
            raise ValueError(f"Node '{node_id}': files должен быть списком")

        company_id = self._resolve_target_company_id()
        reader = FileReader()

        materialized: JsonArray = []
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                raise ValueError(f"Node '{node_id}': files[{index}] должен быть объектом")
            file_entry = entry
            original_name_value = file_entry.get("original_name")
            if not isinstance(original_name_value, str) or not original_name_value.strip():
                raise ValueError(
                    f"Node '{node_id}': files[{index}].original_name должен быть непустой строкой"
                )
            content_type = file_entry.get("content_type")
            if not isinstance(content_type, str) or not content_type.strip():
                raise ValueError(
                    f"Node '{node_id}': files[{index}].content_type должен быть непустой строкой"
                )

            source = self._resolve_file_source(file_entry, node_id, index)
            original_name = original_name_value.strip()
            raw_bytes, _resolved_name = await reader.resolve_source(
                source, original_name, ReadOptions()
            )
            record = await self._upload_flow_asset_file(
                data=raw_bytes,
                original_name=original_name,
                content_type=content_type.strip(),
                company_id=company_id,
                is_public=False,
            )
            item = FileRef.from_record(record)
            materialized.append(item.to_json_object())

        node["files"] = materialized
        return node

    def _convert_tools(self, tools_list: JsonArray) -> list[ToolReference]:
        """Конвертирует список tools в List[ToolReference]."""
        result: list[ToolReference] = []
        for tool in tools_list:
            if isinstance(tool, str):
                result.append(ToolReference(tool_id=tool))
            elif isinstance(tool, dict):
                result.append(ToolReference.model_validate(tool))
        return result

    async def _load_nodes_with_prompts(
        self, bundle_dir: Path, config: JsonObject
    ) -> dict[str, JsonObject]:
        """
        Загружает ноды и встраивает промпты из файлов.

        Если нода содержит node_id - мержит с данными из nodes.json (через _nodes_cache).
        """
        nodes: dict[str, JsonObject] = {}

        raw_nodes = require_json_object(config.get("nodes", {}), "flow.nodes")
        for node_id, node_config in raw_nodes.items():
            if not node_id.strip():
                raise ValueError("flow.nodes keys must be non-empty strings")
            node = require_json_object(node_config, f"flow.nodes.{node_id}")

            # Если нода ссылается на node_id из nodes.json - мержим с данными из кеша
            ref_node_id = node.get("node_id")
            if isinstance(ref_node_id, str) and ref_node_id:
                node = self._merge_node_with_cache(node, ref_node_id, bundle_dir)

            # Инлайним промпт из .md файла если prompt - это путь к файлу
            node = self._inline_prompt_from_file(node, bundle_dir)
            node = self._inline_output_schema_file(node, bundle_dir)

            # Инлайним function -> code
            self._inline_function_to_code(node, node_id)
            node = await self._materialize_node_files(node, node_id)

            # Устанавливаем name по умолчанию если не указан
            if "name" not in node:
                node["name"] = node_id

            nodes[node_id] = node

        return nodes

    def _inline_prompt_from_file(self, node: JsonObject, bundle_dir: Path) -> JsonObject:
        """
        Инлайнит промпт из файла.

        Поддерживает только prompt: "prompts/file.md".
        После обработки prompt содержит текст.
        """
        if "prompt_file" in node:
            raise ValueError("node.prompt_file запрещен; используйте node.prompt")

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

    def _inline_output_schema_file(self, node: JsonObject, bundle_dir: Path) -> JsonObject:
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
            node["output_schema"] = require_json_object(
                cast(JsonValue, json.load(f)),
                f"{schema_path}.output_schema",
            )
        del node["output_schema_file"]
        return node

    def _merge_node_with_cache(
        self, node_config: JsonObject, ref_node_id: str, bundle_dir: Path
    ) -> JsonObject:
        """
        Мержит ноду из flow.json (inline в bundle) с данными из nodes.json (через _nodes_cache).

        Поля из flow.json имеют приоритет над данными из nodes.json.
        """
        cached_node = self._nodes_cache.get(ref_node_id)
        if not cached_node:
            raise ValueError(f"Node '{ref_node_id}' not found in nodes.json")

        # Базовые данные из nodes.json
        merged: JsonObject = {
            "type": cached_node.type,
            "name": cached_node.name,
            "description": cached_node.description,
            "prompt": cached_node.prompt,
            "llm": (
                require_json_object(
                    cached_node.llm.model_dump(mode="json"), f"nodes.{ref_node_id}.llm"
                )
                if cached_node.llm
                else {}
            ),
            "code": cached_node.code,
        }

        # Tools из cached_node (exclude_none, чтобы не было code=None)
        if cached_node.tools:
            merged["tools"] = [
                require_json_object(
                    t.model_dump(mode="json", exclude_none=True), f"nodes.{ref_node_id}.tools[]"
                )
                for t in cached_node.tools
            ]

        # Переопределения из flow.json имеют приоритет
        for key, value in node_config.items():
            if value is not None and key != "node_id":
                if key == "tools" and value:
                    merged["tools"] = value
                elif key == "llm" and isinstance(value, dict):
                    base_llm = merged.get("llm")
                    if not isinstance(base_llm, dict):
                        base_llm = {}
                    merged["llm"] = {**base_llm, **value}
                else:
                    merged[key] = value

        # Инлайним prompt из файла если это путь к .md
        merged = self._inline_prompt_from_file(merged, bundle_dir)
        return self._inline_output_schema_file(merged, bundle_dir)

    def _inline_function_to_code(self, node: JsonObject, node_id: str) -> None:
        """
        Если нода имеет 'function' (путь к функции), загружает исходный код.
        Записывает в 'code' и удаляет 'function'.
        """
        function_path = node.get("function")
        if function_path is None or node.get("code"):
            return  # Уже есть code или нет function
        if not isinstance(function_path, str) or not function_path.strip():
            raise ValueError(f"Node '{node_id}': function must be a non-empty string")

        try:
            # Импортируем функцию по пути
            module_path, func_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            raw_func = module.__dict__.get(func_name)
            if not isinstance(raw_func, FunctionType):
                raise TypeError(f"{function_path} must resolve to a Python function")
            func = raw_func

            # Получаем исходный код функции
            source = inspect.getsource(func)
            node["code"] = source
            del node["function"]

            logger.debug(f"Node '{node_id}': инлайнен код из {function_path}")
        except Exception as e:
            logger.error(f"Node '{node_id}': не удалось загрузить код из {function_path}: {e}")

    async def _load_branches_with_prompts(
        self, bundle_dir: Path, config: JsonObject
    ) -> dict[str, JsonObject]:
        """Загружает ветки (branches) и встраивает промпты для нод в каждой ветке."""
        raw_branches = config.get("branches")
        if raw_branches is None:
            raise ValueError("flow.json: обязательно поле branches (объект веток)")
        if not raw_branches:
            return {}
        if not isinstance(raw_branches, dict):
            raise ValueError("flow.json: поле branches должно быть объектом")

        branches: dict[str, JsonObject] = {}
        for branch_id, branch_payload in raw_branches.items():
            if not branch_id.strip():
                raise ValueError("flow.branches keys must be non-empty strings")
            branch_cfg = require_json_object(branch_payload, f"flow.branches.{branch_id}")

            branch_nodes = require_json_object(
                branch_cfg.get("nodes", {}), f"flow.branches.{branch_id}.nodes"
            )
            if branch_nodes:
                processed_nodes: JsonObject = {}
                for node_id, node_config in branch_nodes.items():
                    if not node_id.strip():
                        raise ValueError(
                            f"flow.branches.{branch_id}.nodes keys must be non-empty strings"
                        )
                    node = require_json_object(
                        node_config, f"flow.branches.{branch_id}.nodes.{node_id}"
                    )

                    ref_node_id = node.get("node_id")
                    if isinstance(ref_node_id, str) and ref_node_id:
                        node = self._merge_node_with_cache(node, ref_node_id, bundle_dir)

                    node = self._inline_prompt_from_file(node, bundle_dir)
                    node = self._inline_output_schema_file(node, bundle_dir)

                    self._inline_function_to_code(node, f"{branch_id}.{node_id}")
                    node = await self._materialize_node_files(node, f"{branch_id}.{node_id}")
                    processed_nodes[node_id] = node

                branch_cfg["nodes"] = processed_nodes

            branches[branch_id] = branch_cfg

        return branches

    def _apply_defaults(self, nodes: dict[str, JsonObject]) -> dict[str, JsonObject]:
        """
        Применяет defaults из registry к нодам.
        Не применяет дефолтные llm если нода ссылается на node_id - там llm уже определен в nodes.json.
        """
        default_llm = require_json_object(self._defaults.get("llm", {}), "registry.defaults.llm")

        for node_id, node_config in nodes.items():
            if node_config.get("type") == "llm_node":
                # Не применяем дефолтные llm если нода ссылается на node_id
                # В этом случае llm уже замержен в _merge_node_with_cache
                if node_config.get("node_id"):
                    continue
                node_llm = require_json_object(node_config.get("llm", {}), f"nodes.{node_id}.llm")
                node_config["llm"] = {**default_llm, **node_llm}

        return nodes

    def _inline_tools_in_nodes(self, nodes: dict[str, JsonObject]) -> dict[str, JsonObject]:
        """
        Рекурсивно резолвит tools в nodes агента.

        Для каждой ноды:
        1. Заменяет tool_id на контракт tool ref; code есть только у пользовательских code tools
        2. Валидирует уникальность reason/exit tools по react_role
        3. Для code-node templates с tool_id подтягивает пользовательский code template
        """
        for node_id, node_config in nodes.items():
            node_type = node_config.get("type")

            # Для нод типа code с tool_id - инлайним код
            if node_type == "code":
                tool_id = node_config.get("tool_id")
                if isinstance(tool_id, str) and tool_id and not node_config.get("code"):
                    tool_ref = self._tools_cache.get(tool_id)
                    if tool_ref and tool_ref.code:
                        node_config["code"] = tool_ref.code
                        if tool_ref.description and not node_config.get("description"):
                            node_config["description"] = tool_ref.description
                        if tool_ref.parameters_schema and not node_config.get("parameters_schema"):
                            node_config["parameters_schema"] = tool_ref.parameters_schema
                        logger.debug(f"Node '{node_id}': инлайнен код tool '{tool_id}'")
                    else:
                        raise ValueError(
                            f"Node '{node_id}' type=tool references tool_id='{tool_id}' which was not found in tools_cache"
                        )

            # Инлайним tools внутри llm_node
            inlined_tools = self._inline_tools_recursive(
                require_json_array(node_config.get("tools", []), f"nodes.{node_id}.tools"),
                context=f"node '{node_id}'",
            )
            node_config["tools"] = inlined_tools

            # Валидируем уникальность reason/exit tools
            if node_type == "llm_node":
                self._validate_llm_node_tools(node_id, inlined_tools)

        return nodes

    def _inline_tools_recursive(self, tools: JsonArray, context: str, depth: int = 0) -> JsonArray:
        """
        Рекурсивно резолвит список tools.

        Аргументы:
            tools: Список tools (строки или dict)
            context: Контекст для логирования
            depth: Глубина рекурсии (защита от бесконечной рекурсии)
        """
        if depth > 10:
            raise ValueError(f"{context}: превышена глубина рекурсии инлайнинга")

        inlined: JsonArray = []
        for tool in tools:
            inlined_tool = self._inline_single_tool(tool, context, depth)
            if inlined_tool:
                inlined.append(inlined_tool)
        return inlined

    def _inline_single_tool(self, tool: JsonValue, context: str, depth: int) -> JsonObject | None:
        """
        Резолвит один tool рекурсивно.

        Если tool — llm_node (вложенный flow как tool), рекурсивно инлайнит его tools.
        """
        if isinstance(tool, str):
            # Строка - это ID (может быть tool_id или node_id)
            # Сначала ищем в tools_cache
            tool_ref = self._tools_cache.get(tool)
            if tool_ref:
                result = require_json_object(
                    tool_ref.model_dump(mode="json", exclude_none=True), f"{context}.tool"
                )
                logger.debug(f"{context}: резолвнут tool ref '{tool}'")
                return result

            # Если не нашли как tool - ищем в nodes_cache (node используется как tool)
            node_config = self._get_node_from_cache(tool)
            if node_config:
                return self._inline_node_as_tool(node_config, context, depth)

            raise ValueError(f"{context}: ID '{tool}' не найден ни в tools_cache ни в nodes_cache")

        elif isinstance(tool, dict):
            tool_payload = tool
            tool_id = tool_payload.get("tool_id")
            exec_kind = tool_payload.get("type")
            code_mode = tool_payload.get("code_mode")

            # Если это llm_node (агент как инструмент) - рекурсивно инлайним его tools
            if exec_kind == "llm_node" or tool_payload.get("prompt"):
                return self._inline_llm_node_tool(tool_payload, context, depth)

            # Tool с tool_id без code — ищем в caches
            # Полностью определённые inline tools (не требуют поиска в кэшах)
            inline_node_types = {
                "channel",
                "flow",
                "mcp",
                "external_api",
                "remote_flow",
                "code",
                "resource",
            }
            if exec_kind in inline_node_types:
                logger.debug(f"{context}: inline tool '{tool_id}' с type='{exec_kind}'")
                return tool_payload
            if code_mode == CodeMode.MCP_TOOL.value:
                logger.debug(f"{context}: inline MCP tool '{tool_id}'")
                return tool_payload

            if isinstance(tool_id, str) and tool_id and not tool_payload.get("code"):
                # Сначала в tools_cache
                tool_ref = self._tools_cache.get(tool_id)
                if tool_ref:
                    merged = require_json_object(
                        tool_ref.model_dump(mode="json", exclude_none=True),
                        f"{context}.tool.{tool_id}",
                    )
                    # Переопределения из tool - только непустые значения
                    for key, value in tool_payload.items():
                        if value is not None and value != {} and value != []:
                            merged[key] = value
                    logger.debug(f"{context}: резолвнут tool ref '{tool_id}'")
                    return merged

                # Если не нашли как tool - ищем в nodes_cache (node как tool)
                node_config = self._get_node_from_cache(tool_id)
                if node_config:
                    return self._inline_node_as_tool(node_config, context, depth)

                raise ValueError(
                    f"{context}: tool '{tool_id}' не найден ни в tools_cache ни в nodes_cache"
                )

            if not tool_payload.get("code") and not tool_payload.get("prompt"):
                raise ValueError(
                    f"{context}: inline tool требует 'type', 'code' или 'prompt': {tool_payload}"
                )

            return tool_payload

        raise ValueError(f"{context}: неизвестный формат tool: {type(tool)}")

    def _inline_llm_node_tool(
        self, node_config: JsonObject, context: str, depth: int
    ) -> JsonObject:
        """
        Инлайнит llm_node который используется как tool.
        Рекурсивно инлайнит все его tools и валидирует уникальность reason/exit.
        """
        result: JsonObject = dict(node_config)
        raw_node_id = result.get("tool_id") or result.get("node_id")
        node_id = raw_node_id if isinstance(raw_node_id, str) and raw_node_id else "unknown"

        # Рекурсивно инлайним tools этой ноды
        if "tools" in result:
            inlined_tools = self._inline_tools_recursive(
                require_json_array(result["tools"], f"{context}.tools"),
                context=f"{context} → llm_node '{node_id}'",
                depth=depth + 1,
            )
            result["tools"] = inlined_tools

            # Валидируем уникальность reason/exit tools
            self._validate_llm_node_tools(node_id, inlined_tools)

        logger.debug(f"{context}: инлайнен llm_node '{node_id}' (depth={depth})")
        return result

    def _inline_node_as_tool(self, node_config: NodeConfig, context: str, depth: int) -> JsonObject:
        """
        Конвертирует NodeConfig в inline tool и рекурсивно инлайнит его tools.
        """
        result: JsonObject = {
            "tool_id": node_config.node_id,
            "type": node_config.type,
            "name": node_config.name,
            "description": node_config.description,
            "prompt": node_config.prompt,
        }

        if node_config.llm:
            result["llm"] = require_json_object(
                node_config.llm.model_dump(mode="json"),
                f"nodes.{node_config.node_id}.llm",
            )

        if node_config.code:
            result["code"] = node_config.code
        if node_config.parameters_schema is None:
            raise ValueError(
                f"Node '{node_config.node_id}' used as tool requires parameters_schema"
            )
        result["parameters_schema"] = require_json_object(
            node_config.parameters_schema,
            f"nodes.{node_config.node_id}.parameters_schema",
        )

        # Собираем tools для инлайнинга
        tools_list: JsonArray = []
        if node_config.tools:
            tools_list = [
                require_json_object(
                    t.model_dump(mode="json", exclude_none=True),
                    f"nodes.{node_config.node_id}.tools[]",
                )
                for t in node_config.tools
            ]

        # Рекурсивно инлайним tools
        if tools_list:
            inlined_tools = self._inline_tools_recursive(
                tools_list, context=f"{context} → node '{node_config.node_id}'", depth=depth + 1
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

    def _validate_llm_node_tools(self, node_id: str, tools: JsonArray) -> None:
        """
        Валидирует что в llm_node только 1 reasoning и только 1 exit tool.

        Аргументы:
            node_id: ID ноды для сообщения об ошибке
            tools: Список инлайненных tools

        Исключения:
            ValueError: Если найдено более 1 reasoning или exit tool
        """
        tool_objects = [require_json_object(t, f"nodes.{node_id}.tools[]") for t in tools]
        reason_tools = [t for t in tool_objects if t.get("react_role") == "reason"]
        exit_tools = [t for t in tool_objects if t.get("react_role") == "exit"]

        if len(reason_tools) > 1:
            names = [t.get("tool_id") or t.get("name") for t in reason_tools]
            raise ValueError(
                f"Node '{node_id}': только 1 reasoning tool разрешён, найдено {len(reason_tools)}: {names}"
            )

        if len(exit_tools) > 1:
            names = [t.get("tool_id") or t.get("name") for t in exit_tools]
            raise ValueError(
                f"Node '{node_id}': только 1 exit tool разрешён, найдено {len(exit_tools)}: {names}"
            )

    def _inline_tools_in_branches(self, branches: dict[str, JsonObject]) -> dict[str, JsonObject]:
        """Рекурсивно инлайнит tools в nodes внутри каждой ветки."""
        for _branch_id, branch_cfg in branches.items():
            branch_nodes = require_json_object(branch_cfg.get("nodes", {}), "branch.nodes")
            if branch_nodes:
                node_map: dict[str, JsonObject] = {
                    node_id: require_json_object(node_payload, f"branch.nodes.{node_id}")
                    for node_id, node_payload in branch_nodes.items()
                }
                inlined_nodes = self._inline_tools_in_nodes(node_map)
                branch_cfg["nodes"] = {
                    node_id: node_payload for node_id, node_payload in inlined_nodes.items()
                }
        return branches

    async def load_all_for_company(
        self, company_id: str, filter_public: bool = True
    ) -> dict[str, int]:
        """
        Универсальный метод загрузки для любой компании.

        Если company_id == "system" или filter_public == False:
            - Загружает ВСЕ агенты и тулы из registry

        Иначе (обычная компания с filter_public == True):
            - Загружает ТОЛЬКО PUBLIC агенты со ВСЕМИ зависимостями
            - Загружает ТОЛЬКО PUBLIC тулы

        Аргументы:
            company_id: "system" или ID компании
            filter_public: Фильтровать ли по public флагу

        Возвращает:
            {"flows": count, "tools": count, "nodes": count}
        """
        self._target_company_id = company_id
        # Загружаем кеши для инлайнинга
        await self.load_tools_cache()
        await self.load_nodes_cache()

        if not self.registry_path.exists():
            logger.warning(f"Registry не найден: {self.registry_path}")
            return {"flows": 0, "tools": 0, "nodes": 0}

        self.load_registry_yaml()

        # Определяем нужно ли фильтровать
        should_filter = filter_public and company_id != "system"

        bundles_to_load: list[str] = []
        for entry in self._bundle_registry.flows:
            if not should_filter or entry.public:
                bundles_to_load.append(entry.id)

        logger.info(
            f"Загрузка {len(bundles_to_load)} flow для company:{company_id} (фильтр public: {should_filter})"
        )

        for bundle_id in bundles_to_load:
            await self.preload_nodes_to_cache(bundle_id)

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
            logger.warning(
                f"Не удалось загрузить {len(failed_bundle_ids)} bundle: {failed_bundle_ids}"
            )

        # Возвращаем статистику
        stats = {
            "flows": len(loaded_flow_ids),
            "tools": 0,  # TODO: если нужна отдельная загрузка tools
            "nodes": len(self._loaded_nodes),
        }

        return stats

    async def reload_flow_bundle(self, bundle_id: str) -> str:
        """
        Перезаписывает один flow и связанные nodes из каталога ``bundles/<bundle_id>/`` в БД.

        Использует тот же путь, что и полная загрузка registry: кеш tools/nodes, defaults из registry.
        """
        context = get_context()
        if not context or not context.active_company or not context.active_company.company_id:
            raise ValueError("reload_flow_bundle требует active_company в контексте")
        self._target_company_id = context.active_company.company_id
        await self.load_tools_cache()
        await self.load_nodes_cache()

        if not self.registry_path.exists():
            raise ValueError(f"Registry не найден: {self.registry_path}")

        self.load_registry_yaml()

        bundle_dir = self.bundles_dir / bundle_id
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            raise ValueError(
                f"Каталог bundle '{bundle_id}' не найден или в нём нет flow.json: {bundle_dir}"
            )

        await self.preload_nodes_to_cache(bundle_id)
        loaded_flow_id = await self._load_flow_bundle(bundle_id)
        if not loaded_flow_id:
            raise ValueError(f"Не удалось загрузить bundle '{bundle_id}' в БД")
        return loaded_flow_id


async def load_flows_to_db(
    flow_repository: FlowRepository,
    node_repository: NodeRepository,
    tool_repository: ToolRepository,
    bundles_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """
    Загружает flows и nodes в БД из каталога с bundle-подпапками и registry.yaml.

    Для каждого id из registry читается ``{bundles_dir}/{bundle_id}/flow.json`` (и nodes),
    tools подтягиваются из ``tool_repository`` и инлайнятся в конфиг.

    Аргументы:
        flow_repository: сохранение FlowConfig
        node_repository: сохранение NodeConfig из nodes.json
        tool_repository: чтение tools для инлайнинга
        bundles_dir: корень каталога с подпапками bundle (``{bundle_id}/flow.json``).
            По умолчанию: ``apps/flows/bundles``, реестр: ``apps/flows/registry.yaml``.
            Если ``bundles_dir`` задан явно: реестр ``{bundles_dir}/registry.yaml``.

    Возвращает:
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

    loader = FlowsLoader(
        bundles_dir, flow_repository, node_repository, tool_repository, registry_path=registry_path
    )
    return await loader.load_all()


async def load_tools_to_db(
    tool_repository: ToolRepository,
    modules: list[str] | None = None,
) -> list[str]:
    """
    Загружает контракты trusted platform tools из Python модулей в БД.

    Поддерживает:
    - FunctionTool (созданные через @tool декоратор) - сохраняет schema/metadata без source-кода

    Аргументы:
        tool_repository: ToolRepository для сохранения
        modules: Список модулей для загрузки

    Возвращает:
        Список загруженных tool_id
    """
    tool_attrs: list[tuple[str, str, FunctionTool]] = []
    if modules is None:
        for module_path, attr_name in BUILTIN_TOOL_SPECS:
            module = importlib.import_module(module_path)
            attr = module.__dict__.get(attr_name)
            if isinstance(attr, FunctionTool):
                tool_attrs.append((module_path, attr_name, attr))
    else:
        for module_path in modules:
            module = importlib.import_module(module_path)
            for attr_name in dir(module):
                attr = module.__dict__.get(attr_name)
                if isinstance(attr, FunctionTool):
                    tool_attrs.append((module_path, attr_name, attr))

    loaded: list[str] = []
    loaded_ids: set[str] = set()

    for _, _, tool_instance in tool_attrs:
        tool_id = tool_instance.name
        if tool_id in loaded_ids:
            continue

        parameters_model = tool_instance.parameters_model
        if parameters_model is None:
            raise ValueError(
                f"Tool '{tool_id}' has no parameters_model — cannot derive JSON Schema"
            )
        parameters_schema_full = pydantic_model_to_parameters_schema(parameters_model)

        tool_ref = ToolReference(
            tool_id=tool_id,
            title=tool_id,
            description=tool_instance.description,
            code=_function_tool_template_code(tool_instance),
            parameters_schema=parameters_schema_full,
            tags=tool_instance.tags,
            react_role=tool_instance.react_role,
        )

        _ = await tool_repository.set(tool_ref)
        loaded.append(tool_id)
        loaded_ids.add(tool_id)
        logger.info(f"  {tool_id}: FunctionTool")

    logger.info(f"Загружено {len(loaded)} tools в БД")
    return loaded


async def get_all_flows(flow_repository: FlowRepository) -> dict[str, FlowConfig]:
    """
    Все flow из БД.

    Аргументы:
        flow_repository: FlowRepository для чтения

    Возвращает:
        Словарь {flow_id: FlowConfig}
    """
    rows = await flow_repository.list(limit=10000)
    return {fc.flow_id: fc for fc in rows}
