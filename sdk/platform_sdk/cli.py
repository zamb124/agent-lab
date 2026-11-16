"""Точка входа `platform`."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from platform_sdk.commands import (
    cmd_case_from_session,
    cmd_context_list,
    cmd_context_use,
    cmd_diff,
    cmd_docs_add,
    cmd_docs_catalogs,
    cmd_docs_list,
    cmd_docs_rag_enable,
    cmd_eval_compare,
    cmd_eval_push,
    cmd_eval_report,
    cmd_eval_run,
    cmd_explain,
    cmd_files_download,
    cmd_files_get,
    cmd_files_upload,
    cmd_flows_list,
    cmd_guide,
    cmd_init,
    cmd_login,
    cmd_logs,
    cmd_pull,
    cmd_push,
    cmd_rag_index,
    cmd_rag_ingest,
    cmd_rag_ns,
    cmd_rag_rm,
    cmd_rag_search,
    cmd_remove,
    cmd_rollback,
    cmd_run,
    cmd_schema_pull,
    cmd_search,
    cmd_search_providers,
    cmd_session_action,
    cmd_sessions_export,
    cmd_sessions_inspect,
    cmd_sessions_list,
    cmd_state_at,
    cmd_trace,
    cmd_validate,
    cmd_vars_list,
    cmd_vars_set,
    cmd_versions,
    cmd_wait,
    cmd_whoami,
)
from platform_sdk.context_store import load_context
from platform_sdk.errors import EXIT_INTERNAL, PlatformCliError, usage_error
from platform_sdk.http import PlatformClient
from platform_sdk.json_types import JsonObject
from platform_sdk.output import configure_output, emit_error


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    configure_output(force_json=args.json)
    try:
        code = asyncio.run(_dispatch(args))
    except PlatformCliError as exc:
        emit_error(exc)
        raise SystemExit(exc.exit_code) from exc
    except BrokenPipeError:
        raise SystemExit(0)
    except KeyboardInterrupt:
        raise SystemExit(EXIT_INTERNAL)
    raise SystemExit(code)


async def _dispatch(args: argparse.Namespace) -> int:
    command = args.command
    if command == "login":
        return await cmd_login(args.host, args.api_key, args.name)
    if command == "context-ls":
        return cmd_context_list()
    if command == "context-use":
        return cmd_context_use(args.name)
    if command == "guide":
        return cmd_guide()
    if command == "init":
        return cmd_init(Path(args.directory), args.flow_id, args.name)
    client = _client(args)
    try:
        return await _with_client(client, args)
    finally:
        await client.close()


async def _with_client(client: PlatformClient, args: argparse.Namespace) -> int:
    command = args.command
    directory = Path(args.directory) if hasattr(args, "directory") else Path(".")
    if command == "whoami":
        return await cmd_whoami(client)
    if command == "schema":
        return await cmd_schema_pull(client, directory)
    if command == "explain":
        return await cmd_explain(client, args.topic, args.name)
    if command == "ls":
        return await cmd_flows_list(client)
    if command == "pull":
        return await cmd_pull(client, directory, args.flow_id)
    if command == "diff":
        return await cmd_diff(client, directory)
    if command == "validate":
        return await cmd_validate(client, directory)
    if command == "push":
        return await cmd_push(client, directory, force_base=args.force_base)
    if command == "versions":
        return await cmd_versions(client, args.flow_id)
    if command == "rollback":
        return await cmd_rollback(client, directory, args.flow_id, args.version)
    if command == "rm":
        return await cmd_remove(client, args.flow_id)
    if command == "vars-ls":
        return await cmd_vars_list(client)
    if command == "vars-set":
        return await cmd_vars_set(client, args.key, args.value, secret=args.secret)
    if command == "run":
        text = _input_text(args.input)
        return await cmd_run(
            client,
            flow_id=args.flow_id,
            text=text,
            branch=args.branch,
            variables=_variables(args.var),
            files=[Path(path) for path in args.file],
            context_id=args.context,
            breakpoints=args.breakpoint,
            detach=args.detach,
        )
    if command == "wait":
        return await cmd_wait(client, args.flow_id, args.task_id)
    if command == "sessions-ls":
        return await cmd_sessions_list(client, args.flow)
    if command == "sessions-inspect":
        return await cmd_sessions_inspect(client, args.session_id)
    if command == "sessions-export":
        return await cmd_sessions_export(client, args.session_id, Path(args.output))
    if command == "state-at":
        return await cmd_state_at(client, args.session_id, args.sequence)
    if command in {"session-action", "fork", "rewind", "retry"}:
        action = args.action if command == "session-action" else command
        return await cmd_session_action(client, args.session_id, action, args.sequence)
    if command == "trace":
        return await cmd_trace(client, args.ref)
    if command == "logs":
        return await cmd_logs(client, args.session_id)
    if command == "eval-push":
        return await cmd_eval_push(client, directory)
    if command == "eval-run":
        return await cmd_eval_run(
            client,
            suite_id=args.suite_id,
            branch_id=args.branch,
            trials=args.trials,
            wait=args.wait,
            timeout=args.timeout,
        )
    if command == "eval-report":
        return await cmd_eval_report(client, args.run_id)
    if command == "eval-compare":
        return await cmd_eval_compare(client, args.left, args.right)
    if command == "case-from-session":
        return await cmd_case_from_session(client, args.suite_id, args.session_id, args.name)
    if command == "files-upload":
        return await cmd_files_upload(client, Path(args.path), args.segment, _upload_spec(args))
    if command == "files-get":
        return await cmd_files_get(client, args.file_id, args.segment)
    if command == "files-download":
        return await cmd_files_download(client, args.file_id, args.segment, Path(args.output))
    if command == "docs-catalogs":
        return await cmd_docs_catalogs(client, args.title)
    if command == "docs-ls":
        return await cmd_docs_list(client)
    if command == "docs-add":
        return await cmd_docs_add(client, Path(args.path), args.catalog)
    if command == "docs-rag":
        return await cmd_docs_rag_enable(client, args.catalog)
    if command == "rag-ns":
        return await cmd_rag_ns(client, args.name, args.description)
    if command == "rag-index":
        return await cmd_rag_index(
            client,
            namespace=args.ns,
            path=Path(args.path) if args.path is not None else None,
            file_id=args.file_id,
            wait=args.wait,
            timeout=args.timeout,
        )
    if command == "rag-ingest":
        return await cmd_rag_ingest(client, args.ns, args.text, args.name)
    if command == "rag-search":
        return await cmd_rag_search(client, args.ns, args.query, args.limit)
    if command == "rag-rm":
        return await cmd_rag_rm(client, args.ns, args.document_id)
    if command == "search":
        return await cmd_search(client, args.query, args.provider, args.limit)
    if command == "search-providers":
        return await cmd_search_providers(client)
    raise usage_error(f"Unknown command {command}")


def _client(args: argparse.Namespace) -> PlatformClient:
    context = load_context(args.context_name)
    return PlatformClient(
        context,
        timeout=args.timeout,
        namespace=args.namespace,
    )


def _input_text(value: str | None) -> str:
    if value is None or value == "-":
        return sys.stdin.read()
    return value


def _variables(pairs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise usage_error(f"--var expects key=value, got {pair}")
        key, raw = pair.split("=", 1)
        if key == "":
            raise usage_error("--var key is empty")
        values[key] = raw
    return values


def _upload_spec(args: argparse.Namespace) -> JsonObject:
    if args.segment == "rag":
        if args.ns is None:
            raise usage_error("files upload --segment rag needs --ns")
        return {
            "source_kind": "rag_document",
            "source_ref": {"namespace_id": args.ns},
            "retention": {"kind": "rag_document"},
        }
    if args.catalog is None:
        raise usage_error("files upload --segment documents needs --catalog")
    return {
        "source_kind": "office_document",
        "source_ref": {},
        "retention": {"kind": "office_document"},
        "placement": {"catalog_id": args.catalog, "catalog_path": [], "conflict": "autorename"},
    }


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    common.add_argument("--timeout", type=float, default=120)
    common.add_argument("--namespace", default=None)
    common.add_argument("--context-name", default=None)
    parser = argparse.ArgumentParser(prog="platform", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", parents=[common])
    login.add_argument("--host", required=True)
    login.add_argument("--api-key", required=True)
    login.add_argument("--name", default="default")

    sub.add_parser("context-ls", parents=[common])
    use = sub.add_parser("context-use", parents=[common])
    use.add_argument("name")
    sub.add_parser("whoami", parents=[common])
    sub.add_parser("guide", parents=[common])

    init = sub.add_parser("init", parents=[common])
    init.add_argument("--directory", default=".")
    init.add_argument("--flow-id", required=True)
    init.add_argument("--name", required=True)

    for name in ("schema", "diff", "validate", "eval-push"):
        command = sub.add_parser(name, parents=[common])
        command.add_argument("--directory", default=".")

    explain = sub.add_parser("explain", parents=[common])
    explain.add_argument(
        "topic",
        choices=[
            "node-types",
            "node",
            "tools",
            "tool",
            "models",
            "resource-types",
            "flow-ui",
            "events",
        ],
    )
    explain.add_argument("name", nargs="?")

    sub.add_parser("ls", parents=[common])

    pull = sub.add_parser("pull", parents=[common])
    pull.add_argument("flow_id")
    pull.add_argument("--directory", default=".")

    push = sub.add_parser("push", parents=[common])
    push.add_argument("--directory", default=".")
    push.add_argument("--force-base", action="store_true")

    versions = sub.add_parser("versions", parents=[common])
    versions.add_argument("flow_id")
    rollback = sub.add_parser("rollback", parents=[common])
    rollback.add_argument("flow_id")
    rollback.add_argument("version")
    rollback.add_argument("--directory", default=".")
    remove = sub.add_parser("rm", parents=[common])
    remove.add_argument("flow_id")

    sub.add_parser("vars-ls", parents=[common])
    var_set = sub.add_parser("vars-set", parents=[common])
    var_set.add_argument("key")
    var_set.add_argument("value")
    var_set.add_argument("--secret", action="store_true")

    run = sub.add_parser("run", parents=[common])
    run.add_argument("--flow", dest="flow_id", required=True)
    run.add_argument("--input", default=None)
    run.add_argument("--branch", default=None)
    run.add_argument("--var", action="append", default=[])
    run.add_argument("--file", action="append", default=[])
    run.add_argument("--context", default=None)
    run.add_argument("--breakpoint", action="append", default=[])
    run.add_argument("--detach", action="store_true")

    wait = sub.add_parser("wait", parents=[common])
    wait.add_argument("--flow", dest="flow_id", required=True)
    wait.add_argument("task_id")

    sessions = sub.add_parser("sessions-ls", parents=[common])
    sessions.add_argument("--flow", default=None)
    inspect = sub.add_parser("sessions-inspect", parents=[common])
    inspect.add_argument("session_id")
    export = sub.add_parser("sessions-export", parents=[common])
    export.add_argument("session_id")
    export.add_argument("-o", "--output", required=True)
    state_at = sub.add_parser("state-at", parents=[common])
    state_at.add_argument("session_id")
    state_at.add_argument("sequence", type=int)
    for action in ("fork", "rewind", "retry"):
        action_parser = sub.add_parser(action, parents=[common])
        action_parser.add_argument("session_id")
        action_parser.add_argument("--sequence", type=int)
        action_parser.set_defaults(command="session-action", action=action)
    trace = sub.add_parser("trace", parents=[common])
    trace.add_argument("ref")
    logs = sub.add_parser("logs", parents=[common])
    logs.add_argument("session_id")

    eval_run = sub.add_parser("eval-run", parents=[common])
    eval_run.add_argument("--suite-id", required=True)
    eval_run.add_argument("--branch", default="default")
    eval_run.add_argument("--trials", type=int, default=1)
    eval_run.add_argument("--wait", action="store_true")
    report = sub.add_parser("eval-report", parents=[common])
    report.add_argument("run_id")
    compare = sub.add_parser("eval-compare", parents=[common])
    compare.add_argument("left")
    compare.add_argument("right")
    case = sub.add_parser("case-from-session", parents=[common])
    case.add_argument("--suite-id", required=True)
    case.add_argument("session_id")
    case.add_argument("--name", required=True)

    upload = sub.add_parser("files-upload", parents=[common])
    upload.add_argument("path")
    upload.add_argument("--segment", choices=["documents", "rag"], required=True)
    upload.add_argument("--catalog", default=None)
    upload.add_argument("--ns", default=None)
    files_get = sub.add_parser("files-get", parents=[common])
    files_get.add_argument("file_id")
    files_get.add_argument("--segment", choices=["documents", "rag"], required=True)
    download = sub.add_parser("files-download", parents=[common])
    download.add_argument("file_id")
    download.add_argument("--segment", choices=["documents", "rag"], required=True)
    download.add_argument("-o", "--output", required=True)

    catalogs = sub.add_parser("docs-catalogs", parents=[common])
    catalogs.add_argument("--title", default=None)
    sub.add_parser("docs-ls", parents=[common])
    docs_add = sub.add_parser("docs-add", parents=[common])
    docs_add.add_argument("path")
    docs_add.add_argument("--catalog", required=True)
    docs_rag = sub.add_parser("docs-rag", parents=[common])
    docs_rag.add_argument("catalog")

    rag_ns = sub.add_parser("rag-ns", parents=[common])
    rag_ns.add_argument("--name", default=None)
    rag_ns.add_argument("--description", default="")
    rag_index = sub.add_parser("rag-index", parents=[common])
    rag_index.add_argument("--ns", required=True)
    rag_index.add_argument("path", nargs="?")
    rag_index.add_argument("--file-id", default=None)
    rag_index.add_argument("--wait", action="store_true")
    ingest = sub.add_parser("rag-ingest", parents=[common])
    ingest.add_argument("--ns", required=True)
    ingest.add_argument("--text", required=True)
    ingest.add_argument("--name", default=None)
    rag_search = sub.add_parser("rag-search", parents=[common])
    rag_search.add_argument("--ns", required=True)
    rag_search.add_argument("query")
    rag_search.add_argument("--limit", type=int, default=5)
    rag_rm = sub.add_parser("rag-rm", parents=[common])
    rag_rm.add_argument("--ns", required=True)
    rag_rm.add_argument("document_id")

    search = sub.add_parser("search", parents=[common])
    search.add_argument("query")
    search.add_argument("--provider", default=None)
    search.add_argument("--limit", type=int, default=10)
    sub.add_parser("search-providers", parents=[common])
    return parser


if __name__ == "__main__":
    main()
