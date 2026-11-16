"""Команды `platform`. Транспорт — REST и A2A, без Centrifugo."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import sys
import time
import uuid
from base64 import b64encode
from pathlib import Path

import jsonschema
import yaml
from pydantic import TypeAdapter, ValidationError

from platform_sdk.bundle import SCHEMA_COMMENT, assemble_bundle, layout_bundle
from platform_sdk.context_store import (
    PlatformContext,
    list_contexts,
    save_context,
    use_context,
)
from platform_sdk.errors import (
    EXIT_EVAL_FAILED,
    EXIT_INPUT_REQUIRED,
    EXIT_INVALID,
    EXIT_OK,
    EXIT_RUN_FAILED,
    PlatformCliError,
    a2a_error,
    parse,
    usage_error,
)
from platform_sdk.files_api import upload_file
from platform_sdk.http import PlatformClient
from platform_sdk.json_types import JsonObject, JsonValue, as_json, as_list, require_object
from platform_sdk.output import emit, emit_line, json_mode
from platform_sdk.project import (
    publish_body,
    read_flow_schema,
    read_lock,
    write_lock,
    write_schema_cache,
)
from platform_sdk.wire import (
    A2AFrame,
    CaseLine,
    DocumentStatus,
    EvalEventPage,
    ExecutionStateView,
    FileRef,
    FlowIdentity,
    HistoryView,
    IdPage,
    IdRow,
    IndexAccepted,
    LockFile,
    LogsView,
    NamedRecord,
    RecordPage,
    RubricCreated,
    RunEnvelope,
    SuiteCreated,
    SuiteFile,
    ValidateResult,
    Versioned,
)

_INPUT = {"TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}
_GUIDE = Path(__file__).resolve().parent / "guide" / "SKILL.md"


async def cmd_login(host: str, api_key: str, name: str) -> int:
    context = PlatformContext(
        name=name,
        host=host if host.startswith("http") else f"https://{host}",
        api_key=api_key,
        company_subdomain=host.split("//")[-1].split("/")[0].split(".")[0],
    )
    path = save_context(context, make_current=True)
    emit({"context": context.name, "host": context.host, "path": str(path)})
    return EXIT_OK


def cmd_context_list() -> int:
    current, names = list_contexts()
    emit({"current": current, "contexts": names})
    return EXIT_OK


def cmd_context_use(name: str) -> int:
    use_context(name)
    emit({"current": name})
    return EXIT_OK


async def cmd_whoami(client: PlatformClient) -> int:
    me = await client.request("GET", "/frontend/api/auth/me", retry=True)
    emit({"host": client.context.host, "context": client.context.name, "user": me})
    return EXIT_OK


def cmd_guide() -> int:
    sys.stdout.write(_GUIDE.read_text(encoding="utf-8"))
    return EXIT_OK


def cmd_init(directory: Path, flow_id: str, name: str) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    flow = {
        "flow_id": flow_id,
        "name": name,
        "description": "",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "name": "main",
                "prompt": "prompts/main.md",
                "tools": [],
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }
    (directory / "prompts").mkdir(exist_ok=True)
    (directory / "prompts" / "main.md").write_text(
        "You are a helpful assistant.\n", encoding="utf-8"
    )
    (directory / "evals").mkdir(exist_ok=True)
    (directory / "evals" / "suite.yaml").write_text(
        "name: default\ndescription: ''\nrubrics: []\n",
        encoding="utf-8",
    )
    (directory / "evals" / "cases.jsonl").write_text("", encoding="utf-8")
    text = yaml.safe_dump(flow, sort_keys=False, allow_unicode=True)
    (directory / "flow.yaml").write_text(SCHEMA_COMMENT + text, encoding="utf-8")
    (directory / "AGENTS.md").write_text(
        "# Агент\n\n"
        "Источник правды — этот каталог. Цикл: правка, `platform validate`, "
        "`platform push`, `platform run`, `platform sessions inspect`, `platform eval run --wait`.\n\n"
        "Схема полей — `.platform/schema` после `platform schema pull`. "
        "Секреты в bundle не хранятся: только `@var:`, значения — `platform vars set`.\n\n"
        "Полный контракт CLI: `platform guide`.\n",
        encoding="utf-8",
    )
    emit({"flow_id": flow_id, "path": str(directory)})
    return EXIT_OK


async def cmd_schema_pull(client: PlatformClient, directory: Path) -> int:
    schema = require_object(
        await client.request("GET", "/flows/api/v1/schema", retry=True), "schema"
    )
    write_schema_cache(directory, schema)
    emit({"path": str(directory / ".platform" / "schema"), "schemas": sorted(schema)})
    return EXIT_OK


async def cmd_explain(client: PlatformClient, topic: str, name: str | None) -> int:
    if topic == "node-types":
        payload = await client.request("GET", "/flows/api/v1/metadata/node-types", retry=True)
    elif topic == "node":
        if name is None:
            raise usage_error("explain node requires a node type")
        cards = await client.request("GET", "/flows/api/v1/metadata/node-types", retry=True)
        payload = _find_named(cards, name, "type")
    elif topic == "tools":
        payload = await client.request(
            "GET", "/flows/api/v1/tools/all", params={"limit": 200}, retry=True
        )
    elif topic == "tool":
        if name is None:
            raise usage_error("explain tool requires a tool_id")
        payload = await client.request("GET", f"/flows/api/v1/tools/{name}/contract", retry=True)
    elif topic == "models":
        payload = await client.request("GET", "/flows/api/v1/registry/models/values", retry=True)
    elif topic == "resource-types":
        payload = await client.request("GET", "/flows/api/v1/metadata/resource-types", retry=True)
    elif topic == "flow-ui":
        payload = await client.request("GET", "/flows/api/v1/flow-ui/schema", retry=True)
    elif topic == "events":
        payload = await client.request("GET", "/flows/api/v1/platform-events/catalog", retry=True)
    else:
        raise usage_error(f"Unknown explain topic {topic}")
    emit(payload)
    return EXIT_OK


async def cmd_flows_list(client: PlatformClient) -> int:
    emit(await client.request("GET", "/flows/api/v1/flows", params={"limit": 200}, retry=True))
    return EXIT_OK


async def cmd_pull(client: PlatformClient, directory: Path, flow_id: str) -> int:
    flow = require_object(
        await client.request("GET", f"/flows/api/v1/flows/{flow_id}", retry=True),
        "flow",
    )
    layout_bundle(directory, flow)
    version = parse(Versioned, flow, "flow").version
    write_lock(
        directory,
        {
            "context": client.context.name,
            "company_subdomain": client.context.company_subdomain,
            "flow_id": flow_id,
            "base_version": version,
        },
    )
    emit({"flow_id": flow_id, "base_version": version, "path": str(directory)})
    return EXIT_OK


async def cmd_diff(client: PlatformClient, directory: Path) -> int:
    local = assemble_bundle(directory)
    flow_id = parse(FlowIdentity, local, "flow").flow_id
    remote = require_object(
        await client.request("GET", f"/flows/api/v1/flows/{flow_id}", retry=True),
        "flow",
    )
    emit({"flow_id": flow_id, "changes": _diff(local, remote, "flow")})
    return EXIT_OK


async def cmd_validate(client: PlatformClient, directory: Path) -> int:
    body = publish_body(directory, base_version=None)
    schema = read_flow_schema(directory)
    local_errors: list[JsonValue] = []
    if schema is None:
        emit_line(
            "No .platform/schema/flow.schema.json. Run platform schema pull for local checks."
        )
    else:
        validator = jsonschema.Draft202012Validator(schema)
        local_errors = [
            {"path": list(error.path), "message": error.message}
            for error in validator.iter_errors(body)
        ]
    remote_body = dict(body)
    remote_body.pop("flow_id", None)
    remote = parse(
        ValidateResult,
        await client.request("POST", "/flows/api/v1/flows/validate", json_body=remote_body),
        "validate",
    )
    valid = remote.valid and len(local_errors) == 0
    emit({"valid": valid, "local_errors": local_errors, "errors": remote.errors})
    if not valid:
        raise PlatformCliError(
            error_code="flow_invalid",
            error_detail="Flow validation failed",
            exit_code=3,
            error_params={"local_errors": local_errors, "errors": remote.errors},
        )
    return EXIT_OK


async def cmd_push(client: PlatformClient, directory: Path, *, force_base: bool) -> int:
    lock = read_lock(directory) if (directory / ".platform" / "lock.json").is_file() else {}
    flow_id = parse(FlowIdentity, assemble_bundle(directory), "flow").flow_id
    existing: JsonValue | None
    created = False
    try:
        existing = await client.request("GET", f"/flows/api/v1/flows/{flow_id}", retry=True)
    except PlatformCliError as exc:
        if exc.http_status not in {403, 404}:
            raise
        existing = None
        created = True
    base_version: str | None
    if created:
        base_version = None
    elif force_base:
        base_version = parse(Versioned, existing, "flow").version
    else:
        locked = parse(LockFile, lock, "lock").base_version
        if locked == "":
            raise usage_error("lock has no base_version. platform pull, or push --force-base")
        base_version = locked
    body = publish_body(directory, base_version=base_version)
    if created:
        saved = require_object(
            await client.request("POST", "/flows/api/v1/flows", json_body=body),
            "create",
        )
    else:
        saved = require_object(
            await client.request("PUT", f"/flows/api/v1/flows/{flow_id}", json_body=body),
            "update",
        )
    version = parse(Versioned, saved, "flow").version
    write_lock(
        directory,
        {
            "context": client.context.name,
            "company_subdomain": client.context.company_subdomain,
            "flow_id": flow_id,
            "base_version": version,
        },
    )
    emit({"flow_id": flow_id, "version": version, "created": created})
    return EXIT_OK


async def cmd_versions(client: PlatformClient, flow_id: str) -> int:
    emit(await client.request("GET", f"/flows/api/v1/flows/{flow_id}/versions", retry=True))
    return EXIT_OK


async def cmd_rollback(client: PlatformClient, directory: Path, flow_id: str, version: str) -> int:
    saved = require_object(
        await client.request("POST", f"/flows/api/v1/flows/{flow_id}/versions/{version}/rollback"),
        "rollback",
    )
    current = require_object(
        await client.request("GET", f"/flows/api/v1/flows/{flow_id}", retry=True),
        "flow",
    )
    if directory.is_dir() and (directory / "flow.yaml").is_file():
        layout_bundle(directory, current)
        write_lock(
            directory,
            {
                "context": client.context.name,
                "company_subdomain": client.context.company_subdomain,
                "flow_id": flow_id,
                "base_version": parse(Versioned, current, "flow").version,
            },
        )
    emit(saved)
    return EXIT_OK


async def cmd_remove(client: PlatformClient, flow_id: str) -> int:
    emit(await client.request("DELETE", f"/flows/api/v1/flows/{flow_id}"))
    return EXIT_OK


async def cmd_vars_list(client: PlatformClient) -> int:
    emit(
        await client.request("GET", "/secrets/api/v1/variables", params={"limit": 200}, retry=True)
    )
    return EXIT_OK


async def cmd_vars_set(client: PlatformClient, key: str, value: str, *, secret: bool) -> int:
    saved = await client.request(
        "POST",
        "/secrets/api/v1/variables",
        json_body={
            "variable_key": key,
            "secret": secret,
            "payload": {"base": {"value_kind": "static", "value": value}},
        },
    )
    emit(saved)
    return EXIT_OK


async def cmd_run(
    client: PlatformClient,
    *,
    flow_id: str,
    text: str,
    branch: str | None,
    variables: dict[str, str],
    files: list[Path],
    context_id: str | None,
    breakpoints: list[str],
    detach: bool,
) -> int:
    context = context_id if context_id is not None and context_id != "" else str(uuid.uuid4())
    metadata: JsonObject = {}
    if branch is not None and branch != "":
        metadata["branch"] = branch
    if variables:
        metadata["variables"] = require_object(variables, "variables")
    if breakpoints:
        metadata["breakpoints"] = require_object(
            {node_id: True for node_id in breakpoints},
            "breakpoints",
        )
    parts: list[JsonObject] = [{"text": text}]
    for path in files:
        mime = mimetypes.guess_type(path.name)[0]
        parts.append(
            {
                "raw": b64encode(path.read_bytes()).decode("ascii"),
                "filename": path.name,
                "mediaType": mime if mime is not None else "application/octet-stream",
            }
        )
    params = require_object(
        {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "contextId": context,
                "parts": parts,
            },
            "metadata": metadata,
            "configuration": {"returnImmediately": detach},
        },
        "a2a",
    )
    if detach:
        body = require_object(
            await client.request(
                "POST",
                f"/flows/api/v1/{flow_id}",
                json_body={"jsonrpc": "2.0", "id": "1", "method": "SendMessage", "params": params},
                headers={"A2A-Version": "1.0"},
            ),
            "a2a",
        )
        if "error" in body:
            raise a2a_error(body)
        emit(body.get("result"))
        return EXIT_OK
    return await _consume_stream(
        client,
        flow_id,
        method="SendStreamingMessage",
        params=params,
        context_id=context,
    )


async def cmd_wait(client: PlatformClient, flow_id: str, task_id: str) -> int:
    return await _consume_stream(
        client,
        flow_id,
        method="SubscribeToTask",
        params={"id": task_id},
        context_id="",
    )


async def cmd_sessions_list(client: PlatformClient, flow_id: str | None) -> int:
    params: dict[str, str | int] = {"limit": 50}
    if flow_id is not None:
        params["flow_id"] = flow_id
    emit(await client.request("GET", "/flows/api/v1/sessions/", params=params, retry=True))
    return EXIT_OK


async def cmd_sessions_inspect(client: PlatformClient, session_id: str) -> int:
    emit(await _session_bundle(client, session_id))
    return EXIT_OK


async def cmd_sessions_export(client: PlatformClient, session_id: str, output: Path) -> int:
    bundle = await _session_bundle(client, session_id)
    output.mkdir(parents=True, exist_ok=True)
    (output / "state.json").write_text(
        json.dumps(bundle["state"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "trace.json").write_text(
        json.dumps(bundle["trace"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(output / "events.jsonl", bundle["events"])
    _write_jsonl(output / "logs.jsonl", bundle["logs"])
    emit({"session_id": session_id, "path": str(output)})
    return EXIT_OK


async def cmd_state_at(client: PlatformClient, session_id: str, sequence: int) -> int:
    emit(
        await client.request(
            "GET",
            f"/flows/api/v1/tasks/{session_id}/state-at/{sequence}",
            retry=True,
        )
    )
    return EXIT_OK


async def cmd_session_action(
    client: PlatformClient,
    session_id: str,
    action: str,
    sequence: int | None,
) -> int:
    body: JsonObject = {}
    if action in {"fork", "rewind"}:
        if sequence is None:
            raise usage_error(f"{action} requires --sequence")
        body["sequence"] = sequence
    if action == "retry" and sequence is not None:
        body["failed_sequence"] = sequence
    emit(await client.request("POST", f"/flows/api/v1/tasks/{session_id}/{action}", json_body=body))
    return EXIT_OK


async def cmd_trace(client: PlatformClient, ref: str) -> int:
    if ":" in ref:
        payload = await client.request("GET", f"/flows/api/v1/traces/session/{ref}", retry=True)
    else:
        payload = await client.request("GET", f"/flows/api/v1/traces/task/{ref}", retry=True)
    emit(payload)
    return EXIT_OK


async def cmd_logs(client: PlatformClient, session_id: str) -> int:
    emit(
        await client.request(
            "GET",
            f"/flows/api/v1/observability/logs/by-session/{session_id}",
            retry=True,
        )
    )
    return EXIT_OK


async def cmd_eval_push(client: PlatformClient, directory: Path) -> int:
    flow = assemble_bundle(directory)
    flow_id = parse(FlowIdentity, flow, "flow").flow_id
    suite_path = directory / "evals" / "suite.yaml"
    if not suite_path.is_file():
        raise usage_error(f"Missing {suite_path}")
    suite_doc = parse(SuiteFile, _load_yaml(suite_path), "suite")
    suites = parse(
        IdPage,
        await client.request(
            "GET",
            "/flows/api/v1/evaluation/suites",
            params={"flow_id": flow_id},
            retry=True,
        ),
        "suites",
    )
    suite_id = _id_by_name(suites.items, suite_doc.name, "suite_id")
    if suite_id is None:
        created = parse(
            SuiteCreated,
            await client.request(
                "POST",
                "/flows/api/v1/evaluation/suites",
                json_body={
                    "flow_id": flow_id,
                    "name": suite_doc.name,
                    "description": suite_doc.description,
                    "tags": suite_doc.tags,
                },
            ),
            "suite",
        )
        suite_id = created.suite_id
    rubric_ids: list[JsonValue] = []
    if suite_doc.rubrics:
        existing = parse(
            IdPage,
            await client.request(
                "GET",
                "/flows/api/v1/evaluation/rubrics",
                params={"flow_id": flow_id},
                retry=True,
            ),
            "rubrics",
        )
        for rubric in suite_doc.rubrics:
            found = _id_by_name(existing.items, rubric.name, "rubric_id")
            if found is None:
                made = parse(
                    RubricCreated,
                    await client.request(
                        "POST",
                        "/flows/api/v1/evaluation/rubrics",
                        json_body={
                            "flow_id": flow_id,
                            "name": rubric.name,
                            "prompt": rubric.prompt,
                            "pass_threshold": rubric.pass_threshold,
                        },
                    ),
                    "rubric",
                )
                found = made.resolved_id()
                if found == "":
                    raise PlatformCliError(
                        error_code="ws_invalid_payload",
                        error_detail="rubric_id must be a non-empty string",
                        exit_code=EXIT_INVALID,
                    )
            else:
                await client.request(
                    "POST",
                    f"/flows/api/v1/evaluation/rubrics/{found}/versions",
                    json_body={"prompt": rubric.prompt, "pass_threshold": rubric.pass_threshold},
                )
            rubric_ids.append(found)
    cases_path = directory / "evals" / "cases.jsonl"
    imported: JsonValue = {"cases": []}
    if cases_path.is_file() and cases_path.stat().st_size > 0:
        lines = _prepare_cases(directory, cases_path)
        if lines != "":
            imported = await client.request(
                "POST",
                f"/flows/api/v1/evaluation/suites/{suite_id}/cases/import",
                json_body={"format": "jsonl", "content": lines},
            )
    emit({"suite_id": suite_id, "rubric_ids": rubric_ids, "import": imported})
    return EXIT_OK


async def cmd_eval_run(
    client: PlatformClient,
    *,
    suite_id: str,
    branch_id: str,
    trials: int,
    wait: bool,
    timeout: float,
) -> int:
    created = await client.request(
        "POST",
        "/flows/api/v1/evaluation/runs",
        json_body={
            "suite_id": suite_id,
            "branch_id": branch_id,
            "scope": {"type": "suite"},
            "trials": trials,
            "idempotency_key": str(uuid.uuid4()),
        },
        retry=True,
    )
    run = parse(RunEnvelope, created, "run").resolved()
    if run.run_id == "":
        raise PlatformCliError(
            error_code="ws_invalid_payload",
            error_detail="run_id must be a non-empty string",
            exit_code=EXIT_INVALID,
        )
    run_id = run.run_id
    if not wait:
        emit(created)
        return EXIT_OK
    state = await _poll_run(client, run_id, timeout)
    emit(state)
    terminal = _run_state(state)
    if terminal in {"failed", "error"}:
        raise PlatformCliError(
            error_code="evaluation_failed",
            error_detail=f"Evaluation run {run_id} {terminal}",
            exit_code=EXIT_EVAL_FAILED,
            error_params={"run_id": run_id, "state": terminal},
        )
    if terminal == "canceled":
        raise PlatformCliError(
            error_code="evaluation_canceled",
            error_detail=f"Evaluation run {run_id} canceled",
            exit_code=EXIT_RUN_FAILED,
            error_params={"run_id": run_id},
        )
    return EXIT_OK


async def cmd_eval_report(client: PlatformClient, run_id: str) -> int:
    run = await client.request("GET", f"/flows/api/v1/evaluation/runs/{run_id}", retry=True)
    cases = await client.request("GET", f"/flows/api/v1/evaluation/runs/{run_id}/cases", retry=True)
    emit({"run": run, "cases": cases})
    return EXIT_OK


async def cmd_eval_compare(client: PlatformClient, left: str, right: str) -> int:
    emit(
        await client.request(
            "GET",
            "/flows/api/v1/evaluation/runs/compare",
            params={"left_run_id": left, "right_run_id": right},
            retry=True,
        )
    )
    return EXIT_OK


async def cmd_case_from_session(
    client: PlatformClient, suite_id: str, session_id: str, name: str
) -> int:
    state = require_object(
        await client.request(
            "GET",
            "/flows/api/v1/tasks/state",
            params={"session_id": session_id},
            retry=True,
        ),
        "state",
    )
    dialog: list[JsonObject] = [
        {"role": message.role, "content": message.content}
        for message in parse(ExecutionStateView, state, "state").messages
        if message.role in {"user", "assistant", "system"} and message.content != ""
    ]
    if not dialog:
        raise usage_error(
            f"Session {session_id} has no user/assistant messages to turn into a case"
        )
    emit(
        await client.request(
            "POST",
            f"/flows/api/v1/evaluation/suites/{suite_id}/cases/from-dialog",
            json_body={"name": name, "branch_ids": "*", "dialog": dialog},
        )
    )
    return EXIT_OK


async def cmd_files_upload(
    client: PlatformClient, path: Path, segment: str, spec: JsonObject
) -> int:
    emit(await upload_file(client, path, segment=segment, spec=spec))
    return EXIT_OK


async def cmd_files_get(client: PlatformClient, file_id: str, segment: str) -> int:
    emit(await client.request("GET", f"/{segment}/api/v1/files/{file_id}", retry=True))
    return EXIT_OK


async def cmd_files_download(
    client: PlatformClient, file_id: str, segment: str, output: Path
) -> int:
    _headers, content = await client.request_bytes(
        "GET", f"/{segment}/api/v1/files/download/{file_id}"
    )
    output.write_bytes(content)
    emit({"file_id": file_id, "path": str(output), "bytes": len(content)})
    return EXIT_OK


async def cmd_docs_catalogs(client: PlatformClient, title: str | None) -> int:
    if title is None:
        emit(await client.request("GET", "/documents/api/v1/catalogs", retry=True))
        return EXIT_OK
    emit(
        await client.request(
            "POST",
            "/documents/api/v1/catalogs",
            json_body={"title": title, "company_visible": True},
        )
    )
    return EXIT_OK


async def cmd_docs_list(client: PlatformClient) -> int:
    emit(await client.request("GET", "/documents/api/v1/documents", retry=True))
    return EXIT_OK


async def cmd_docs_add(client: PlatformClient, path: Path, catalog_id: str) -> int:
    ref = await upload_file(
        client,
        path,
        segment="documents",
        spec={
            "source_kind": "office_document",
            "source_ref": {},
            "retention": {"kind": "office_document"},
            "placement": {"catalog_id": catalog_id, "catalog_path": [], "conflict": "autorename"},
        },
    )
    file_id = parse(FileRef, ref, "file").file_id
    document = await client.request(
        "POST",
        "/documents/api/v1/documents",
        json_body={"file_id": file_id, "catalog_id": catalog_id, "title": path.stem},
    )
    emit({"file": ref, "document": document})
    return EXIT_OK


async def cmd_docs_rag_enable(client: PlatformClient, catalog_id: str) -> int:
    emit(await client.request("POST", f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable"))
    return EXIT_OK


async def cmd_rag_ns(client: PlatformClient, name: str | None, description: str) -> int:
    if name is None:
        emit(await client.request("GET", "/rag/api/v1/namespaces", retry=True))
        return EXIT_OK
    emit(
        await client.request(
            "POST",
            "/rag/api/v1/namespaces",
            json_body={"name": name, "description": description},
        )
    )
    return EXIT_OK


async def cmd_rag_index(
    client: PlatformClient,
    *,
    namespace: str,
    path: Path | None,
    file_id: str | None,
    wait: bool,
    timeout: float,
) -> int:
    resolved = file_id
    if path is not None:
        ref = await upload_file(
            client,
            path,
            segment="rag",
            spec={
                "source_kind": "rag_document",
                "source_ref": {"namespace_id": namespace},
                "retention": {"kind": "rag_document"},
            },
        )
        resolved = parse(FileRef, ref, "file").file_id
    if resolved is None:
        raise usage_error("rag index needs a path or --file-id")
    indexed = require_object(
        await client.request(
            "POST",
            f"/rag/api/v1/namespaces/{namespace}/documents/index-file",
            json_body={"file_id": resolved},
        ),
        "index",
    )
    if wait:
        document_id = parse(IndexAccepted, indexed, "index").document_id
        indexed = await _poll_document(client, document_id, timeout)
    emit(indexed)
    return EXIT_OK


async def cmd_rag_ingest(
    client: PlatformClient, namespace: str, text: str, name: str | None
) -> int:
    body: JsonObject = {"text": text}
    if name is not None:
        body["document_name"] = name
    emit(
        await client.request(
            "POST", f"/rag/api/v1/namespaces/{namespace}/ingest-text", json_body=body
        )
    )
    return EXIT_OK


async def cmd_rag_search(client: PlatformClient, namespace: str, query: str, limit: int) -> int:
    emit(
        await client.request(
            "POST",
            f"/rag/api/v1/namespaces/{namespace}/search",
            json_body={"query": query, "limit": limit},
        )
    )
    return EXIT_OK


async def cmd_rag_rm(client: PlatformClient, namespace: str, document_id: str) -> int:
    emit(
        await client.request(
            "DELETE",
            f"/rag/api/v1/namespaces/{namespace}/documents/{document_id}",
        )
    )
    return EXIT_OK


async def cmd_search(client: PlatformClient, query: str, provider: str | None, limit: int) -> int:
    providers = [provider] if provider is not None and provider != "" else ["auto"]
    emit(
        await client.request(
            "POST",
            "/search/api/v1/search",
            json_body={"query": query, "limit": limit, "providers": providers},
        )
    )
    return EXIT_OK


async def cmd_search_providers(client: PlatformClient) -> int:
    emit(await client.request("GET", "/search/api/v1/providers", retry=True))
    return EXIT_OK


async def _consume_stream(
    client: PlatformClient,
    flow_id: str,
    *,
    method: str,
    params: JsonObject,
    context_id: str,
) -> int:
    last_state = ""
    task_id = ""
    seen_context = context_id
    texts: list[str] = []
    async for event in client.stream(
        "POST",
        f"/flows/api/v1/{flow_id}",
        json_body={"jsonrpc": "2.0", "id": "1", "method": method, "params": params},
        headers={"A2A-Version": "1.0"},
    ):
        if not json_mode():
            sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        if "error" in event:
            raise a2a_error(event)
        state, found_task, found_context, found_text = _read_a2a(event)
        if state is not None:
            last_state = state
        if found_task is not None:
            task_id = found_task
        if found_context is not None:
            seen_context = found_context
        if found_text is not None and found_text != "":
            texts.append(found_text)
    summary: JsonObject = {
        "flow_id": flow_id,
        "task_id": task_id,
        "context_id": seen_context,
        "session_id": f"{flow_id}:{seen_context}" if seen_context != "" else "",
        "task_state": last_state,
        "response": "\n".join(texts),
    }
    sys.stdout.write(json.dumps({"summary": summary}, ensure_ascii=False) + "\n")
    if last_state in _INPUT:
        raise PlatformCliError(
            error_code="input_required",
            error_detail="Agent is waiting for input",
            exit_code=EXIT_INPUT_REQUIRED,
            error_params=summary,
            hint=f"platform run --flow {flow_id} --context {seen_context} --input '...'",
        )
    if last_state in {"TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}:
        raise PlatformCliError(
            error_code="run_failed",
            error_detail=f"Run finished {last_state}",
            exit_code=EXIT_RUN_FAILED,
            error_params=summary,
        )
    return EXIT_OK


def _read_a2a(event: JsonObject) -> tuple[str | None, str | None, str | None, str | None]:
    try:
        frame = A2AFrame.model_validate(event)
    except ValidationError:
        return None, None, None, None
    result = frame.result
    if result is None:
        return None, None, None, None
    state: str | None = None
    task_id: str | None = None
    context_id: str | None = None
    text: str | None = None
    task = result.task
    update = result.statusUpdate
    holder = task.status if task is not None else None
    if holder is None and update is not None:
        holder = update.status
    if task is not None and "id" in task.model_fields_set:
        task_id = task.id
    if task is not None and "contextId" in task.model_fields_set:
        context_id = task.contextId
    if holder is not None and "state" in holder.model_fields_set:
        state = holder.state
    if holder is not None and holder.message is not None:
        rendered = holder.message.text()
        text = rendered if rendered != "" else None
    if update is not None and "taskId" in update.model_fields_set:
        task_id = update.taskId
    if update is not None and "contextId" in update.model_fields_set:
        context_id = update.contextId
    return state, task_id, context_id, text


async def _session_bundle(client: PlatformClient, session_id: str) -> JsonObject:
    state = await client.request(
        "GET",
        "/flows/api/v1/tasks/state",
        params={"session_id": session_id},
        retry=True,
    )
    history = await client.request(
        "GET",
        f"/flows/api/v1/tasks/{session_id}/history",
        params={"limit": 1000},
        retry=True,
    )
    trace = await client.request("GET", f"/flows/api/v1/traces/session/{session_id}", retry=True)
    try:
        logs = await client.request(
            "GET",
            f"/flows/api/v1/observability/logs/by-session/{session_id}",
            retry=True,
        )
    except PlatformCliError as exc:
        if exc.http_status != 503:
            raise
        logs = require_object(
            {"error_code": exc.error_code, "error_detail": exc.error_detail},
            "logs",
        )
    return require_object(
        {
            "state": state,
            "events": _history_events(history),
            "trace": trace,
            "logs": _log_rows(logs),
            "logs_status": logs,
        },
        "session",
    )


def _history_events(history: JsonValue) -> list[JsonValue]:
    try:
        return HistoryView.model_validate(history).events
    except ValidationError:
        return []


def _log_rows(logs: JsonValue) -> list[JsonValue]:
    rows = as_list(logs)
    if rows is not None:
        return rows
    try:
        return LogsView.model_validate(logs).items
    except ValidationError:
        return []


def _write_jsonl(path: Path, rows: JsonValue) -> None:
    parsed = as_list(rows)
    lines = [] if parsed is None else [json.dumps(row, ensure_ascii=False) for row in parsed]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _diff(local: JsonObject, remote: JsonObject, label: str) -> list[JsonObject]:
    changes: list[JsonObject] = []
    keys = sorted(set(local) | set(remote))
    for key in keys:
        if key in {"version", "company_id", "flow_row_id", "is_current", "metadata"}:
            continue
        left = local.get(key)
        right = remote.get(key)
        if left != right:
            changes.append(
                {"path": f"{label}.{key}", "local": _brief(left), "remote": _brief(right)}
            )
    return changes


def _brief(value: JsonValue) -> JsonValue:
    match value:
        case str() if len(value) > 200:
            return value[:200] + "…"
        case dict() as mapping:
            return require_object({"keys": sorted(mapping)}, "diff")
        case list() as items:
            return require_object({"len": len(items)}, "diff")
        case _:
            return value


_RECORD_LIST = TypeAdapter(list[NamedRecord])
_TEXT = TypeAdapter(str)


def _find_named(payload: JsonValue, name: str, field: str) -> JsonValue:
    for record in _records(payload):
        if _record_field(record, field) == name:
            return require_object(record.model_dump(mode="json", exclude_unset=True), "record")
    raise usage_error(f"No {field}={name}")


def _records(payload: object) -> list[NamedRecord]:
    try:
        return _RECORD_LIST.validate_python(payload)
    except ValidationError:
        try:
            return RecordPage.model_validate(payload).items
        except ValidationError as exc:
            raise usage_error("payload is not a list of records") from exc


def _record_field(record: NamedRecord, field: str) -> str:
    if field == "type":
        return record.type
    if field == "name":
        return record.name
    value = record.model_dump(mode="json", exclude_unset=True).get(field)
    try:
        return _TEXT.validate_python(value)
    except ValidationError:
        return ""


def _id_by_name(items: list[IdRow], name: str, id_field: str) -> str | None:
    for item in items:
        if item.name != name:
            continue
        found = item.suite_id if id_field == "suite_id" else item.rubric_id
        if found != "":
            return found
    return None


def _load_yaml(path: Path) -> JsonValue:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    return as_json(loaded, path.name)


def _prepare_cases(directory: Path, path: Path) -> str:
    prepared: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.strip() == "":
            continue
        try:
            case = CaseLine.model_validate(json.loads(raw_line))
        except ValidationError as exc:
            raise usage_error(f"{path} lines must be JSON objects") from exc
        if "name" not in case.model_fields_set and case.case_key != "":
            case.name = case.case_key
        body = case.model_dump(mode="json", exclude={"case_key", "fixtures"}, exclude_unset=True)
        prepared.append(json.dumps(body, ensure_ascii=False))
    _ = directory
    return "\n".join(prepared)


async def _poll_run(client: PlatformClient, run_id: str, timeout: float) -> JsonObject:
    deadline = time.monotonic() + timeout
    after = 0
    last: JsonObject = {}
    while time.monotonic() < deadline:
        page = parse(
            EvalEventPage,
            await client.request(
                "GET",
                f"/flows/api/v1/evaluation/runs/{run_id}/events-page",
                params={"after_sequence": after, "limit": 200},
                retry=True,
            ),
            "events-page",
        )
        for event in page.items:
            if "sequence" in event.model_fields_set:
                after = event.sequence
            emit_line(f"eval {event.event_type} seq={event.sequence}")
        run = require_object(
            await client.request("GET", f"/flows/api/v1/evaluation/runs/{run_id}", retry=True),
            "run",
        )
        last = run
        if _run_state(run) in {"passed", "failed", "error", "canceled"}:
            return run
        await asyncio.sleep(1)
    emit_line(f"eval wait timed out; continue with platform eval report {run_id}")
    return last


def _run_state(run: JsonObject) -> str:
    return parse(RunEnvelope, run, "run").resolved_state()


async def _poll_document(client: PlatformClient, document_id: str, timeout: float) -> JsonObject:
    deadline = time.monotonic() + timeout
    last: JsonObject = {}
    while time.monotonic() < deadline:
        status = require_object(
            await client.request("GET", f"/rag/api/v1/documents/{document_id}/status", retry=True),
            "status",
        )
        last = status
        state = parse(DocumentStatus, status, "status").status
        emit_line(f"rag {document_id} {state}")
        if state in {"completed", "failed", "skipped"}:
            return status
        await asyncio.sleep(1)
    return last
