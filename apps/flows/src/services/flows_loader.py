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
import mimetypes
from pathlib import Path
from types import FunctionType
from urllib.parse import urlparse

from apps.flows.src.models import (
    CodeMode,
    FlowConfig,
    FlowToolReference,
    NodeConfig,
    ToolReference,
    TriggerConfig,
)
from apps.flows.src.models.bundle_registry import FlowBundleRegistry
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.src.tools.json_schema_parameters import pydantic_model_to_parameters_schema
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.context import get_context
from core.files.file_ref import stored_file_ref
from core.files.models import FileRecord
from core.files.reader import FileReader, ReadOptions
from core.files.service import FilesService
from core.llm_context import LLMContextPatch
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_array,
    parse_json_object,
    parse_yaml_value,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

_INLINE_SELF_CONTAINED_TOOL_TYPES = frozenset(
    {
        "channel",
        "flow",
        "mcp",
        "datasource",
        "external_api",
        "remote_flow",
        "code_agent",
        "code",
        "resource",
    }
)


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
        registry_path: Path | None = None,
        flow_access_service: FlowAccessService | None = None,
        files_service: FilesService | None = None,
    ):
        self.bundles_dir: Path = bundles_dir
        self.flow_access_service: FlowAccessService | None = flow_access_service
        self.files_service: FilesService | None = files_service
        self.registry_path: Path = registry_path or (bundles_dir / "registry.yaml")
        self._registry: JsonObject = {}
        self._bundle_registry: FlowBundleRegistry = FlowBundleRegistry()
        self._defaults: JsonObject = {}
        self._loaded_nodes: list[str] = []
        self._tools_cache: dict[str, ToolReference] = {}  # session memo: tool refs для инлайнинга
        self._nodes_cache: dict[str, NodeConfig] = {}  # session memo: nodes для инлайнинга
        self._preloaded_bundle_ids: set[str] = set()
        self._target_company_id: str | None = None

    async def _sync_loaded_flow(self, flow_config: FlowConfig) -> None:
        if self.flow_access_service is None:
            raise RuntimeError("flow_access_service required for OpenFGA dual-write on flow load")
        company_id = self._resolve_target_company_id()
        await self.flow_access_service.sync_flow_saved(
            flow_config,
            company_id=company_id,
            owner_user_id="system",
        )

    def load_registry_yaml(self) -> None:
        """Загружает ``registry.yaml`` в ``_registry`` и ``_defaults`` (секция ``defaults``)."""
        if not self.registry_path.exists():
            logger.warning("flows.loader.registry_missing", path=str(self.registry_path))
            self._registry = {}
            self._bundle_registry = FlowBundleRegistry()
            self._defaults = {}
            return
        loaded = parse_yaml_value(self.registry_path.read_text(encoding="utf-8"), "registry.yaml")
        if loaded is None:
            self._registry = {}
        else:
            self._registry = require_json_object(loaded, "registry.yaml")
        self._bundle_registry = FlowBundleRegistry.model_validate(self._registry)
        self._defaults = self._bundle_registry.defaults

    async def load_all(self) -> tuple[list[str], list[str]]:
        """
        Загружает flows из ``registry.yaml`` (секция ``flows``) и связанные nodes в БД.

        Возвращает:
            Кортеж (список загруженных flow_id, список загруженных node_id)
        """
        self._target_company_id = "system"

        if not self.registry_path.exists():
            logger.warning("flows.loader.registry_missing", path=str(self.registry_path))
            return [], []

        self.load_registry_yaml()
        registry_bundle_ids = [entry.id for entry in self._bundle_registry.flows]
        bundle_ids = self._expand_bundle_ids_with_dependencies(registry_bundle_ids)

        logger.info(
            "flows.loader.registry_load_started",
            bundle_count=len(bundle_ids),
            registry_bundle_count=len(registry_bundle_ids),
        )

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
                logger.error(
                    "flows.loader.bundle_load_failed",
                    bundle_id=bundle_id,
                    error=str(e),
                    exc_info=True,
                )
                failed_bundle_ids.append(bundle_id)

        logger.info(
            "flows.loader.flows_loaded", count=len(loaded_flow_ids), flow_ids=loaded_flow_ids
        )
        if failed_bundle_ids:
            logger.warning(
                "flows.loader.bundles_failed",
                count=len(failed_bundle_ids),
                bundle_ids=failed_bundle_ids,
            )
        logger.info("flows.loader.nodes_loaded", count=len(self._loaded_nodes))
        return loaded_flow_ids, self._loaded_nodes

    async def preload_nodes_to_cache(self, bundle_id: str) -> None:
        """Предзагрузка nodes из каталога bundle в session memo (без сохранения flow в БД)."""
        if bundle_id in self._preloaded_bundle_ids:
            return

        bundle_dir = self.bundles_dir / bundle_id

        nodes_path = bundle_dir / "nodes.json"
        if not nodes_path.exists():
            self._preloaded_bundle_ids.add(bundle_id)
            return

        await self._load_nodes(bundle_dir, nodes_path)
        self._preloaded_bundle_ids.add(bundle_id)

    async def _ensure_references_resolved(self, reference_ids: set[str]) -> None:
        """Подгружает tool/node refs по явным ID через found_unique_by_tool_ids (demand-driven)."""
        if not reference_ids:
            return

        missing_tool_lookup = [
            ref_id
            for ref_id in reference_ids
            if ref_id not in self._tools_cache and ref_id not in self._nodes_cache
        ]
        if not missing_tool_lookup:
            return

        resolved_tools = await ToolReference.found_unique_by_tool_ids(missing_tool_lookup)
        for ref_id, tool_ref in resolved_tools.items():
            if tool_ref.tool_id.startswith("mcp:"):
                continue
            if not tool_ref.code:
                raise ValueError(
                    f"Tool '{tool_ref.tool_id}' in the database has no code. "
                    + "Custom code tools must have inline code for the isolated runner."
                )
            self._tools_cache[ref_id] = tool_ref

        still_missing = [
            ref_id
            for ref_id in missing_tool_lookup
            if ref_id not in self._tools_cache and ref_id not in self._nodes_cache
        ]
        if not still_missing:
            logger.info(
                "flows.loader.tool_refs_resolved",
                tool_count=len(resolved_tools),
                node_count=0,
            )
            return

        resolved_nodes = await NodeConfig.get_many(still_missing)
        for ref_id, node_config in resolved_nodes.items():
            self._nodes_cache[ref_id] = node_config

        logger.info(
            "flows.loader.tool_refs_resolved",
            tool_count=len(resolved_tools),
            node_count=len(resolved_nodes),
        )

    def _collect_reference_ids_from_tool(self, tool: JsonValue) -> set[str]:
        if isinstance(tool, str):
            return {tool}

        if isinstance(tool, dict):
            tool_payload = tool
            tool_id = tool_payload.get("tool_id")
            exec_kind = tool_payload.get("type")
            code_mode = tool_payload.get("code_mode")

            if exec_kind == "llm_node" or tool_payload.get("prompt"):
                nested_tools = tool_payload.get("tools")
                if isinstance(nested_tools, list):
                    return self._collect_reference_ids_from_tools(
                        require_json_array(nested_tools, "tool.tools")
                    )
                return set()

            if exec_kind in _INLINE_SELF_CONTAINED_TOOL_TYPES:
                return set()
            if code_mode == CodeMode.MCP_TOOL.value:
                return set()

            if isinstance(tool_id, str) and tool_id and not tool_payload.get("code"):
                return {tool_id}

            if tool_payload.get("code") or tool_payload.get("prompt"):
                return set()

            return set()

        return set()

    def _collect_reference_ids_from_tools(self, tools: JsonArray) -> set[str]:
        reference_ids: set[str] = set()
        for tool in tools:
            reference_ids.update(self._collect_reference_ids_from_tool(tool))
        return reference_ids

    def _collect_reference_ids_from_nodes(self, nodes: dict[str, JsonObject]) -> set[str]:
        reference_ids: set[str] = set()
        for node_id, node_config in nodes.items():
            if node_config.get("type") == "code":
                tool_id = node_config.get("tool_id")
                if isinstance(tool_id, str) and tool_id and not node_config.get("code"):
                    reference_ids.add(tool_id)

            tools_raw = node_config.get("tools", [])
            reference_ids.update(
                self._collect_reference_ids_from_tools(
                    require_json_array(tools_raw, f"nodes.{node_id}.tools")
                )
            )
        return reference_ids

    def _collect_reference_ids(
        self,
        nodes: dict[str, JsonObject],
        branches: dict[str, JsonObject],
    ) -> set[str]:
        reference_ids = self._collect_reference_ids_from_nodes(nodes)
        for branch_id, branch_cfg in branches.items():
            branch_nodes_raw = branch_cfg.get("nodes", {})
            if not isinstance(branch_nodes_raw, dict):
                continue
            branch_nodes = {
                node_id: require_json_object(node_payload, f"branch.{branch_id}.nodes.{node_id}")
                for node_id, node_payload in branch_nodes_raw.items()
            }
            reference_ids.update(self._collect_reference_ids_from_nodes(branch_nodes))
        return reference_ids

    async def _load_flow_bundle(
        self,
        bundle_id: str,
        *,
        target_flow_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> str | None:
        """Один каталог bundle -> FlowConfig в БД. Nodes предзагружены в preload_nodes_to_cache."""
        flow_config = await self.build_flow_bundle_config(bundle_id)
        if flow_config is None:
            return None

        overrides: dict[str, str] = {}
        if target_flow_id is not None and target_flow_id != flow_config.flow_id:
            # Копия из каталога под другим id — не 1:1 file-backed entry registry.
            overrides["flow_id"] = target_flow_id
            overrides["source"] = "api"
        if name is not None:
            overrides["name"] = name
        if description is not None:
            overrides["description"] = description
        if overrides:
            flow_config = flow_config.model_copy(update=overrides)

        previous = await FlowConfig.current_for_flow(flow_config.flow_id)
        _ = await FlowConfig.create_version(flow_config)
        try:
            await self._sync_loaded_flow(flow_config)
        except Exception:
            if previous is None:
                _ = await FlowConfig.delete_by_flow_id(flow_config.flow_id)
            else:
                _ = await FlowConfig.create_version(previous)
            raise

        logger.info(
            "flows.loader.bundle_saved",
            bundle_id=bundle_id,
            flow_id=flow_config.flow_id,
            name=flow_config.name,
        )
        return flow_config.flow_id

    async def build_flow_bundle_config(self, bundle_id: str) -> FlowConfig | None:
        """Собирает FlowConfig из bundle без сохранения в БД."""
        bundle_dir = self.bundles_dir / bundle_id
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            logger.warning("flows.loader.flow_json_missing", bundle_dir=str(bundle_dir))
            return None

        if not self._defaults and self.registry_path.exists():
            self.load_registry_yaml()

        await self.preload_nodes_to_cache(bundle_id)

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = parse_json_object(f.read(), "flow.json")

        nodes = await self._load_nodes_with_prompts(bundle_dir, raw_config)
        nodes = self._apply_defaults(nodes)
        branches = await self._load_branches_with_prompts(bundle_dir, raw_config)
        reference_ids = self._collect_reference_ids(nodes, branches)
        await self._ensure_references_resolved(reference_ids)
        nodes = self._inline_tools_in_nodes(nodes)
        branches = self._inline_tools_in_branches(branches)

        edges = require_json_array(raw_config.get("edges", []), "flow.edges")

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
            raise ValueError("flow.json: flow_id is required and must be a non-empty string")
        raw_name = raw_config.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("flow.json: name is required and must be a non-empty string")
        raw_entry = raw_config.get("entry")
        if not isinstance(raw_entry, str) or not raw_entry.strip():
            raise ValueError("flow.json: entry is required and must be a non-empty string")

        raw_hidden = raw_config.get("hidden", False)
        if not isinstance(raw_hidden, bool):
            raise ValueError("flow.json: hidden must be boolean")

        depends_on_flow_ids = self._read_bundle_depends_on_flow_ids(bundle_dir)

        raw_interface = raw_config.get("interface")
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
                "hidden": raw_hidden,
                "depends_on_flow_ids": depends_on_flow_ids,
                **({"interface": raw_interface} if raw_interface is not None else {}),
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
            record = await self._upload_flow_asset_file(
                data=data,
                original_name=original_name,
                content_type=content_type,
                flow_id=bundle_dir.name,
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
            nodes_list = parse_json_array(f.read(), "nodes.json")

        for raw_node in nodes_list:
            if not isinstance(raw_node, dict):
                logger.warning("flows.loader.node_not_object", nodes_path=str(nodes_path))
                continue
            node_id = raw_node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                logger.warning("flows.loader.node_missing_id", nodes_path=str(nodes_path))
                continue

            # Инлайним промпт и схему structured output из файлов
            raw_node = self._inline_prompt_from_file(raw_node, bundle_dir)
            raw_node = self._inline_output_schema_file(raw_node, bundle_dir)
            raw_node = await self._materialize_node_files(raw_node, node_id, bundle_dir.name)

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
                    "agent_skills": raw_node.get("agent_skills", []),
                    "llm": llm_config,
                    "llm_context": llm_context,
                    "llm_context_resource_key": raw_node.get("llm_context_resource_key"),
                    "llm_capability": raw_node.get("llm_capability"),
                    "structured_output": raw_node.get("structured_output", False),
                    "output_schema": raw_node.get("output_schema"),
                    "react": raw_node.get("react"),
                    "code": raw_node.get("code"),
                    "parameters_schema": raw_node.get("parameters_schema"),
                    "files": raw_node.get("files", []),
                    "local_variables": raw_node.get("variables", {}),
                    "source": "file",
                }
            )

            _ = await NodeConfig.set(node_config)
            # Добавляем в кеш для инлайнинга в flows
            self._nodes_cache[node_id] = node_config
            self._loaded_nodes.append(node_id)
            logger.info("flows.loader.node_saved", node_id=node_id)

    def _resolve_target_company_id(self) -> str:
        context = get_context()
        if context and context.active_company and context.active_company.company_id:
            return context.active_company.company_id
        if self._target_company_id:
            return self._target_company_id
        raise ValueError("Failed to determine company_id for bundle file materialization")

    async def _upload_flow_asset_file(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        flow_id: str,
        is_public: bool,
    ) -> FileRecord:
        if self.files_service is None:
            raise RuntimeError("files_service required to place a flow asset in Documents")
        return await self.files_service.get_or_create_flow_asset(
            data=data,
            original_name=original_name,
            content_type=content_type,
            flow_id=flow_id,
            is_public=is_public,
        )

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

        raise ValueError(f"Node '{node_id}': files[{index}] must contain url")

    async def _materialize_node_files(
        self,
        node: JsonObject,
        node_id: str,
        flow_id: str,
    ) -> JsonObject:
        files = node.get("files")
        if not files:
            return node
        if not isinstance(files, list):
            raise ValueError(f"Node '{node_id}': files must be a list")

        reader = FileReader()

        materialized: JsonArray = []
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                raise ValueError(f"Node '{node_id}': files[{index}] must be an object")
            file_entry = entry
            original_name_value = file_entry.get("original_name")
            if not isinstance(original_name_value, str) or not original_name_value.strip():
                raise ValueError(
                    f"Node '{node_id}': files[{index}].original_name must be a non-empty string"
                )
            content_type = file_entry.get("content_type")
            if not isinstance(content_type, str) or not content_type.strip():
                raise ValueError(
                    f"Node '{node_id}': files[{index}].content_type must be a non-empty string"
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
                flow_id=flow_id,
                is_public=False,
            )
            item = stored_file_ref(record)
            materialized.append(item.to_json_object())

        node["files"] = materialized
        return node

    def _convert_tools(
        self,
        tools_list: JsonArray,
    ) -> list[FlowToolReference | ToolReference]:
        """Конвертирует список tools в List[ToolReference]."""
        result: list[FlowToolReference | ToolReference] = []
        for tool in tools_list:
            if isinstance(tool, str):
                result.append(ToolReference(tool_id=tool))
            elif isinstance(tool, dict):
                if tool.get("type") == "flow":
                    result.append(FlowToolReference.model_validate(tool))
                else:
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
            node = await self._materialize_node_files(node, node_id, bundle_dir.name)

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
            raise ValueError("node.prompt_file is forbidden; use node.prompt")

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
            node["output_schema"] = parse_json_object(f.read(), f"{schema_path}.output_schema")
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

            logger.debug(
                "flows.loader.node_code_inlined", node_id=node_id, function_path=function_path
            )
        except Exception as e:
            logger.error(
                "flows.loader.node_code_load_failed",
                node_id=node_id,
                function_path=function_path,
                error=str(e),
            )

    async def _load_branches_with_prompts(
        self, bundle_dir: Path, config: JsonObject
    ) -> dict[str, JsonObject]:
        """Загружает ветки (branches) и встраивает промпты для нод в каждой ветке."""
        raw_branches = config.get("branches")
        if raw_branches is None:
            raise ValueError("flow.json: branches field is required (object of branches)")
        if not raw_branches:
            return {}
        if not isinstance(raw_branches, dict):
            raise ValueError("flow.json: branches must be an object")

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
                    node = await self._materialize_node_files(
                        node, f"{branch_id}.{node_id}", bundle_dir.name
                    )
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
                        logger.debug(
                            "flows.loader.tool_code_inlined", node_id=node_id, tool_id=tool_id
                        )
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
            raise ValueError(f"{context}: inlining recursion depth exceeded")

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
                logger.debug("flows.loader.tool_ref_resolved", context=context, tool_id=tool)
                return result

            # Если не нашли как tool - ищем в nodes_cache (node используется как tool)
            node_config = self._get_node_from_cache(tool)
            if node_config:
                return self._inline_node_as_tool(node_config, context, depth)

            raise ValueError(f"{context}: ID '{tool}' not found in tools_cache or nodes_cache")

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
            if exec_kind == "flow":
                flow_ref = FlowToolReference.model_validate(tool_payload)
                logger.debug(
                    "flows.loader.inline_flow_tool", context=context, tool_id=flow_ref.tool_id
                )
                return require_json_object(
                    flow_ref.model_dump(mode="json", exclude_none=True),
                    f"{context}.flow_tool",
                )
            if exec_kind in _INLINE_SELF_CONTAINED_TOOL_TYPES:
                logger.debug(
                    "flows.loader.inline_tool",
                    context=context,
                    tool_id=tool_id,
                    exec_kind=exec_kind,
                )
                return tool_payload
            if code_mode == CodeMode.MCP_TOOL.value:
                logger.debug("flows.loader.inline_mcp_tool", context=context, tool_id=tool_id)
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
                    logger.debug("flows.loader.tool_ref_resolved", context=context, tool_id=tool_id)
                    return merged

                # Если не нашли как tool - ищем в nodes_cache (node как tool)
                node_config = self._get_node_from_cache(tool_id)
                if node_config:
                    return self._inline_node_as_tool(node_config, context, depth)

                raise ValueError(
                    f"{context}: tool '{tool_id}' not found in tools_cache or nodes_cache"
                )

            if not tool_payload.get("code") and not tool_payload.get("prompt"):
                raise ValueError(
                    f"{context}: inline tool requires 'type', 'code' or 'prompt': {tool_payload}"
                )

            return tool_payload

        raise ValueError(f"{context}: unknown tool format: {type(tool)}")

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

        logger.debug("flows.loader.llm_node_inlined", context=context, node_id=node_id, depth=depth)
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

        logger.debug(
            "flows.loader.node_as_tool_inlined", context=context, node_id=node_config.node_id
        )
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
                f"Node '{node_id}': only 1 reasoning tool is allowed, found {len(reason_tools)}: {names}"
            )

        if len(exit_tools) > 1:
            names = [t.get("tool_id") or t.get("name") for t in exit_tools]
            raise ValueError(
                f"Node '{node_id}': only 1 exit tool is allowed, found {len(exit_tools)}: {names}"
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

        if not self.registry_path.exists():
            logger.warning("flows.loader.registry_missing", path=str(self.registry_path))
            return {"flows": 0, "tools": 0, "nodes": 0}

        self.load_registry_yaml()

        # Определяем нужно ли фильтровать
        should_filter = filter_public and company_id != "system"

        bundles_to_load: list[str] = []
        for entry in self._bundle_registry.flows:
            if not should_filter or entry.public:
                bundles_to_load.append(entry.id)

        expanded_bundle_ids = self._expand_bundle_ids_with_dependencies(bundles_to_load)

        logger.info(
            "flows.loader.company_load_started",
            company_id=company_id,
            bundle_count=len(expanded_bundle_ids),
            registry_bundle_count=len(bundles_to_load),
            filter_public=should_filter,
        )

        for bundle_id in expanded_bundle_ids:
            await self.preload_nodes_to_cache(bundle_id)

        loaded_flow_ids: list[str] = []
        failed_bundle_ids: list[str] = []
        for bundle_id in expanded_bundle_ids:
            try:
                flow_id = await self._load_flow_bundle(bundle_id)
                if flow_id:
                    loaded_flow_ids.append(flow_id)
                else:
                    failed_bundle_ids.append(bundle_id)
            except Exception as e:
                logger.error(
                    "flows.loader.bundle_load_failed",
                    bundle_id=bundle_id,
                    error=str(e),
                    exc_info=True,
                )
                failed_bundle_ids.append(bundle_id)

        logger.info(
            "flows.loader.company_flows_loaded", company_id=company_id, count=len(loaded_flow_ids)
        )
        if failed_bundle_ids:
            logger.warning(
                "flows.loader.bundles_failed",
                count=len(failed_bundle_ids),
                bundle_ids=failed_bundle_ids,
            )

        # Возвращаем статистику
        stats = {
            "flows": len(loaded_flow_ids),
            "tools": 0,  # TODO: если нужна отдельная загрузка tools
            "nodes": len(self._loaded_nodes),
        }

        return stats

    @staticmethod
    def _parse_bundle_depends_on_flow_ids(raw_flow: JsonObject, bundle_name: str) -> list[str]:
        raw_deps = raw_flow.get("depends_on_flow_ids")
        if raw_deps is None:
            raw_deps = raw_flow.get("install_with_bundles", [])
        if raw_deps is None:
            return []
        if not isinstance(raw_deps, list):
            raise ValueError(f"Bundle '{bundle_name}': depends_on_flow_ids must be list[str]")
        deps: list[str] = []
        for item in raw_deps:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Bundle '{bundle_name}': depends_on_flow_ids entries must be non-empty strings"
                )
            deps.append(item.strip())
        return deps

    def _read_bundle_depends_on_flow_ids(self, bundle_dir: Path) -> list[str]:
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            return []
        with open(config_path, "r", encoding="utf-8") as f:
            raw_flow = parse_json_object(f.read(), f"{bundle_dir.name}.flow")
        return self._parse_bundle_depends_on_flow_ids(raw_flow, bundle_dir.name)

    def _expand_bundle_ids_with_dependencies(self, bundle_ids: list[str]) -> list[str]:
        """
        Топологический порядок: зависимости раньше зависимого bundle.
        Каждый bundle_id в результате не более одного раза.
        """
        ordered: list[str] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def visit(bundle_id: str, path: list[str]) -> None:
            if bundle_id in seen:
                return
            if bundle_id in visiting:
                chain = " -> ".join(path + [bundle_id])
                raise ValueError(f"Cycle in depends_on_flow_ids: {chain}")
            visiting.add(bundle_id)
            bundle_dir = self.bundles_dir / bundle_id
            for dep_id in self._read_bundle_depends_on_flow_ids(bundle_dir):
                visit(dep_id, path + [bundle_id])
            visiting.remove(bundle_id)
            seen.add(bundle_id)
            ordered.append(bundle_id)

        for bundle_id in bundle_ids:
            visit(bundle_id, [])
        return ordered

    async def _reload_bundle_chain(
        self,
        bundle_id: str,
        *,
        seen: set[str],
        target_flow_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        if bundle_id in seen:
            return target_flow_id if target_flow_id is not None else bundle_id
        seen.add(bundle_id)
        bundle_dir = self.bundles_dir / bundle_id
        config_path = bundle_dir / "flow.json"
        if not config_path.exists():
            raise ValueError(
                f"Bundle directory '{bundle_id}' not found or has no flow.json: {bundle_dir}"
            )
        for companion_id in self._read_bundle_depends_on_flow_ids(bundle_dir):
            _ = await self._reload_bundle_chain(companion_id, seen=seen)
        await self.preload_nodes_to_cache(bundle_id)
        loaded_flow_id = await self._load_flow_bundle(
            bundle_id,
            target_flow_id=target_flow_id,
            name=name,
            description=description,
        )
        if not loaded_flow_id:
            raise ValueError(f"Failed to load bundle '{bundle_id}' into the database")
        return loaded_flow_id

    async def reload_flow_bundle(
        self,
        bundle_id: str,
        *,
        target_flow_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Перезаписывает один flow и связанные nodes из каталога ``bundles/<bundle_id>/`` в БД.

        ``target_flow_id`` / ``name`` / ``description`` — установка под другим id или с
        override метаданных (зависимости ``depends_on_flow_ids`` грузятся без remap).

        Использует тот же путь, что и полная загрузка registry: demand-driven резолв refs, defaults из registry.
        """
        context = get_context()
        if not context or not context.active_company or not context.active_company.company_id:
            raise ValueError("reload_flow_bundle requires active_company in the context")
        self._target_company_id = context.active_company.company_id

        if not self.registry_path.exists():
            raise ValueError(f"Registry not found: {self.registry_path}")

        self.load_registry_yaml()

        seen: set[str] = set()
        return await self._reload_bundle_chain(
            bundle_id,
            seen=seen,
            target_flow_id=target_flow_id,
            name=name,
            description=description,
        )


async def load_flows_to_db(
    flow_access_service: FlowAccessService,
    bundles_dir: Path | None = None,
    *,
    files_service: FilesService,
) -> tuple[list[str], list[str]]:
    """
    Загружает flows и nodes в БД из каталога с bundle-подпапками и registry.yaml.

    Для каждого id из registry читается ``{bundles_dir}/{bundle_id}/flow.json`` (и nodes),
    tools подтягиваются из ``tool_repository`` и инлайнятся в конфиг.

    Аргументы:
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
        bundles_dir,
        registry_path=registry_path,
        flow_access_service=flow_access_service,
        files_service=files_service,
    )
    return await loader.load_all()


async def load_tools_to_db(
    modules: list[str] | None = None,
    *,
    flow_access_service: FlowAccessService,
    company_id: str = "system",
) -> list[str]:
    """
    Загружает контракты trusted platform tools из Python модулей в БД.

    Поддерживает:
    - FunctionTool (созданные через @tool декоратор) - сохраняет schema/metadata без source-кода

    Аргументы:
        modules: Список модулей для загрузки
        flow_access_service: dual-write OpenFGA для tool tuples
        company_id: компания для company#member viewer (seed — system)

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

        _ = await ToolReference.set(tool_ref)
        await flow_access_service.sync_tool_saved(
            tool_id,
            company_id=company_id,
            permission=tool_ref.permission,
        )
        loaded.append(tool_id)
        loaded_ids.add(tool_id)
        logger.info("flows.loader.function_tool_saved", tool_id=tool_id)

    logger.info("flows.loader.tools_loaded", count=len(loaded))
    return loaded
