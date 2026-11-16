"""CLI проходит validate, push, повторный push с base_version и запуск code-flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from platform_sdk.commands import cmd_push, cmd_run, cmd_schema_pull, cmd_validate
from platform_sdk.context_store import PlatformContext
from platform_sdk.errors import PlatformCliError
from platform_sdk.http import PlatformClient
from platform_sdk.project import read_lock

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(90)]

_FLOW = """\
flow_id: {flow_id}
name: CLI cycle
description: ""
entry: main
nodes:
  main:
    type: code
    language: python
    prompt: prompts/main.md
    code: |
      async def run(args, state):
          state["response"] = "ok"
          return state
edges:
  - from_node: main
    to_node: null
"""


def _client(http_client) -> PlatformClient:
    header = http_client.headers.get("authorization") or http_client.headers.get("Authorization")
    token = str(header).removeprefix("Bearer ").strip()
    context = PlatformContext(
        name="test",
        host="http://test",
        api_key=token,
        company_subdomain="system",
    )
    return PlatformClient(context, timeout=60, http=http_client)


async def test_push_is_idempotent_until_the_graph_changes(
    client, unique_id: str, tmp_path: Path
) -> None:
    flow_id = f"cli_cycle_{unique_id}"
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "main.md").write_text("unused\n", encoding="utf-8")
    (tmp_path / "flow.yaml").write_text(_FLOW.format(flow_id=flow_id), encoding="utf-8")
    sdk = _client(client)
    await cmd_schema_pull(sdk, tmp_path)
    assert await cmd_validate(sdk, tmp_path) == 0
    assert await cmd_push(sdk, tmp_path, force_base=False) == 0
    first = read_lock(tmp_path)["base_version"]
    assert await cmd_push(sdk, tmp_path, force_base=False) == 0
    assert read_lock(tmp_path)["base_version"] == first
    prompt = tmp_path / "prompts" / "main.md"
    prompt.write_text("changed\n", encoding="utf-8")
    # code node ignores the prompt; change the code file path by rewriting flow code inline via yaml
    text = (
        (tmp_path / "flow.yaml")
        .read_text(encoding="utf-8")
        .replace(
            'state["response"] = "ok"',
            'state["response"] = "ready"',
        )
    )
    (tmp_path / "flow.yaml").write_text(text, encoding="utf-8")
    assert await cmd_push(sdk, tmp_path, force_base=False) == 0
    assert read_lock(tmp_path)["base_version"] != first
    code = await cmd_run(
        sdk,
        flow_id=flow_id,
        text="hi",
        branch=None,
        variables={},
        files=[],
        context_id=None,
        breakpoints=[],
        detach=False,
    )
    assert code == 0
    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_push_reports_conflict_when_lock_is_stale(
    client, unique_id: str, tmp_path: Path
) -> None:
    flow_id = f"cli_conflict_{unique_id}"
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "main.md").write_text("one\n", encoding="utf-8")
    (tmp_path / "flow.yaml").write_text(_FLOW.format(flow_id=flow_id), encoding="utf-8")
    sdk = _client(client)
    assert await cmd_push(sdk, tmp_path, force_base=False) == 0
    lock_path = tmp_path / ".platform" / "lock.json"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace(
            str(read_lock(tmp_path)["base_version"]),
            "19990101000000000000",
        ),
        encoding="utf-8",
    )
    text = (tmp_path / "flow.yaml").read_text(encoding="utf-8").replace("CLI cycle", "CLI cycle 2")
    (tmp_path / "flow.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(PlatformCliError) as caught:
        await cmd_push(sdk, tmp_path, force_base=False)
    assert caught.value.exit_code == 6
    assert caught.value.error_code == "flow_version_conflict"
    await client.delete(f"/flows/api/v1/flows/{flow_id}")
