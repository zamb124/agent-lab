"""op_* Sync зовут сервис, а не модели; handlers не держат отправку и запись звонка."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report

_OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
_HANDLERS = REPO_ROOT / "apps" / "sync" / "realtime" / "handlers.py"
_MESSAGE_SERVICE = REPO_ROOT / "apps" / "sync" / "services" / "message_service.py"
_RECORDING_SERVICE = REPO_ROOT / "apps" / "sync" / "services" / "recording_service.py"


@dataclass(frozen=True)
class OpBodySpec:
    label: str
    service_attr: str
    forbidden: tuple[str, ...]
    names: tuple[str, ...] = ()
    prefix: str = ""
    word: bool = False


_SPECS: tuple[OpBodySpec, ...] = (
    OpBodySpec(
        "channel ops",
        "channel_service",
        ("SyncChannel", "SyncChannelMember", "SyncMessage", "SyncThread"),
        prefix="op_channels_",
    ),
    OpBodySpec(
        "message ops",
        "message_service",
        ("SyncMessage", "SyncMessageContent", "SyncThread", "SyncChannel", "SyncCall"),
        prefix="op_messages_",
    ),
    OpBodySpec(
        "link ops",
        "call_link_service",
        ("SyncCallLink", "SyncCall", "SyncChannel", "livekit_client"),
        names=(
            "op_calls_links_list",
            "op_calls_links_create",
            "op_calls_links_update",
            "op_calls_links_remove",
            "op_calls_join_info",
            "op_calls_join_accept",
        ),
    ),
    OpBodySpec(
        "lifecycle ops",
        "call_service",
        ("handle_call_", "SyncCall", "SyncChannel", "maybe_start_speech_to_chat_poll"),
        names=("op_calls_invite", "op_calls_accept", "op_calls_decline", "op_calls_hangup"),
    ),
    OpBodySpec(
        "session ops",
        "call_service",
        ("SyncCall", "SyncCallParticipant", "SyncCallRecording", "AuthzObject"),
        names=(
            "op_calls_get",
            "op_calls_recordings_list",
            "op_calls_token",
            "op_calls_turn_credentials",
            "op_calls_admin_transfer",
            "op_calls_signal",
        ),
    ),
    OpBodySpec(
        "recording ops",
        "call_recording_service",
        ("SyncCallRecording", "build_livekit_recording_client", "stop_and_finalize_recording"),
        names=("op_calls_recording_start", "op_calls_recording_stop"),
    ),
    OpBodySpec(
        "directory ops",
        "channel_service",
        ("Company", "SyncChannel", "SyncMessage", "User.get"),
        names=("op_company_members_list", "op_company_shared_channels_list"),
        word=True,
    ),
    OpBodySpec(
        "file upload",
        "files_service",
        ("FileRecord", "stored_file_ref"),
        names=("op_files_upload_completed",),
        word=True,
    ),
    OpBodySpec(
        "thread ops",
        "thread_service",
        ("SyncThread", "SyncMessage"),
        prefix="op_threads_",
        word=True,
    ),
    OpBodySpec(
        "git ops",
        "git_service",
        ("GitResourceRef",),
        prefix="op_git_resources_",
        word=True,
    ),
)

_RECORDING_HANDLER_FORBIDDEN = frozenset(
    {
        "stop_and_finalize_recording",
        "build_livekit_recording_client",
        "normalize_s3_egress_endpoint",
    }
)
_THREAD_HANDLER_FORBIDDEN = frozenset({"create_thread", "upsert_git_resource"})
_MESSAGE_SEND_FORBIDDEN = frozenset({"send_message", "send_message_with_side_effects"})


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _forbidden_in_source(name: str, source: str, *, word: bool) -> bool:
    if word:
        return re.search(rf"\b{re.escape(name)}\b", source) is not None
    return name in source


def _matches(spec: OpBodySpec, name: str) -> bool:
    if spec.prefix:
        return name.startswith(spec.prefix)
    return name in spec.names


def _scan_operations(source_text: str, tree: ast.Module) -> list[str]:
    errors: list[str] = []
    for spec in _SPECS:
        found = 0
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef) or not _matches(spec, node.name):
                continue
            found += 1
            source = ast.get_source_segment(source_text, node)
            if source is None:
                errors.append(f"{node.name}: source missing")
                continue
            if spec.service_attr not in source:
                errors.append(f"{node.name}: must call {spec.service_attr}")
            for name in spec.forbidden:
                if _forbidden_in_source(name, source, word=spec.word):
                    errors.append(f"{node.name}: {name} belongs in the service")
        expected = len(spec.names) if spec.names else 1
        if spec.names and found != expected:
            errors.append(f"{spec.label}: expected {expected}, found {found}")
        elif spec.prefix and found == 0:
            errors.append(f"{spec.prefix}*: no operations found")
    return errors


def _scan_handlers(handler_names: set[str]) -> list[str]:
    errors: list[str] = []
    for name in sorted(_RECORDING_HANDLER_FORBIDDEN & handler_names):
        errors.append(f"handlers.py: {name} belongs in SyncCallRecordingService")
    for name in sorted(_THREAD_HANDLER_FORBIDDEN & handler_names):
        errors.append(f"handlers.py: {name} belongs in a service")
    for name in sorted(_MESSAGE_SEND_FORBIDDEN & handler_names):
        errors.append(f"handlers.py: {name} belongs in SyncMessageService")
    return errors


def collect_errors() -> list[str]:
    source_text = _OPERATIONS.read_text(encoding="utf-8")
    errors = _scan_operations(source_text, ast.parse(source_text))
    if not _RECORDING_SERVICE.is_file():
        errors.append("apps/sync/services/recording_service.py: missing")
    if not _MESSAGE_SERVICE.is_file():
        errors.append("apps/sync/services/message_service.py: missing")
    elif missing := _MESSAGE_SEND_FORBIDDEN - _function_names(_MESSAGE_SERVICE):
        for name in sorted(missing):
            errors.append(f"message_service.py: missing {name}")
    if not _HANDLERS.is_file():
        errors.append("apps/sync/realtime/handlers.py: missing")
        return errors
    errors.extend(_scan_handlers(_function_names(_HANDLERS)))
    return errors


def main() -> int:
    return report("op_adapters", collect_errors())


if __name__ == "__main__":
    raise SystemExit(main())
