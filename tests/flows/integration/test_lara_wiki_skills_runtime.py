"""Lara Wiki E2E: MockLLM + run_flow; wiki ASGI/Postgres — как в проде.

Покрывает unlock skills и полный обход каждого builtin `wiki_*`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

import pytest
from pydantic import TypeAdapter

from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.services.platform_assistant_skills import (
    LARA_PLATFORM_SKILL_ROOTS,
    PLATFORM_ASSISTANT_SEED_SKILL_IDS,
    seed_platform_assistant_skills,
)
from core.clients.llm.mock import MockLLM, MockLLMQueuedResponse
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from core.state import ExecutionState
from core.types import JsonObject, JsonValue
from tests.flows.agent_skills_harness import ensure_lara_flow
from tests.flows.durable_runtime_harness import run_flow
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.usefixtures("app"), pytest.mark.timeout(300, func_only=True)]

MockLLMQueue = Callable[[list[MockLLMQueuedResponse]], MockLLM]
_JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
_BRANCH = "wiki"

WIKI_SKILL_CHAIN: tuple[str, ...] = (
    "wiki-platform",
    "wiki-pages",
    "wiki-access",
    "wiki-discovery",
    "team-directory",
)

ALL_WIKI_TOOL_IDS: frozenset[str] = frozenset(
    {
        "wiki_list_tree",
        "wiki_list_namespaces",
        "wiki_get_page",
        "wiki_get_markdown",
        "wiki_create_page",
        "wiki_update_markdown",
        "wiki_update_properties",
        "wiki_move_page",
        "wiki_move_page_namespace",
        "wiki_delete_page",
        "wiki_list_deleted",
        "wiki_restore_page",
        "wiki_import_markdown",
        "wiki_parse_markdown",
        "wiki_list_revisions",
        "wiki_get_revision",
        "wiki_restore_revision",
        "wiki_list_comments",
        "wiki_create_comment",
        "wiki_resolve_comment",
        "wiki_delete_comment",
        "wiki_get_access",
        "wiki_set_member",
        "wiki_remove_member",
        "wiki_rotate_public_link",
        "wiki_search",
        "wiki_list_backlinks",
    }
)


@contextmanager
def _employee_context(
    employee_user: User,
    company: Company,
    *,
    namespace: str,
) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=employee_user,
        host="",
        trace_id="lara-wiki-skills-runtime",
        session_id="lara-wiki-skills",
        channel="a2a",
    )
    set_context(ctx.model_copy(update={"active_namespace": namespace}))
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _lara_state(*, unique_id: str, user_id: str, suffix: str = "") -> ExecutionState:
    context_id = f"lara-wiki-{unique_id}{suffix}"
    return ExecutionState(
        task_id=f"task-wiki-{unique_id}{suffix}",
        context_id=context_id,
        user_id=user_id,
        session_id=f"lara:{context_id}",
        branch_id=_BRANCH,
        content=f"wiki runtime {unique_id}{suffix}",
    )


async def _seed_lara_skills(container: FlowContainer) -> None:
    seeded = await seed_platform_assistant_skills(
        container.agent_skill_service,
        container.files_service,
        "system",
    )
    assert seeded == len(PLATFORM_ASSISTANT_SEED_SKILL_IDS)


async def _require_lara(container: FlowContainer) -> Flow:
    _ = await ensure_lara_flow(container)
    flow = await container.flow_factory.get_flow("lara", branch_id=_BRANCH)
    assert flow is not None
    return flow


async def _run_lara(container: FlowContainer, *, state: ExecutionState) -> ExecutionState:
    flow = await _require_lara(container)
    main_node = flow.nodes["main"]
    assert getattr(main_node, "agent_skill_ids", None) == list(LARA_PLATFORM_SKILL_ROOTS)
    tool_names = {tool.name for tool in await main_node.get_tools(state)}
    assert "load_agent_skill" in tool_names
    assert "wiki_list_tree" not in tool_names
    return await run_flow(
        container=as_flow_runtime_container(container),
        flow=flow,
        state=state,
    )


def _tool_json(value: JsonValue) -> JsonObject:
    if isinstance(value, str):
        return _JSON_OBJECT_ADAPTER.validate_json(value)
    return _JSON_OBJECT_ADAPTER.validate_python(value)


def _load(*skill_ids: str) -> list[MockLLMQueuedResponse]:
    return [
        {
            "type": "tool_call",
            "tool": "load_agent_skill",
            "args": {"agent_skill_id": skill_id},
        }
        for skill_id in skill_ids
    ]


def _text(content: str) -> MockLLMQueuedResponse:
    return {"type": "text", "content": content}


def _call(tool: str, **args: object) -> MockLLMQueuedResponse:
    return {"type": "tool_call", "tool": tool, "args": dict(args)}


def _require_str(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise AssertionError(f"expected non-empty str {key} in {payload}")
    return value


def _ok_tool(result: ExecutionState, tool_id: str) -> JsonObject:
    raw = result.tool_results.get(tool_id)
    if raw is None:
        raise AssertionError(f"missing tool_results[{tool_id}]; keys={sorted(result.tool_results)}")
    payload = _tool_json(raw)
    if isinstance(payload, dict) and payload.get("success") is False:
        raise AssertionError(f"tool {tool_id} failed: {payload}")
    return payload


async def _prepare_employee(
    *,
    frontend_container,
    unique_id: str,
    flow_suffix: str,
) -> tuple[User, Company, str, str]:
    flow_id = f"lara_wiki_{flow_suffix}_{unique_id}"
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_container,
        flow_id=flow_id,
        company_id="system",
        name=f"Lara Wiki {flow_suffix}",
        roles=["member"],
        curator_user_ids=["system"],
    )
    employee_user_id = flow_employee_user_id(flow_id)
    namespace = f"lara_wiki_{flow_suffix}_{unique_id}"
    await seed_namespace_via_repo("system", namespace)
    return employee, company, employee_user_id, namespace


def _captured_tool_names(call: JsonObject) -> set[str]:
    raw_tools = call.get("tools")
    names: set[str] = set()
    if not isinstance(raw_tools, list):
        return names
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        direct_name = tool.get("name")
        if isinstance(direct_name, str) and direct_name.strip():
            names.add(direct_name)
            continue
        function = tool.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name.strip():
                names.add(function_name)
    return names


async def _turn(
    *,
    container: FlowContainer,
    mock_llm_with_queue: MockLLMQueue,
    employee: User,
    company: Company,
    namespace: str,
    unique_id: str,
    employee_user_id: str,
    suffix: str,
    queue: Sequence[MockLLMQueuedResponse],
) -> ExecutionState:
    _ = mock_llm_with_queue(list(queue))
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id, suffix=suffix)
    with _employee_context(employee, company, namespace=namespace):
        result = await _run_lara(container, state=state)
    assert result.interrupt is None, result.interrupt
    return result


@pytest.mark.asyncio
async def test_lara_wiki_unlock_skills(
    container: FlowContainer,
    flows_service,
    frontend_container,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        unique_id=unique_id,
        flow_suffix="unlock",
    )
    _ = mock_llm_with_queue(
        [
            *_load(
                *WIKI_SKILL_CHAIN,
                "knowledge-rag",
                "document-workspace",
            ),
            _text("wiki skills ready"),
        ]
    )
    state = _lara_state(unique_id=unique_id, user_id=employee_user_id)
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)
        result = await _run_lara(container, state=state)

    assert result.interrupt is None
    calls = await mock_llm_capture()
    assert "wiki_list_tree" not in _captured_tool_names(calls[0])
    unlocked = set().union(*(_captured_tool_names(call) for call in calls))
    missing = ALL_WIKI_TOOL_IDS - unlocked
    assert not missing, f"wiki tools not unlocked after skills: {sorted(missing)}"
    for tool_name in ("rag_search", "create_file", "team_list_members"):
        assert tool_name in unlocked


@pytest.mark.asyncio
async def test_lara_wiki_every_tool_full_tour(
    container: FlowContainer,
    flows_service,
    frontend_container,
    mock_llm_with_queue: MockLLMQueue,
    system_user2_id: str,
    unique_id: str,
) -> None:
    """Каждый wiki_* вызывается хотя бы раз через Lara на реальном wiki ASGI."""
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        unique_id=unique_id,
        flow_suffix="full",
    )
    other_namespace = f"lara_wiki_full_other_{unique_id}"
    await seed_namespace_via_repo("system", other_namespace)

    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)

    exercised: set[str] = set()

    def mark(*tool_ids: str) -> None:
        exercised.update(tool_ids)

    skills = _load(*WIKI_SKILL_CHAIN)
    title = f"Full tour {unique_id}"
    body_v1 = f"# {title}\n\nVersion one {unique_id}."
    body_v2 = f"# {title}\n\nVersion two {unique_id}."
    entity_id = f"ent-wiki-tour-{unique_id}"

    # --- orient + create + parse/import ---
    turn1 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-01",
        queue=[
            *skills,
            _call("wiki_list_namespaces"),
            _call("wiki_list_tree"),
            _call("wiki_create_page", title=title, markdown=body_v1),
            _call(
                "wiki_parse_markdown",
                markdown=f"---\ntitle: Imported {unique_id}\n---\n\n# Imported\n",
            ),
            _call(
                "wiki_import_markdown",
                markdown=(
                    f"---\ntitle: Imported {unique_id}\n---\n\n"
                    f"# Imported\n\nBody {unique_id}."
                ),
            ),
            _text("created"),
        ],
    )
    namespaces = _ok_tool(turn1, "wiki_list_namespaces")
    assert namespaces.get("count", 0) >= 1
    tree0 = _ok_tool(turn1, "wiki_list_tree")
    assert tree0.get("count", 0) >= 0
    created = _ok_tool(turn1, "wiki_create_page")
    wiki_page_id = _require_str(created, "wiki_page_id")
    parsed = _ok_tool(turn1, "wiki_parse_markdown")
    assert "notice_count" in parsed
    imported = _ok_tool(turn1, "wiki_import_markdown")
    imported_page_id = _require_str(imported, "wiki_page_id")
    mark(
        "wiki_list_namespaces",
        "wiki_list_tree",
        "wiki_create_page",
        "wiki_parse_markdown",
        "wiki_import_markdown",
    )

    # --- read / write / search / properties / child + move ---
    turn2 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-02",
        queue=[
            *skills,
            _call("wiki_get_page", wiki_page_id=wiki_page_id),
            _call("wiki_get_markdown", wiki_page_id=wiki_page_id),
            _call(
                "wiki_update_markdown",
                wiki_page_id=wiki_page_id,
                markdown=body_v2,
                create_revision=True,
            ),
            _call(
                "wiki_update_properties",
                wiki_page_id=wiki_page_id,
                icon="📘",
                is_full_width=True,
            ),
            _call("wiki_search", query=unique_id, mode="lexical"),
            _call(
                "wiki_create_page",
                title=f"Child {unique_id}",
                markdown=f"# Child {unique_id}",
            ),
            _text("edited"),
        ],
    )
    page = _ok_tool(turn2, "wiki_get_page")
    assert page.get("can_edit") is True
    md = _ok_tool(turn2, "wiki_get_markdown")
    assert unique_id in str(md.get("markdown"))
    _ok_tool(turn2, "wiki_update_markdown")
    props = _ok_tool(turn2, "wiki_update_properties")
    assert props.get("wiki_page_id") == wiki_page_id
    searched = _ok_tool(turn2, "wiki_search")
    assert searched.get("success") is True
    # last wiki_create_page overwrites tool_results key
    child = _ok_tool(turn2, "wiki_create_page")
    child_page_id = _require_str(child, "wiki_page_id")
    mark(
        "wiki_get_page",
        "wiki_get_markdown",
        "wiki_update_markdown",
        "wiki_update_properties",
        "wiki_search",
        "wiki_create_page",
    )

    turn3 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-03",
        queue=[
            *skills,
            _call(
                "wiki_move_page",
                wiki_page_id=child_page_id,
                parent_page_id=wiki_page_id,
            ),
            _call("wiki_list_tree"),
            _text("moved"),
        ],
    )
    moved = _ok_tool(turn3, "wiki_move_page")
    assert moved.get("wiki_page_id") == child_page_id
    tree = _ok_tool(turn3, "wiki_list_tree")
    assert tree.get("count", 0) >= 2
    mark("wiki_move_page", "wiki_list_tree")

    # --- revisions ---
    turn4 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-04",
        queue=[
            *skills,
            _call("wiki_list_revisions", wiki_page_id=wiki_page_id),
            _text("revisions listed"),
        ],
    )
    revisions = _ok_tool(turn4, "wiki_list_revisions")
    items = revisions.get("items")
    assert isinstance(items, list) and len(items) >= 1
    first_revision = items[0]
    assert isinstance(first_revision, dict)
    wiki_revision_id = first_revision.get("wiki_revision_id")
    assert isinstance(wiki_revision_id, str) and wiki_revision_id.strip()
    mark("wiki_list_revisions")

    turn5 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-05",
        queue=[
            *skills,
            _call("wiki_get_revision", wiki_revision_id=wiki_revision_id),
            _call("wiki_restore_revision", wiki_revision_id=wiki_revision_id),
            _text("revision restored"),
        ],
    )
    revision = _ok_tool(turn5, "wiki_get_revision")
    assert revision.get("wiki_revision_id") == wiki_revision_id
    restored_rev = _ok_tool(turn5, "wiki_restore_revision")
    assert restored_rev.get("wiki_page_id") == wiki_page_id
    mark("wiki_get_revision", "wiki_restore_revision")

    # --- comments ---
    turn6 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-06",
        queue=[
            *skills,
            _call(
                "wiki_create_comment",
                wiki_page_id=wiki_page_id,
                body_markdown=f"Comment {unique_id}",
                anchor_text="Version",
            ),
            _call("wiki_list_comments", wiki_page_id=wiki_page_id),
            _text("commented"),
        ],
    )
    created_comment = _ok_tool(turn6, "wiki_create_comment")
    wiki_comment_id = _require_str(created_comment, "wiki_comment_id")
    listed_comments = _ok_tool(turn6, "wiki_list_comments")
    assert listed_comments.get("count", 0) >= 1
    mark("wiki_create_comment", "wiki_list_comments")

    turn7 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-07",
        queue=[
            *skills,
            _call(
                "wiki_resolve_comment",
                wiki_comment_id=wiki_comment_id,
                resolved=True,
            ),
            _call("wiki_delete_comment", wiki_comment_id=wiki_comment_id),
            _text("comment closed"),
        ],
    )
    resolved = _ok_tool(turn7, "wiki_resolve_comment")
    assert resolved.get("wiki_comment_id") == wiki_comment_id
    deleted_comment = _ok_tool(turn7, "wiki_delete_comment")
    assert deleted_comment.get("deleted") is True
    mark("wiki_resolve_comment", "wiki_delete_comment")

    # --- access + public link ---
    turn8 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-08",
        queue=[
            *skills,
            _call("wiki_get_access", wiki_page_id=wiki_page_id),
            _call(
                "wiki_set_member",
                wiki_page_id=wiki_page_id,
                user_id=system_user2_id,
                permission="read",
            ),
            _call(
                "wiki_remove_member",
                wiki_page_id=wiki_page_id,
                user_id=system_user2_id,
            ),
            _call(
                "wiki_update_properties",
                wiki_page_id=wiki_page_id,
                is_published=True,
            ),
            _call(
                "wiki_rotate_public_link",
                wiki_page_id=wiki_page_id,
                enabled=True,
                permission="view",
            ),
            _text("link on"),
        ],
    )
    access = _ok_tool(turn8, "wiki_get_access")
    assert access.get("wiki_page_id") == wiki_page_id
    _ok_tool(turn8, "wiki_set_member")
    _ok_tool(turn8, "wiki_remove_member")
    _ok_tool(turn8, "wiki_update_properties")
    rotated_on = _ok_tool(turn8, "wiki_rotate_public_link")
    assert rotated_on.get("enabled") is True
    public_url = rotated_on.get("url")
    assert isinstance(public_url, str) and "/wiki/s/" in public_url
    mark(
        "wiki_get_access",
        "wiki_set_member",
        "wiki_remove_member",
        "wiki_update_properties",
        "wiki_rotate_public_link",
    )

    turn8b = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-08b",
        queue=[
            *skills,
            _call(
                "wiki_rotate_public_link",
                wiki_page_id=wiki_page_id,
                enabled=False,
            ),
            _text("link off"),
        ],
    )
    rotated_off = _ok_tool(turn8b, "wiki_rotate_public_link")
    assert rotated_off.get("enabled") is False
    mark("wiki_rotate_public_link")

    # --- backlinks (mention in markdown) ---
    turn9 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-09",
        queue=[
            *skills,
            _call(
                "wiki_update_markdown",
                wiki_page_id=wiki_page_id,
                markdown=f"# {title}\n\nSee @[Entity](entity:{entity_id}).",
            ),
            _call(
                "wiki_list_backlinks",
                target_kind="crm_entity",
                target_id=entity_id,
            ),
            _text("backlinks"),
        ],
    )
    _ok_tool(turn9, "wiki_update_markdown")
    backlinks = _ok_tool(turn9, "wiki_list_backlinks")
    backlink_items = backlinks.get("items")
    assert isinstance(backlink_items, list)
    assert wiki_page_id in {
        item.get("wiki_page_id") for item in backlink_items if isinstance(item, dict)
    }
    mark("wiki_update_markdown", "wiki_list_backlinks")

    # --- trash / restore (imported page) ---
    turn10 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-10",
        queue=[
            *skills,
            _call("wiki_delete_page", wiki_page_id=imported_page_id),
            _call("wiki_list_deleted"),
            _call("wiki_restore_page", wiki_page_id=imported_page_id),
            _text("trash cycle"),
        ],
    )
    deleted = _ok_tool(turn10, "wiki_delete_page")
    assert deleted.get("deleted") is True
    deleted_list = _ok_tool(turn10, "wiki_list_deleted")
    deleted_items = deleted_list.get("items")
    assert isinstance(deleted_items, list)
    assert imported_page_id in {
        item.get("wiki_page_id") for item in deleted_items if isinstance(item, dict)
    }
    restored_page = _ok_tool(turn10, "wiki_restore_page")
    assert restored_page.get("wiki_page_id") == imported_page_id
    mark("wiki_delete_page", "wiki_list_deleted", "wiki_restore_page")

    # --- move to another namespace (disposable page last) ---
    turn11 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-11",
        queue=[
            *skills,
            _call(
                "wiki_create_page",
                title=f"Relocate {unique_id}",
                markdown=f"# Relocate {unique_id}",
            ),
            _text("ready to move ns"),
        ],
    )
    relocate = _ok_tool(turn11, "wiki_create_page")
    relocate_page_id = _require_str(relocate, "wiki_page_id")
    mark("wiki_create_page")

    turn12 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-12",
        queue=[
            *skills,
            _call(
                "wiki_move_page_namespace",
                wiki_page_id=relocate_page_id,
                target_namespace=other_namespace,
            ),
            _text("namespace moved"),
        ],
    )
    ns_moved = _ok_tool(turn12, "wiki_move_page_namespace")
    assert ns_moved.get("wiki_page_id") == relocate_page_id
    mark("wiki_move_page_namespace")

    missing = ALL_WIKI_TOOL_IDS - exercised
    assert not missing, f"wiki tools not exercised: {sorted(missing)}"
    assert exercised == ALL_WIKI_TOOL_IDS


@pytest.mark.asyncio
async def test_lara_wiki_page_lifecycle(
    container: FlowContainer,
    flows_service,
    frontend_container,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        unique_id=unique_id,
        flow_suffix="life",
    )
    title = f"Wiki page {unique_id}"
    body_md = f"# {title}\n\nBody for {unique_id}."
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)

    result1 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-c",
        queue=[
            *_load("wiki-platform", "wiki-pages"),
            _call("wiki_create_page", title=title, markdown=body_md),
            _text("created"),
        ],
    )
    created = _ok_tool(result1, "wiki_create_page")
    wiki_page_id = _require_str(created, "wiki_page_id")

    result2 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-rw",
        queue=[
            *_load("wiki-platform", "wiki-pages", "wiki-discovery"),
            _call("wiki_get_markdown", wiki_page_id=wiki_page_id),
            _call(
                "wiki_update_markdown",
                wiki_page_id=wiki_page_id,
                markdown=f"{body_md}\n\nUpdated.",
            ),
            _call("wiki_search", query=unique_id, mode="lexical"),
            _call("wiki_list_tree"),
            _text("read write search"),
        ],
    )
    md = _ok_tool(result2, "wiki_get_markdown")
    assert unique_id in str(md.get("markdown"))
    _ok_tool(result2, "wiki_update_markdown")
    _ok_tool(result2, "wiki_search")
    tree = _ok_tool(result2, "wiki_list_tree")
    assert tree.get("count", 0) >= 1


@pytest.mark.asyncio
async def test_lara_wiki_access_public_link(
    container: FlowContainer,
    flows_service,
    frontend_container,
    mock_llm_with_queue: MockLLMQueue,
    unique_id: str,
) -> None:
    _ = flows_service
    employee, company, employee_user_id, namespace = await _prepare_employee(
        frontend_container=frontend_container,
        unique_id=unique_id,
        flow_suffix="access",
    )
    with _employee_context(employee, company, namespace=namespace):
        await _seed_lara_skills(container)

    result1 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-p",
        queue=[
            *_load("wiki-platform", "wiki-pages", "wiki-access", "team-directory"),
            _call(
                "wiki_create_page",
                title=f"Public {unique_id}",
                markdown=f"# Public {unique_id}",
            ),
            _text("page ready"),
        ],
    )
    created = _ok_tool(result1, "wiki_create_page")
    wiki_page_id = _require_str(created, "wiki_page_id")

    result2 = await _turn(
        container=container,
        mock_llm_with_queue=mock_llm_with_queue,
        employee=employee,
        company=company,
        namespace=namespace,
        unique_id=unique_id,
        employee_user_id=employee_user_id,
        suffix="-l",
        queue=[
            *_load("wiki-platform", "wiki-pages", "wiki-access"),
            _call("wiki_update_properties", wiki_page_id=wiki_page_id, is_published=True),
            _call("wiki_get_access", wiki_page_id=wiki_page_id),
            _call(
                "wiki_rotate_public_link",
                wiki_page_id=wiki_page_id,
                enabled=True,
                permission="view",
            ),
            _text("link ready"),
        ],
    )
    access = _ok_tool(result2, "wiki_get_access")
    assert access.get("wiki_page_id") == wiki_page_id
    rotated = _ok_tool(result2, "wiki_rotate_public_link")
    assert rotated.get("enabled") is True
    url = rotated.get("url")
    assert isinstance(url, str) and "/wiki/s/" in url
