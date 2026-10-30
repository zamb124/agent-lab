"""
FlowFactory - создание flow из БД.
"""

import copy
from collections.abc import Mapping
from typing import overload

from apps.flows.src.contracts import (
    EffectiveFlowConfig,
    FlowNodeRuntimeConfig,
    RuntimeFlowProtocol,
    ToolRegistryProtocol,
)
from apps.flows.src.models import BranchConfig, FlowConfig, ResourceMapInput, ResourceReference
from apps.flows.src.models.enums import MergeMode
from apps.flows.src.models.flow_config import Edge
from apps.flows.src.resources.json_merge import deep_merge
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import NodeConstructor
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.graph_compiler import GraphCompiler
from core.context import require_context
from core.errors import InvalidGraphError
from core.logging import get_logger
from core.types import JsonArray, JsonObject, JsonValue, require_json_object
from core.variables import VarResolver
from core.variables.service import VariablesService

logger = get_logger(__name__)


class FlowFactory:
    """Фабрика для создания Flow из БД."""

    def __init__(
        self,
        variables_service: VariablesService,
        graph_compiler: GraphCompiler,
        node_constructor: NodeConstructor,
        flow_access_service: FlowAccessService,
    ):
        self.variables_service: VariablesService = variables_service
        self.compiler: GraphCompiler = graph_compiler
        self.node_constructor: NodeConstructor = node_constructor
        self.flow_access_service: FlowAccessService = flow_access_service

    @staticmethod
    def _resource_map_to_plain(ref_map: dict[str, ResourceReference] | None) -> ResourceMapInput:
        """ResourceReference и dict в плоский dict для ResourceResolver."""
        out: ResourceMapInput = {}
        for key, value in (ref_map or {}).items():
            out[key] = require_json_object(
                value.model_dump(mode="json", exclude_none=True),
                f"resources.{key}",
            )
        return out

    async def get_flow_config_snapshot(
        self, flow_id: str, config_version: str | None = None
    ) -> FlowConfig | None:
        """Снимок FlowConfig: конкретная версия или последняя в flows."""
        if config_version:
            return await FlowConfig.by_flow_id_and_version(flow_id, config_version)
        return await FlowConfig.current_for_flow(flow_id)

    async def get_flow(
        self,
        flow_id: str,
        branch_id: str = "default",
        config_version: str | None = None,
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol | None:
        """
        Загружает flow из БД и создаёт Flow.
        Применяет skill overrides если указан branch_id.

        Аргументы:
            flow_id: ID flow
            branch_id: ID skill (по умолчанию "default")
            config_version: версия из flows_versions; None = последняя запись в flows

        Возвращает:
            Flow или None
        """
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' version '{config_version}' not found in flows_versions"
                )
            logger.warning("flows.factory.flow_missing", flow_id=flow_id)
            return None

        return await self._create_flow(config, branch_id, tool_registry=tool_registry)

    async def get_resource_maps(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> tuple[ResourceMapInput, ResourceMapInput | None]:
        """
        Ресурсы уровня flow и skill из БД (без inline state.flow_config).

        Возвращает:
            (flow_resources, skill_resources или None)
        """
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' version '{config_version}' not found in flows_versions"
                )
            return {}, None

        flow_resources = self._resource_map_to_plain(config.resources)
        skill_resources: ResourceMapInput | None = None
        if (
            branch_id
            and branch_id != "default"
            and config.branches
            and branch_id in config.branches
        ):
            sk = config.branches[branch_id]
            raw_skill_res = sk.resources or {}
            if raw_skill_res:
                skill_resources = self._resource_map_to_plain(raw_skill_res)

        return flow_resources, skill_resources

    async def get_effective_nodes_map(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> dict[str, FlowNodeRuntimeConfig]:
        """Ноды графа после применения skill (для evaluation и отладки)."""
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' version '{config_version}' not found in flows_versions"
                )
            raise ValueError(f"Flow '{flow_id}' not found")
        effective = self.apply_branch(config, branch_id)
        nodes = effective["nodes"]
        return nodes

    async def get_resolved_variables_map(
        self,
        flow_id: str,
        branch_id: str = "default",
        *,
        config_version: str | None = None,
    ) -> JsonObject:
        """
        Словарь resolved variables для flow+skill — тот же, что попадает в ``Flow.variables``
        (после ``apply_branch`` и ``_resolve_variables``), без сборки графа.
        """
        config = await self.get_flow_config_snapshot(flow_id, config_version)
        if config is None:
            if config_version:
                raise ValueError(
                    f"Flow '{flow_id}' version '{config_version}' not found in flows_versions"
                )
            raise ValueError(f"Flow '{flow_id}' not found")
        effective = self.apply_branch(config, branch_id)
        return await self._resolve_variables(effective["variables"])

    async def _create_flow(
        self,
        config: FlowConfig,
        branch_id: str = "default",
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol:
        """
        Создаёт Flow из FlowConfig с применением skill.

        Zero-Guess: валидация графа через GraphCompiler перед созданием flow.

        Аргументы:
            config: FlowConfig из БД
            branch_id: ID skill для применения

        Возвращает:
            Flow
        """
        effective = self.apply_branch(config, branch_id)
        entry = effective["entry"]
        if entry is None:
            raise InvalidGraphError(
                message=f"Flow '{config.flow_id}' branch '{branch_id}' has no entry node",
                payload={"flow_id": config.flow_id, "branch_id": branch_id},
            )

        # Валидация графа через GraphCompiler
        _ = self.compiler.compile(
            flow_id=config.flow_id,
            branch_id=branch_id,
            entry=entry,
            nodes=effective["nodes"],
            edges=effective["edges"],
            variables=effective["variables"],
        )

        resolved_variables = await self._resolve_variables(effective["variables"])

        edges = [
            {
                "from_node": e.from_node,
                "to_node": e.to_node,
                "condition": (
                    e.condition.model_dump(mode="json") if e.condition is not None else None
                ),
                "from_port": e.from_port,
                "contributes_to_join": e.contributes_to_join,
            }
            for e in effective["edges"]
        ]

        # Полный inline конфиг
        config_dict = require_json_object(config.model_dump(mode="json"), "flow_config")
        config_dict["resolved_variables"] = resolved_variables
        config_dict["entry"] = entry
        config_dict["nodes"] = effective["nodes"]
        config_dict["edges"] = edges
        config_dict["interface"] = config.interface_for_branch(branch_id).model_dump(mode="json")

        return await Flow.from_config(
            config_dict,
            node_constructor=self.node_constructor,
            tool_registry=tool_registry,
            flow_factory=self,
        )

    async def create_validation_flow(
        self,
        config: JsonObject,
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol:
        """Создаёт transient Flow из уже собранного inline config для валидатора."""
        return await Flow.from_config(
            config,
            node_constructor=self.node_constructor,
            tool_registry=tool_registry,
            flow_factory=self,
        )

    def apply_branch(self, config: FlowConfig, branch_id: str) -> EffectiveFlowConfig:
        """
        Применяет ветку (branch) к конфигу flow.

        Аргументы:
            config: FlowConfig
            branch_id: ID ветки

        Возвращает:
            Dict с effective конфигом (entry, nodes, edges, variables)
        """
        # Извлекаем значения из FlowVariableConfig объектов
        variables_dict: JsonObject = {}
        for key, value in config.variables.items():
            variables_dict[key] = value.value

        result: EffectiveFlowConfig = {
            "entry": config.entry,
            "nodes": copy.deepcopy(config.nodes or {}),
            "edges": list(config.edges),
            "variables": variables_dict,
        }

        if not config.branches:
            return result

        branch = config.branches.get(branch_id)
        if branch is None:
            if branch_id != "default":
                logger.warning("flows.factory.branch_missing", branch_id=branch_id, flow_id=config.flow_id)
            return result

        # Точка входа (всегда replace)
        if branch.entry:
            result["entry"] = branch.entry

        # Ноды
        if branch.nodes is not None:
            if branch.nodes_mode == MergeMode.MERGE:
                self._merge_nodes(result["nodes"], branch.nodes)
            else:
                result["nodes"] = copy.deepcopy(branch.nodes)

        # Рёбра
        if branch.edges is not None:
            if branch.edges_mode == MergeMode.MERGE:
                self._merge_edges(result["edges"], branch.edges)
            else:
                result["edges"] = list(branch.edges)

        # Переменные
        if branch.variables:
            branch_vars: JsonObject = {}
            for key, value in branch.variables.items():
                branch_vars[key] = value.value

            if branch.variables_mode == MergeMode.MERGE:
                result["variables"].update(branch_vars)
            else:
                result["variables"] = branch_vars

        return result

    def _merge_nodes(
        self,
        base_nodes: dict[str, FlowNodeRuntimeConfig],
        skill_nodes: dict[str, FlowNodeRuntimeConfig],
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

    def _merge_edges(self, base_edges: list[Edge], skill_edges: list[Edge]) -> None:
        """
        Мержит skill edges в base edges.
        Edges с той же парой (from_node, to_node) заменяются, новые добавляются.
        """
        skill_edge_pairs = {(e.from_node, e.to_node) for e in skill_edges}

        filtered = [e for e in base_edges if (e.from_node, e.to_node) not in skill_edge_pairs]
        base_edges.clear()
        base_edges.extend(filtered)
        base_edges.extend(skill_edges)

    async def _resolve_variables(self, variables: JsonObject) -> JsonObject:
        """
        Резолвит @var:key ссылки в переменных и извлекает значения из FlowVariableConfig.

        Если company variable не существует — значение становится None.

        Аргументы:
            variables: Словарь FlowVariableConfig объектов

        Возвращает:
            Словарь с резолвнутыми значениями (только values, без метаданных)
        """
        company_variables = await self.variables_service.get_company_variables_map()
        resolved = self._resolve_flow_variables(
            value=variables,
            company_variables=company_variables,
        )

        result: JsonObject = {}
        for key, value in resolved.items():
            if isinstance(value, dict) and "value" in value:
                result[key] = value["value"]
            else:
                result[key] = value

        return result

    @overload
    def _resolve_flow_variables(
        self,
        value: JsonObject,
        company_variables: Mapping[str, JsonValue],
    ) -> JsonObject: ...

    @overload
    def _resolve_flow_variables(
        self,
        value: JsonArray,
        company_variables: Mapping[str, JsonValue],
    ) -> JsonArray: ...

    @overload
    def _resolve_flow_variables(
        self,
        value: JsonValue,
        company_variables: Mapping[str, JsonValue],
    ) -> JsonValue: ...

    def _resolve_flow_variables(
        self,
        value: JsonValue,
        company_variables: Mapping[str, JsonValue],
    ) -> JsonValue:
        if isinstance(value, dict):
            return {
                key: self._resolve_flow_variables(item, company_variables)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_flow_variables(item, company_variables) for item in value]
        if not isinstance(value, str):
            return value

        return VarResolver.resolve_for_flow_variable(value, company_variables)

    async def create_flow(
        self,
        config: FlowConfig,
        branch_id: str = "default",
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol:
        """
        Сохраняет FlowConfig в БД и создаёт Flow.

        Аргументы:
            config: FlowConfig
            branch_id: ID skill (по умолчанию "default")

        Возвращает:
            Flow
        """
        previous = await FlowConfig.current_for_flow(config.flow_id)
        _ = await FlowConfig.create_version(config)
        ctx = require_context()
        if ctx.active_company is None:
            raise ValueError("active company required for flow authz sync")
        try:
            await self.flow_access_service.sync_flow_saved(
                config,
                company_id=ctx.active_company.company_id,
                owner_user_id=ctx.user.user_id,
            )
        except Exception:
            if previous is None:
                _ = await FlowConfig.delete_by_flow_id(config.flow_id)
            else:
                _ = await FlowConfig.create_version(previous)
            raise
        logger.info("flows.factory.flow_saved", flow_id=config.flow_id)
        return await self._create_flow(config, branch_id, tool_registry=tool_registry)

    async def delete_flow(self, flow_id: str) -> bool:
        """Удаляет flow из БД"""
        ctx = require_context()
        if ctx.active_company is None:
            raise ValueError("active company required for flow authz sync")
        config = await FlowConfig.current_for_flow(flow_id)
        branch_ids = list(config.branches.keys()) if config is not None else []
        deleted = await FlowConfig.delete_by_flow_id(flow_id)
        if deleted:
            await self.flow_access_service.sync_flow_deleted(
                flow_id,
                company_id=ctx.active_company.company_id,
                branch_ids=branch_ids,
            )
        return deleted

    async def get_branches(self, flow_id: str) -> dict[str, BranchConfig]:
        """
        Возвращает ветки flow.
        Если branches не заданы — возвращает default-ветку.

        Аргументы:
            flow_id: ID flow
        Возвращает:
            Dict branch_id -> BranchConfig
        """
        config = await FlowConfig.current_for_flow(flow_id)
        if config is None:
            return {}

        if config.branches:
            return config.branches

        return {
            "default": BranchConfig(
                name=config.name,
                description=config.description or "",
                tags=config.tags,
            )
        }
