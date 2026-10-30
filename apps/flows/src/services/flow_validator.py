"""
FlowValidator - валидация структуры и ссылок во flow.

Проверки:
1. Структура графа: entry, edges, достижимость нод
2. Ссылки: flow_id, tools, flow (inline tool), remote_flow
3. Переменные: @var: в input_mapping, url, headers
4. Inline code: парсинг обращений к state
5. Попытка сборки Flow
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from apps.flows.src.flow_ui.templates import default_chat_document
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.models.urn import extract_resource_id
from apps.flows.src.reflection import default_pass_fail_exits
from apps.flows.src.state.node_files import validate_node_files_list
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object

if TYPE_CHECKING:
    from apps.flows.src.contracts import RuntimeFlowProtocol
    from apps.flows.src.runtime.flow import Flow

logger = get_logger(__name__)


_EDGE_ALLOWED_FIELDS = frozenset(
    {"from_node", "to_node", "condition", "from_port", "contributes_to_join"}
)

_EVALUATION_ROLES = frozenset({"tester", "judge"})


def _is_evaluation_node(cfg: JsonObject) -> bool:
    """llm_node с store.evaluation_role tester|judge — harness-only, не execution-граф."""
    store = cfg.get("store")
    if not isinstance(store, dict):
        return False
    role = store.get("evaluation_role")
    return isinstance(role, str) and role in _EVALUATION_ROLES


def _is_non_execution_graph_node(cfg: JsonObject) -> bool:
    """Resource или evaluation — не участвуют в walk/terminal/unreachable."""
    if cfg.get("type") == "resource":
        return True
    return _is_evaluation_node(cfg)


def _edge_endpoint_ids(edge: JsonObject) -> tuple[str | None, str | None]:
    """Возвращает канонические концы ребра."""
    fn = edge.get("from_node")
    tn = edge.get("to_node")
    if not isinstance(fn, str) or fn == "":
        fn = None
    if not isinstance(tn, str) or tn == "":
        tn = None
    return (fn, tn)


def _default_reflection_exit_ids() -> frozenset[str]:
    return frozenset(exit_item.exit_id for exit_item in default_pass_fail_exits())


def _reflection_exit_ids(node_cfg: JsonObject) -> frozenset[str]:
    """exit_id из critic_policy.exits; без/пустых exits — default approved/blocked."""
    raw_policy = node_cfg.get("critic_policy")
    if not isinstance(raw_policy, dict):
        return _default_reflection_exit_ids()
    raw_exits = raw_policy.get("exits")
    if raw_exits is None:
        return _default_reflection_exit_ids()
    if not isinstance(raw_exits, list):
        return _default_reflection_exit_ids()
    exit_ids: list[str] = []
    for item in raw_exits:
        if not isinstance(item, dict):
            continue
        exit_id = item.get("exit_id")
        if isinstance(exit_id, str) and exit_id.strip() != "":
            exit_ids.append(exit_id)
    if not exit_ids:
        return _default_reflection_exit_ids()
    return frozenset(exit_ids)


def _infer_reflection_exit_port(
    condition: JsonValue | None,
    *,
    allowed_exit_ids: frozenset[str],
) -> str | None:
    """Сопоставляет simple condition с exit_id (validation.exit_id или approved)."""
    if not isinstance(condition, dict):
        return None
    if condition.get("type") != "simple":
        return None
    if condition.get("operator") != "==":
        return None
    variable = condition.get("variable")
    value = condition.get("value")
    if variable == "validation.exit_id":
        if isinstance(value, str) and value in allowed_exit_ids:
            return value
        return None
    if variable == "validation.approved":
        if value is True and "approved" in allowed_exit_ids:
            return "approved"
        if value is False and "blocked" in allowed_exit_ids:
            return "blocked"
        return None
    return None


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class FlowValidationError:
    """Ошибка валидации flow."""

    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    node_id: str | None = None
    details: JsonObject | None = None


@dataclass
class FlowValidationResult:
    """Результат валидации flow."""

    valid: bool
    errors: list[FlowValidationError] = field(default_factory=list)
    state_keys_used: set[str] = field(default_factory=set)
    var_keys_used: set[str] = field(default_factory=set)

    def add_error(
        self,
        code: str,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        node_id: str | None = None,
        details: JsonObject | None = None,
    ) -> None:
        self.errors.append(
            FlowValidationError(
                code=code,
                message=message,
                severity=severity,
                node_id=node_id,
                details=details,
            )
        )
        if severity == ValidationSeverity.ERROR:
            self.valid = False


class FlowValidator:
    """Валидатор конфигурации flow."""

    def __init__(
        self,
        resolve_node_refs: bool = False,
        flow_builder: Callable[[JsonObject], Awaitable["Flow | RuntimeFlowProtocol"]] | None = None,
    ) -> None:
        self._resolve_node_refs: bool = resolve_node_refs
        self.flow_builder: Callable[[JsonObject], Awaitable[Flow | RuntimeFlowProtocol]] | None = (
            flow_builder
        )

    async def validate(
        self,
        nodes: dict[str, JsonObject],
        edges: list[JsonObject],
        entry: str,
        variables: JsonObject,
        flow_id: str | None = None,
    ) -> FlowValidationResult:
        """
        Валидирует конфигурацию flow.

        Аргументы:
            nodes: Словарь нод {node_id: config}
            edges: Список edges [{from_node, to_node, condition}]
            entry: ID entry ноды
            variables: Переменные flow
            flow_id: ID flow (опционально, для контекста)

        Возвращает:
            FlowValidationResult с ошибками и предупреждениями
        """
        result = FlowValidationResult(valid=True)

        # 1. Валидация структуры графа
        self._validate_structure(nodes, edges, entry, result)

        # 2. Валидация ссылок на сущности
        await self._validate_references(nodes, result)

        # 3. Валидация переменных @var:
        self._validate_variables(nodes, variables, result)

        # 4. Парсинг inline code
        self._parse_inline_code(nodes, result)

        # 4b. messages_filter у llm_node (список node_id)
        self._validate_messages_filters(nodes, result)

        # 4c. поле files у нод (как state.files)
        self._validate_node_files(nodes, result)

        self._validate_hitl_nodes(nodes, result)

        # 5. Попытка сборки (если нет критических ошибок)
        if result.valid:
            await self._try_build(nodes, edges, entry, flow_id, result)

        return result

    def _validate_structure(
        self,
        nodes: dict[str, JsonObject],
        edges: list[JsonObject],
        entry: str,
        result: FlowValidationResult,
    ) -> None:
        """Валидация структуры графа."""
        node_ids = set(nodes.keys())

        # Точка входа существует
        if not entry:
            result.add_error(
                code="missing_entry",
                message="Не указана точка входа (entry)",
            )
        elif entry not in node_ids:
            result.add_error(
                code="entry_not_found",
                message=f"Entry нода '{entry}' не найдена в nodes",
                details={"entry": entry, "available_nodes": list(node_ids)},
            )

        # Проверка edges
        for edge in edges:
            extra_fields = sorted(set(edge) - _EDGE_ALLOWED_FIELDS)
            if extra_fields:
                result.add_error(
                    code="edge_unknown_fields",
                    message="Edge содержит поля вне canonical contract",
                    details={"edge": edge, "fields": extra_fields},
                )
                continue

            from_node, to_node = _edge_endpoint_ids(edge)

            if not from_node:
                result.add_error(
                    code="edge_from_missing",
                    message="Edge должен содержать непустой from_node",
                    details={"edge": edge},
                )
            elif from_node not in node_ids:
                result.add_error(
                    code="edge_from_not_found",
                    message=f"Edge from_node '{from_node}' ссылается на несуществующую ноду",
                    details={"edge": edge},
                )

            # to_node может быть null (конец графа)
            if to_node and to_node not in node_ids:
                result.add_error(
                    code="edge_to_not_found",
                    message=f"Edge to_node '{to_node}' ссылается на несуществующую ноду",
                    details={"edge": edge},
                )

            from_port = edge.get("from_port")
            if from_port is not None:
                if not isinstance(from_port, str) or from_port.strip() == "":
                    result.add_error(
                        code="edge_from_port_invalid",
                        message="Edge from_port must be a non-empty string when set",
                        details={"edge": edge},
                    )
                elif from_node and from_node in node_ids:
                    source_cfg = nodes.get(from_node) or {}
                    if source_cfg.get("type") == "reflection":
                        allowed = _reflection_exit_ids(source_cfg)
                        if from_port not in allowed:
                            result.add_error(
                                code="edge_from_port_unknown",
                                message=(
                                    f"Reflection edge from_port must be one of "
                                    f"{sorted(allowed)}, got {from_port!r}"
                                ),
                                node_id=from_node,
                                details={"edge": edge, "allowed_ports": sorted(allowed)},
                            )

        self._check_reflection_exit_coverage(nodes, edges, result)

        for edge in edges:
            e_from, e_to = _edge_endpoint_ids(edge)
            for label, nid in (("from_node", e_from), ("to_node", e_to)):
                if not nid:
                    continue
                if nid not in node_ids:
                    continue
                ncfg = nodes.get(nid) or {}
                if ncfg.get("type") == "resource":
                    result.add_error(
                        code="edge_involves_resource_node",
                        message=f"Ребро не может соединяться с нодой type=resource ('{nid}')",
                        node_id=nid,
                        details={"edge": edge, "endpoint": label},
                    )
                elif _is_evaluation_node(ncfg):
                    result.add_error(
                        code="edge_involves_evaluation_node",
                        message=(
                            f"Ребро не может соединяться с evaluation-нодой "
                            f"(tester/judge) '{nid}'"
                        ),
                        node_id=nid,
                        details={"edge": edge, "endpoint": label},
                    )

        # Проверка достижимости нод от entry
        if entry and entry in node_ids:
            reachable = self._find_reachable_nodes(entry, edges, node_ids)
            unreachable = {
                nid
                for nid in (node_ids - reachable)
                if not _is_non_execution_graph_node(nodes.get(nid) or {})
            }

            if unreachable:
                result.add_error(
                    code="unreachable_nodes",
                    message=f"Недостижимые ноды от entry: {', '.join(unreachable)}",
                    severity=ValidationSeverity.WARNING,
                    details={"unreachable": list(unreachable)},
                )

        # Проверка что граф имеет выход
        execution_node_ids = {
            nid
            for nid in node_ids
            if not _is_non_execution_graph_node(nodes.get(nid) or {})
        }
        nodes_with_outgoing: set[str] = set()
        for e in edges:
            ef, _et = _edge_endpoint_ids(e)
            if ef:
                nodes_with_outgoing.add(ef)
        terminal_nodes = execution_node_ids - nodes_with_outgoing
        edges_to_null = [e for e in edges if _edge_endpoint_ids(e)[1] is None]

        if not terminal_nodes and not edges_to_null:
            result.add_error(
                code="no_exit",
                message="Граф не имеет выхода (нет терминальных нод или edges с to=null)",
                severity=ValidationSeverity.WARNING,
            )

        self._warn_fan_in_without_incoming_policy(nodes, edges, result)
        if entry and entry in node_ids:
            self._warn_cycles_reachable_from_entry(entry, edges, node_ids, result)

    def _check_reflection_exit_coverage(
        self,
        nodes: dict[str, JsonObject],
        edges: list[JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """Error, если у reflection есть исходящие, но не покрыты все exits policy."""
        for node_id, cfg in nodes.items():
            if cfg.get("type") != "reflection":
                continue
            allowed = _reflection_exit_ids(cfg)
            covered: set[str] = set()
            has_outgoing = False
            for edge in edges:
                from_node, _to_node = _edge_endpoint_ids(edge)
                if from_node != node_id:
                    continue
                has_outgoing = True
                port = edge.get("from_port")
                if isinstance(port, str) and port in allowed:
                    covered.add(port)
                    continue
                inferred = _infer_reflection_exit_port(
                    edge.get("condition"),
                    allowed_exit_ids=allowed,
                )
                if inferred is not None:
                    covered.add(inferred)
            if not has_outgoing:
                continue
            missing = sorted(allowed - covered)
            if missing:
                result.add_error(
                    code="reflection_exits_incomplete",
                    message=(
                        f"Reflection-нода '{node_id}' имеет исходящие рёбра, "
                        f"но не покрыты выходы: {', '.join(missing)}"
                    ),
                    severity=ValidationSeverity.ERROR,
                    node_id=node_id,
                    details={"missing_ports": missing, "declared_ports": sorted(allowed)},
                )

    def _warn_fan_in_without_incoming_policy(
        self,
        nodes: dict[str, JsonObject],
        edges: list[JsonObject],
        result: FlowValidationResult,
    ) -> None:
        incoming_edge_count: dict[str, int] = {}
        for edge in edges:
            from_n, to_n = _edge_endpoint_ids(edge)
            if from_n and to_n:
                incoming_edge_count[to_n] = incoming_edge_count.get(to_n, 0) + 1
        for target, edge_n in incoming_edge_count.items():
            if edge_n < 2:
                continue
            cfg = nodes.get(target) or {}
            if _is_non_execution_graph_node(cfg):
                continue
            if "incoming_policy" not in cfg:
                result.add_error(
                    code="fan_in_without_incoming_policy",
                    message=(
                        f"Нода '{target}' имеет несколько входящих веток; "
                        f"укажите incoming_policy ('any' или 'all'), иначе по умолчанию any — "
                        f"двойной запуск join-ноды между волнами возможен"
                    ),
                    severity=ValidationSeverity.WARNING,
                    node_id=target,
                )

    def _warn_cycles_reachable_from_entry(
        self,
        entry: str,
        edges: list[JsonObject],
        node_ids: set[str],
        result: FlowValidationResult,
    ) -> None:
        adj: dict[str, list[str]] = {n: [] for n in node_ids}
        for edge in edges:
            f, t = _edge_endpoint_ids(edge)
            if f in node_ids and t in node_ids:
                adj[f].append(t)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n: WHITE for n in node_ids}
        cycle_found = False

        def dfs(n: str) -> bool:
            nonlocal cycle_found
            if cycle_found:
                return True
            color[n] = GRAY
            for w in adj[n]:
                if color[w] == GRAY:
                    cycle_found = True
                    return True
                if color[w] == WHITE and dfs(w):
                    return True
            color[n] = BLACK
            return False

        if entry in color:
            _ = dfs(entry)
        if cycle_found:
            result.add_error(
                code="graph_cycle_reachable",
                message=(
                    "От entry достижим ориентированный цикл; "
                    "для AND-join помечайте back-edges contributes_to_join=false"
                ),
                severity=ValidationSeverity.WARNING,
            )

    def _validate_react_role_uniqueness(
        self,
        node_id: str,
        tools: list[JsonValue],
        result: FlowValidationResult,
    ) -> None:
        """Валидация что в llm_node только 1 reasoning и только 1 exit tool."""
        reason_tools: list[str] = []
        exit_tools: list[str] = []

        for tool in tools:
            if isinstance(tool, dict):
                react_role = tool.get("react_role")
                tool_name_value = tool.get("tool_id") or tool.get("name")
                tool_name = tool_name_value if isinstance(tool_name_value, str) else "unknown"

                if react_role == "reason":
                    reason_tools.append(tool_name)
                elif react_role == "exit":
                    exit_tools.append(tool_name)

        if len(reason_tools) > 1:
            result.add_error(
                code="duplicate_reason_tool",
                message=f"Только 1 reasoning tool разрешён, найдено {len(reason_tools)}: {reason_tools}",
                node_id=node_id,
            )

        if len(exit_tools) > 1:
            result.add_error(
                code="duplicate_exit_tool",
                message=f"Только 1 exit tool разрешён, найдено {len(exit_tools)}: {exit_tools}",
                node_id=node_id,
            )

    def _find_reachable_nodes(
        self,
        entry: str,
        edges: list[JsonObject],
        all_nodes: set[str],
    ) -> set[str]:
        """BFS для поиска достижимых нод от entry."""
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in all_nodes}

        for edge in edges:
            from_node, to_node = _edge_endpoint_ids(edge)
            if from_node and to_node and from_node in outgoing:
                outgoing[from_node].append(to_node)

        reachable: set[str] = set()
        queue = [entry]

        while queue:
            node = queue.pop(0)
            if node in reachable:
                continue
            reachable.add(node)

            for next_node in outgoing.get(node, []):
                if next_node not in reachable and next_node in all_nodes:
                    queue.append(next_node)

        return reachable

    async def _validate_references(
        self,
        nodes: dict[str, JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """Валидация ссылок на flows, tools, ноды."""
        for node_id, config in nodes.items():
            node_type = config.get("type")
            if not node_type:
                result.add_error(
                    code="missing_type",
                    message=f"Node '{node_id}' requires 'type' field",
                    node_id=node_id,
                )
                continue

            # node_id для llm_node
            if node_type == "llm_node" and "node_id" in config:
                ref_node_id = config["node_id"]
                if isinstance(ref_node_id, str) and self._resolve_node_refs:
                    node = await NodeConfig.get(NodeConfig.node_row_id_for_active_company(ref_node_id))
                    if node is None:
                        result.add_error(
                            code="node_not_found",
                            message=f"Нода '{ref_node_id}' не найдена",
                            node_id=node_id,
                        )

            # tools в llm_node
            raw_tools = config.get("tools", [])
            tools = raw_tools if isinstance(raw_tools, list) else []

            # Валидация уникальности reason/exit tools
            if node_type == "llm_node":
                self._validate_react_role_uniqueness(node_id, tools, result)
            for tool_ref in tools:
                if isinstance(tool_ref, dict):
                    # Inline tool — пропускаем проверку
                    continue
                if not isinstance(tool_ref, str) or not tool_ref:
                    result.add_error(
                        code="invalid_tool_ref",
                        message="Tool reference должен быть строкой tool_id или inline объектом tool",
                        node_id=node_id,
                    )
                    continue

                # Проверяем как tool, node или flow (flow может быть tool по ID)
                tool_exists = False
                tool = await ToolReference.get(ToolReference.row_id_for_active_company(tool_ref))
                if tool:
                    tool_exists = True

                if not tool_exists and self._resolve_node_refs:
                    node = await NodeConfig.get(NodeConfig.node_row_id_for_active_company(tool_ref))
                    if node:
                        tool_exists = True

                if not tool_exists:
                    flow_cfg = await FlowConfig.current_for_flow(tool_ref)
                    if flow_cfg:
                        tool_exists = True

                if not tool_exists:
                    result.add_error(
                        code="tool_not_found",
                        message=f"Tool/Flow '{tool_ref}' не найден",
                        node_id=node_id,
                    )

            # tool_id для type: code
            if node_type == "code":
                tool_id = config.get("tool_id")
                has_code = "code" in config

                if isinstance(tool_id, str) and tool_id and not has_code:
                    tool = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
                    if tool is None:
                        result.add_error(
                            code="tool_not_found",
                            message=f"Tool '{tool_id}' не найден",
                            node_id=node_id,
                        )

            # flow_id для ноды type: flow (вложенный flow)
            if node_type == "flow":
                ref_flow_id = config.get("flow_id")
                if isinstance(ref_flow_id, str) and ref_flow_id:
                    callee = await FlowConfig.current_for_flow(ref_flow_id)
                    if callee is None:
                        result.add_error(
                            code="flow_not_found",
                            message=f"Flow '{ref_flow_id}' не найден",
                            node_id=node_id,
                        )

            # remote_flow — только direct A2A URL (без registry flow_id)
            if node_type == "remote_flow":
                flow_id = config.get("flow_id")
                url = config.get("url")
                has_flow_id = isinstance(flow_id, str) and bool(flow_id.strip())
                has_url = isinstance(url, str) and bool(url.strip())

                if has_flow_id:
                    result.add_error(
                        code="remote_flow_registry_forbidden",
                        message=(
                            "Remote flow не поддерживает registry flow_id — "
                            "укажите прямой A2A url"
                        ),
                        node_id=node_id,
                    )
                elif not has_url:
                    result.add_error(
                        code="remote_flow_no_target",
                        message="Remote flow должен иметь url",
                        node_id=node_id,
                    )

                metadata_template = config.get("metadata_template")
                if metadata_template is not None:
                    if not isinstance(metadata_template, str):
                        result.add_error(
                            code="remote_flow_metadata_template_invalid",
                            message="remote_flow.metadata_template must be a JSON object string",
                            node_id=node_id,
                        )
                    elif metadata_template.strip():
                        try:
                            _ = parse_json_object(
                                metadata_template.strip(),
                                "remote_flow.metadata_template",
                            )
                        except ValueError as e:
                            result.add_error(
                                code="remote_flow_metadata_template_invalid",
                                message=str(e),
                                node_id=node_id,
                            )

            if node_type == "code_agent":
                metadata_template = config.get("metadata_template")
                if metadata_template is not None:
                    if not isinstance(metadata_template, str):
                        result.add_error(
                            code="code_agent_metadata_template_invalid",
                            message="code_agent.metadata_template must be a JSON object string",
                            node_id=node_id,
                        )
                    elif metadata_template.strip():
                        try:
                            _ = parse_json_object(
                                metadata_template.strip(),
                                "code_agent.metadata_template",
                            )
                        except ValueError as e:
                            result.add_error(
                                code="code_agent_metadata_template_invalid",
                                message=str(e),
                                node_id=node_id,
                            )

            if node_type == "channel":
                self._validate_channel_node(node_id, config, result)

    def _validate_channel_node(
        self,
        node_id: str,
        config: JsonObject,
        result: FlowValidationResult,
    ) -> None:
        """Валидация ChannelNode; email — delivery XOR; sms — HTTP-супербаза."""
        channel = config.get("channel")
        if channel == "email":
            self._validate_email_channel_node(node_id, config, result)
            return
        if channel == "sms":
            self._validate_sms_channel_node(node_id, config, result)
            return

    def _validate_sms_channel_node(
        self,
        node_id: str,
        config: JsonObject,
        result: FlowValidationResult,
    ) -> None:
        """SMS: url обязателен; method/timeout/body_template — типы; recipient/text не требуются."""
        raw_cfg = config.get("channel_config")
        channel_config = raw_cfg if isinstance(raw_cfg, dict) else {}
        url = channel_config.get("url")
        if not isinstance(url, str) or not url.strip():
            result.add_error(
                code="sms_channel_url_required",
                message="SMS channel требует channel_config.url",
                node_id=node_id,
            )
        method = channel_config.get("method")
        if method is not None and (not isinstance(method, str) or not method.strip()):
            result.add_error(
                code="sms_channel_method_invalid",
                message="SMS channel_config.method must be a non-empty string",
                node_id=node_id,
            )
        body_template = channel_config.get("body_template")
        if body_template is not None and not isinstance(body_template, (str, dict)):
            result.add_error(
                code="sms_channel_body_template_invalid",
                message="SMS channel_config.body_template must be a JSON string or object",
                node_id=node_id,
            )
        timeout = channel_config.get("timeout")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float))
        ):
            result.add_error(
                code="sms_channel_timeout_invalid",
                message="SMS channel_config.timeout must be a number",
                node_id=node_id,
            )

    def _validate_email_channel_node(
        self,
        node_id: str,
        config: JsonObject,
        result: FlowValidationResult,
    ) -> None:
        """Email — delivery=mailbox|smtp (XOR)."""
        raw_cfg = config.get("channel_config")
        channel_config = raw_cfg if isinstance(raw_cfg, dict) else {}
        smtp_keys = (
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "from_email",
            "password",
            "smtp_use_tls",
        )
        delivery = channel_config.get("delivery")
        if delivery not in ("mailbox", "smtp"):
            result.add_error(
                code="email_channel_delivery_required",
                message="Email channel требует channel_config.delivery = 'mailbox' | 'smtp'",
                node_id=node_id,
            )
        elif delivery == "mailbox":
            for smtp_key in smtp_keys:
                if smtp_key in channel_config:
                    result.add_error(
                        code="email_channel_mailbox_smtp_mixed",
                        message=(
                            f"Email delivery=mailbox запрещает {smtp_key!r}; "
                            "используйте delivery=smtp"
                        ),
                        node_id=node_id,
                        details={"key": smtp_key},
                    )
            binding_id = channel_config.get("mailbox_binding_id")
            if not isinstance(binding_id, str) or not binding_id.strip():
                result.add_error(
                    code="email_channel_mailbox_binding_required",
                    message="Email delivery=mailbox требует channel_config.mailbox_binding_id",
                    node_id=node_id,
                )
        else:
            if "mailbox_binding_id" in channel_config:
                result.add_error(
                    code="email_channel_smtp_mailbox_mixed",
                    message=(
                        "Email delivery=smtp запрещает mailbox_binding_id; "
                        "используйте delivery=mailbox"
                    ),
                    node_id=node_id,
                )
            for required_key in ("smtp_host", "from_email", "password"):
                value = channel_config.get(required_key)
                if not isinstance(value, str) or not value.strip():
                    result.add_error(
                        code="email_channel_smtp_field_required",
                        message=(
                            f"Email delivery=smtp требует channel_config.{required_key}"
                        ),
                        node_id=node_id,
                        details={"key": required_key},
                    )

        raw_mapping = config.get("input_mapping")
        mapping = raw_mapping if isinstance(raw_mapping, dict) else {}
        recipient = mapping.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            result.add_error(
                code="email_channel_recipient_required",
                message="Email channel требует input_mapping.recipient (Кому)",
                node_id=node_id,
            )
        text = mapping.get("text")
        if not isinstance(text, str) or not text.strip():
            result.add_error(
                code="email_channel_text_required",
                message="Email channel требует input_mapping.text (тело письма)",
                node_id=node_id,
            )
        if "subject" not in mapping:
            result.add_error(
                code="email_channel_subject_missing",
                message="Email channel: задайте input_mapping.subject (допускается пустая строка)",
                severity=ValidationSeverity.WARNING,
                node_id=node_id,
            )

    def _validate_variables(
        self,
        nodes: dict[str, JsonObject],
        variables: JsonObject,
        result: FlowValidationResult,
    ) -> None:
        """Валидация использования @var: переменных."""
        var_pattern = re.compile(r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)")

        # Извлекаем имена переменных (без value обёртки)
        available_vars: set[str] = set()
        for key in variables:
            available_vars.add(key)

        def check_var_refs(
            value: JsonValue,
            node_id: str,
            context: str,
            *,
            require_flow_variable: bool = True,
        ) -> None:
            """Рекурсивно проверяет @var: ссылки в значении."""
            if isinstance(value, str):
                for match in var_pattern.finditer(value):
                    var_name = match.group(1).split(".")[0]
                    result.var_keys_used.add(var_name)

                    if require_flow_variable and var_name not in available_vars:
                        result.add_error(
                            code="undefined_variable",
                            message=f"Переменная '@var:{var_name}' не определена в секции variables",
                            severity=ValidationSeverity.ERROR,
                            node_id=node_id,
                            details={"context": context, "variable": var_name},
                        )
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_var_refs(
                        v,
                        node_id,
                        f"{context}.{k}",
                        require_flow_variable=require_flow_variable,
                    )
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    check_var_refs(
                        v,
                        node_id,
                        f"{context}[{i}]",
                        require_flow_variable=require_flow_variable,
                    )

        for node_id, config in nodes.items():
            # input_mapping
            if "input_mapping" in config:
                check_var_refs(config["input_mapping"], node_id, "input_mapping")

            # url в remote_flow и external_api
            if "url" in config:
                check_var_refs(config["url"], node_id, "url")

            # headers (remote_flow, external_api)
            if "headers" in config:
                check_var_refs(config["headers"], node_id, "headers")

            # body_template (external_api и др.)
            if "body_template" in config:
                bt = config.get("body_template")
                if isinstance(bt, str):
                    check_var_refs(bt, node_id, "body_template")

            # metadata_template (remote_flow A2A params.metadata)
            if "metadata_template" in config:
                mt = config.get("metadata_template")
                if isinstance(mt, str):
                    check_var_refs(mt, node_id, "metadata_template")

        # Проверяем значения переменных flow на @var: ссылки
        for var_key, var_value in variables.items():
            if isinstance(var_value, dict) and "value" in var_value:
                # FlowVariableConfig.value может быть ссылкой на company variable.
                # Такие @var:* должны попадать в var_keys_used, но не обязаны быть
                # объявлены в этой же flow variables секции.
                check_var_refs(
                    var_value["value"],
                    "variables",
                    f"variables.{var_key}.value",
                    require_flow_variable=False,
                )
            elif isinstance(var_value, str):
                # Простой строковый формат также используется как flow variable value.
                check_var_refs(
                    var_value,
                    "variables",
                    f"variables.{var_key}",
                    require_flow_variable=False,
                )

    def _validate_messages_filters(
        self,
        nodes: dict[str, JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """Список messages_filter у llm_node должен ссылаться только на node_id из этого графа."""
        node_ids = set(nodes.keys())
        for nid, cfg in nodes.items():
            if cfg.get("type") != "llm_node":
                continue
            mf = cfg.get("messages_filter", "all")
            if not isinstance(mf, list):
                continue
            for ref in mf:
                if not isinstance(ref, str):
                    result.add_error(
                        code="messages_filter_invalid_node",
                        message=f"Нода '{nid}': messages_filter должен содержать только строки node_id",
                        node_id=nid,
                        details={"messages_filter": mf},
                    )
                    continue
                referenced_node_id = extract_resource_id(ref)
                if referenced_node_id not in node_ids:
                    result.add_error(
                        code="messages_filter_unknown_node",
                        message=(
                            f"Нода '{nid}': messages_filter содержит неизвестный node_id '{referenced_node_id}'"
                        ),
                        node_id=nid,
                        details={"messages_filter": mf, "unknown": referenced_node_id},
                    )

    def _validate_node_files(
        self,
        nodes: dict[str, JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """Поле files: список объектов с непустыми строками original_name и url."""
        for node_id, cfg in nodes.items():
            if "files" not in cfg:
                continue
            raw = cfg.get("files")
            if raw is None or raw == []:
                continue
            try:
                validate_node_files_list(raw, node_id=node_id)
            except ValueError as exc:
                result.add_error(
                    code="invalid_node_files",
                    message=str(exc),
                    node_id=node_id,
                )

    def _validate_hitl_nodes(
        self,
        nodes: dict[str, JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """hitl_node: задан источник очереди (work_queue_slug или input_mapping.assignee_queue)."""
        for nid, cfg in nodes.items():
            if cfg.get("type") != "hitl_node":
                continue
            slug = cfg.get("work_queue_slug")
            has_slug = isinstance(slug, str) and bool(slug.strip())
            im = cfg.get("input_mapping")
            assignee_queue = im.get("assignee_queue") if isinstance(im, dict) else None
            has_im_queue = (
                isinstance(im, dict)
                and isinstance(assignee_queue, str)
                and bool(assignee_queue.strip())
            )
            if not has_slug and not has_im_queue:
                result.add_error(
                    code="hitl_queue_source",
                    message=(
                        f"Нода '{nid}' (hitl_node): укажите work_queue_slug "
                        "или input_mapping.assignee_queue"
                    ),
                    node_id=nid,
                )

    def _parse_inline_code(
        self,
        nodes: dict[str, JsonObject],
        result: FlowValidationResult,
    ) -> None:
        """Парсит inline code и извлекает обращения к state."""
        # Паттерны для обращений к state
        patterns = [
            re.compile(r"state\[(['\"])(\w+)\1\]"),  # state['key'] или state["key"]
            re.compile(r"state\.get\((['\"])(\w+)\1"),  # state.get('key')
        ]

        for node_id, config in nodes.items():
            code = config.get("code")
            if not isinstance(code, str) or not code:
                continue

            state_keys: set[str] = set()

            for pattern in patterns:
                for match in pattern.finditer(code):
                    key = match.group(2)
                    state_keys.add(key)

            if state_keys:
                result.state_keys_used.update(state_keys)
                result.add_error(
                    code="inline_code_state_keys",
                    message=f"Inline code использует state ключи: {', '.join(sorted(state_keys))}",
                    severity=ValidationSeverity.INFO,
                    node_id=node_id,
                    details={"state_keys": list(state_keys)},
                )

    async def _try_build(
        self,
        nodes: dict[str, JsonObject],
        edges: list[JsonObject],
        entry: str,
        flow_id: str | None,
        result: FlowValidationResult,
    ) -> None:
        """Попытка собрать Flow из конфигурации."""
        if self.flow_builder is None:
            return
        try:
            # Сборка проверяет граф; документ интерфейса валидируется отдельно при сохранении.
            config: JsonObject = {
                "flow_id": flow_id or "validation_test",
                "name": "Validation Test",
                "entry": entry,
                "nodes": nodes,
                "edges": edges,
                "interface": default_chat_document().model_dump(mode="json"),
            }

            _ = await self.flow_builder(config)

        except Exception as e:
            result.add_error(
                code="build_failed",
                message=f"Ошибка сборки Flow: {str(e)}",
                details={"exception": type(e).__name__},
            )
