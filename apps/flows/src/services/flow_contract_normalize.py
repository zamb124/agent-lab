"""
Нормализация JSON flow / node / tool под контракт без легаси type нод tool|function и tool_type.

FlowRepository вызывает normalize_flow_config_dict перед FlowConfig.model_validate.

Легаси в том же смысле, что ревизия ``agents_0005``: при чтении из БД ключ ``skills``
переносится в ``branches``, в evaluation ``skill_ids`` → ``branch_ids`` (in-memory;
персистентная правка строк — по-прежнему через ``alembic upgrade``).
"""

from __future__ import annotations

import copy
import importlib
import inspect
from collections.abc import Mapping, MutableMapping
from typing import Any

from apps.flows.src.models.enums import ReactToolRole
from core.logging import get_logger

logger = get_logger(__name__)


def _inline_function_path(node: MutableMapping[str, Any], context: str) -> None:
    function_path = node.get("function")
    if not function_path or node.get("code"):
        return
    module_path, func_name = function_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    node["code"] = inspect.getsource(func)
    del node["function"]
    logger.debug("Node '%s': inlined code from %s", context, function_path)


def normalize_tool_entry(entry: Any) -> Any:
    if not isinstance(entry, dict):
        return entry
    out: dict[str, Any] = copy.deepcopy(entry)
    if "tool_type" in out:
        legacy = out.pop("tool_type")
        if legacy == "tool":
            out["react_role"] = ReactToolRole.STANDARD.value
        elif legacy in ("reason", "exit"):
            out["react_role"] = legacy
        else:
            out["react_role"] = ReactToolRole.STANDARD.value
    ty = out.get("type")
    if ty in ("tool", "function"):
        if out.get("prompt"):
            out["type"] = "llm_node"
        else:
            out["type"] = "code"
    return out


def _merge_legacy_auth_headers_into_headers(target: MutableMapping[str, Any]) -> None:
    """Легаси: auth_headers отдельно от headers; при чтении слить (как бывший порядок в клиенте)."""
    if "auth_headers" not in target:
        return
    legacy = target.get("auth_headers")
    if legacy is None or legacy == {}:
        target.pop("auth_headers", None)
        return
    if not isinstance(legacy, dict):
        raise ValueError("auth_headers must be a dict when present")
    base = target.get("headers")
    if not isinstance(base, dict):
        base = {}
    target["headers"] = {**base, **legacy}
    target.pop("auth_headers", None)


def _migrate_external_api_legacy_parameters(node: MutableMapping[str, Any]) -> None:
    """
    Легаси external_api.parameters (path/query/header): при чтении удалить.

    После этого: ключи строковых default для location header мержятся первыми в headers,
    существующие ключи headers не перезаписываются.
    """
    raw = node.get("parameters")
    if raw is None:
        return
    if not isinstance(raw, list):
        node.pop("parameters", None)
        return
    base = node.get("headers")
    if not isinstance(base, dict):
        base = {}
    migration: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get("location") != "header":
            continue
        pname = entry.get("name")
        default_val = entry.get("default")
        if isinstance(pname, str) and pname and isinstance(default_val, str):
            migration[pname] = default_val
    node["headers"] = {**migration, **base}
    node.pop("parameters", None)


def normalize_node_config(node: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(copy.deepcopy(node))
    nid = str(out.get("node_id", "?"))
    nt = out.get("type")
    if nt in ("tool", "function"):
        out["type"] = "code"
    if out.get("function") and not out.get("code"):
        _inline_function_path(out, nid)
    tools = out.get("tools")
    if isinstance(tools, list):
        out["tools"] = [normalize_tool_entry(t) for t in tools]
    if nt in ("external_api", "remote_flow"):
        _merge_legacy_auth_headers_into_headers(out)
    if nt == "external_api":
        _migrate_external_api_legacy_parameters(out)
    return out


def _evaluation_function_type_to_modern(part: MutableMapping[str, Any], role: str) -> None:
    """
    Легаси evaluation: type=function. Сейчас: inline_code (исходник) или string (путь к checker в модуле).
    """
    value = part.get("value", "")
    if isinstance(value, str):
        stripped = value.strip()
        looks_like_source = (
            "\n" in stripped
            or stripped.startswith(("def ", "async def"))
            or " def " in stripped
            or "async def " in stripped
        )
        if not looks_like_source and role == "check":
            path_parts = stripped.split(".")
            if len(path_parts) >= 2 and all(p.isidentifier() for p in path_parts):
                part["type"] = "string"
                return
    part["type"] = "inline_code"


def _normalize_evaluation_turn(turn: MutableMapping[str, Any]) -> None:
    for key in ("input", "check"):
        part = turn.get(key)
        if isinstance(part, dict) and part.get("type") == "function":
            _evaluation_function_type_to_modern(part, key)


def _normalize_evaluation(evaluation: Any) -> None:
    if not isinstance(evaluation, dict):
        return
    for case_id, case in evaluation.items():
        if not isinstance(case, dict):
            continue
        if "skill_ids" in case:
            if "branch_ids" in case:
                raise ValueError(
                    f"evaluation['{case_id}']: в одном кейсе одновременно skill_ids и branch_ids"
                )
            case["branch_ids"] = case.pop("skill_ids")
        turns = case.get("turns")
        if isinstance(turns, list):
            for turn in turns:
                if isinstance(turn, dict):
                    _normalize_evaluation_turn(turn)


def _migrate_legacy_skills_to_branches(out: MutableMapping[str, Any]) -> None:
    if "skills" not in out:
        return
    legacy = out.pop("skills")
    if not isinstance(legacy, dict) or len(legacy) == 0:
        return
    existing = out.get("branches")
    has_branches = isinstance(existing, dict) and len(existing) > 0
    if has_branches:
        raise ValueError("flow: одновременно branches и skills")
    out["branches"] = legacy


def normalize_flow_config_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(copy.deepcopy(data))
    nodes = out.get("nodes")
    if isinstance(nodes, dict):
        out["nodes"] = {k: normalize_node_config(v) for k, v in nodes.items()}
    _migrate_legacy_skills_to_branches(out)
    ev = out.get("evaluation")
    if ev is not None:
        _normalize_evaluation(ev)
    if "auth_headers" in out:
        _merge_legacy_auth_headers_into_headers(out)
    return out


def normalize_tool_library_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(copy.deepcopy(data))
    if "tool_type" in out:
        legacy = out.pop("tool_type")
        if legacy == "tool":
            out["react_role"] = ReactToolRole.STANDARD.value
        elif legacy in ("reason", "exit"):
            out["react_role"] = legacy
        else:
            out["react_role"] = ReactToolRole.STANDARD.value
    if out.get("type") in ("tool", "function"):
        out.pop("type", None)
    return out
