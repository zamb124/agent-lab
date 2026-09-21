"""E2E: привычные библиотеки и синтаксис isolated code runners."""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient

from core.capabilities import (
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionKind,
    CodeExecutionRequest,
    CodeValidationRequest,
    execution_token_exp,
    issue_execution_token,
    locked_down_code_sandbox_policy,
)
from core.types import JsonObject
from tests.capabilities.capability_language_helpers import fetch_manifest

pytestmark = pytest.mark.timeout(180)

RUNNER_EXECUTE = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/execute"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/execute"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/execute"),
}
RUNNER_VALIDATE = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/validate"),
}


def _execution_context() -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="test_user",
        flow_id="test_flow",
        branch_id="main",
        session_id="test_flow:test_context",
        task_id="test_task",
        context_id="test_context",
        channel="a2a",
        request_id="familiar-request-id",
        exp=execution_token_exp(300),
    )
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
        request_id=claims.request_id,
        trace_id="familiar-trace-id",
    )


def _execute_payload(
    language: CapabilityLanguage,
    code: str,
    *,
    entrypoint: str | None = None,
    kind: CodeExecutionKind = "node",
    args: JsonObject | None = None,
    state: JsonObject | None = None,
    manifest: CapabilityManifest | None = None,
    wall_time_limit_seconds: int = 30,
    memory_limit_mb: int = 256,
) -> dict[str, object]:
    request = CodeExecutionRequest(
        kind=kind,
        language=language,
        code=code,
        entrypoint=entrypoint,
        wall_time_limit_seconds=wall_time_limit_seconds,
        sandbox=locked_down_code_sandbox_policy(
            wall_time_limit_seconds=wall_time_limit_seconds,
            cpu_time_limit_seconds=wall_time_limit_seconds,
            memory_limit_mb=memory_limit_mb,
            filesystem_limit_mb=64,
            stdout_stderr_limit_bytes=1_048_576,
        ),
        args=args or {},
        state=state or {},
        context=_execution_context(),
        capability_manifest=manifest or CapabilityManifest(version="test", capabilities=[]),
    )
    return request.model_dump(mode="json")


def _validate_payload(language: CapabilityLanguage, code: str) -> dict[str, object]:
    wall_time_limit_seconds = 30
    request = CodeValidationRequest(
        kind="node",
        language=language,
        code=code,
        entrypoint=None,
        wall_time_limit_seconds=wall_time_limit_seconds,
        sandbox=locked_down_code_sandbox_policy(
            wall_time_limit_seconds=wall_time_limit_seconds,
            cpu_time_limit_seconds=wall_time_limit_seconds,
            memory_limit_mb=256,
            filesystem_limit_mb=64,
            stdout_stderr_limit_bytes=1_048_576,
        ),
        context=_execution_context(),
        capability_manifest=CapabilityManifest(version="test", capabilities=[]),
    )
    return request.model_dump(mode="json")


async def _post_execute(
    sandbox_services: dict[str, str],
    language: CapabilityLanguage,
    payload: dict[str, object],
    *,
    timeout: float = 60.0,
) -> dict[str, object]:
    service_name, path = RUNNER_EXECUTE[language]
    async with AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{sandbox_services[service_name]}{path}",
            json=payload,
            headers={"X-Request-Id": "familiar-request-id", "X-Trace-Id": "familiar-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert isinstance(body, dict)
    return cast(dict[str, object], body)


@pytest.mark.asyncio
async def test_python_execute_csv_json_pathlib(sandbox_services) -> None:
    code = (
        "import csv\n"
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "async def run(args, state):\n"
        "    joined = (Path('reports') / 'export.csv').as_posix()\n"
        "    suffix = Path('export.csv').suffix\n"
        '    rows = list(csv.reader(["a,b", "1,2"]))\n'
        "    payload = json.dumps({'rows': rows, 'path': joined, 'suffix': suffix})\n"
        "    return json.loads(payload)\n"
    )
    body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert body["status"] == "completed", body
    result = body["result"]
    assert isinstance(result, dict)
    assert result["suffix"] == ".csv"
    assert result["path"] == "reports/export.csv"
    assert result["rows"] == [["a", "b"], ["1", "2"]]


@pytest.mark.asyncio
async def test_python_execute_pandas_dataframe(sandbox_services) -> None:
    code = (
        "import pandas\n"
        "\n"
        "async def run(args, state):\n"
        "    frame = pandas.DataFrame({'n': [1, 2]})\n"
        "    return {'rows': int(len(frame)), 'sum': int(frame['n'].sum())}\n"
    )
    body = await _post_execute(
        sandbox_services,
        "python",
        _execute_payload("python", code, wall_time_limit_seconds=60, memory_limit_mb=512),
        timeout=90.0,
    )
    assert body["status"] == "completed", body
    assert body["result"] == {"rows": 2, "sum": 3}


@pytest.mark.asyncio
async def test_python_execute_zipfile_bs4_email(sandbox_services) -> None:
    code = (
        "import zipfile\n"
        "from email.message import EmailMessage\n"
        "from io import BytesIO\n"
        "from bs4 import BeautifulSoup\n"
        "\n"
        "async def run(args, state):\n"
        "    buffer = BytesIO()\n"
        "    with zipfile.ZipFile(buffer, 'w') as archive:\n"
        "        archive.writestr('a.txt', 'hello')\n"
        "    message = EmailMessage()\n"
        "    message['Subject'] = 'hi'\n"
        "    soup = BeautifulSoup('<p>ok</p>', 'html.parser')\n"
        "    return {\n"
        "        'zip_files': zipfile.ZipFile(BytesIO(buffer.getvalue())).namelist(),\n"
        "        'subject': str(message['Subject']),\n"
        "        'text': soup.get_text(),\n"
        "    }\n"
    )
    body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert body["status"] == "completed", body
    assert body["result"] == {"zip_files": ["a.txt"], "subject": "hi", "text": "ok"}


@pytest.mark.asyncio
async def test_python_execute_rejects_requests(sandbox_services) -> None:
    code = (
        "import requests\n"
        "\n"
        "async def run(args, state):\n"
        "    return {'ok': True}\n"
    )
    body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert body["status"] == "failed", body
    error = body["error"]
    assert isinstance(error, dict)
    assert "import is not allowed" in str(error["message"])
    assert "requests" in str(error["message"])


@pytest.mark.asyncio
async def test_python_validate_rejects_apps_flowinterrupt_import(sandbox_services) -> None:
    code = (
        "from apps.flows.src.runtime.exceptions import FlowInterrupt\n"
        "\n"
        "async def run(args, state):\n"
        "    raise FlowInterrupt(question='nope')\n"
    )
    service_name, path = RUNNER_VALIDATE["python"]
    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services[service_name]}{path}",
            json=_validate_payload("python", code),
            headers={"X-Request-Id": "familiar-request-id", "X-Trace-Id": "familiar-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["valid"] is False
    assert "import is not allowed" in body["error"]["message"]


@pytest.mark.asyncio
async def test_python_execute_raise_flowinterrupt(sandbox_services) -> None:
    code = (
        "async def run(args, state):\n"
        "    raise FlowInterrupt(question='Need a name')\n"
    )
    body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert body["status"] == "interrupted", body
    interrupt = body["interrupt"]
    assert isinstance(interrupt, dict)
    assert interrupt["kind"] == "user_message"
    assert interrupt["body"]["question"] == "Need a name"


@pytest.mark.asyncio
async def test_python_first_function_is_entrypoint(sandbox_services) -> None:
    code = (
        "def helper(args, state):\n"
        "    return {'who': 'helper'}\n"
        "\n"
        "async def run(args, state):\n"
        "    return {'who': 'run'}\n"
    )
    default_body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert default_body["status"] == "completed", default_body
    assert default_body["result"] == {"who": "helper"}

    named_body = await _post_execute(
        sandbox_services,
        "python",
        _execute_payload("python", code, entrypoint="run"),
    )
    assert named_body["status"] == "completed", named_body
    assert named_body["result"] == {"who": "run"}


@pytest.mark.asyncio
async def test_python_import_wiki_sdk_module(sandbox_services) -> None:
    manifest = CapabilityManifest.model_validate(await fetch_manifest(sandbox_services))
    code = (
        "import wiki\n"
        "from files import read\n"
        "\n"
        "async def run(args, state):\n"
        "    return {\n"
        "        'wiki_create': callable(wiki.create_page),\n"
        "        'files_read': callable(read),\n"
        "    }\n"
    )
    body = await _post_execute(
        sandbox_services,
        "python",
        _execute_payload("python", code, manifest=manifest),
    )
    assert body["status"] == "completed", body
    assert body["result"] == {"wiki_create": True, "files_read": True}


@pytest.mark.asyncio
async def test_javascript_json_date_map(sandbox_services) -> None:
    code = (
        "async function run(args, state) {\n"
        "  const parsed = JSON.parse('{\"n\": 1}');\n"
        "  const stamp = new Date('2020-01-01T00:00:00.000Z').toISOString();\n"
        "  const mapped = new Map([['k', 2]]);\n"
        "  return {n: parsed.n, stamp, mapped: mapped.get('k')};\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "javascript", _execute_payload("javascript", code))
    assert body["status"] == "completed", body
    assert body["result"] == {"n": 1, "stamp": "2020-01-01T00:00:00.000Z", "mapped": 2}


@pytest.mark.asyncio
async def test_javascript_lodash_static_import(sandbox_services) -> None:
    code = (
        "import lodash from 'lodash';\n"
        "\n"
        "async function run(args, state) {\n"
        "  return {sum: lodash.sum([1, 2, 3])};\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "javascript", _execute_payload("javascript", code))
    assert body["status"] == "completed", body
    assert body["result"] == {"sum": 6}


@pytest.mark.asyncio
async def test_javascript_uuid_date_fns_and_crypto(sandbox_services) -> None:
    code = (
        "import { v4 } from 'uuid';\n"
        "import { format } from 'date-fns';\n"
        "\n"
        "async function run(args, state) {\n"
        "  const id = v4();\n"
        "  const day = format(new Date(Date.UTC(2020, 0, 2)), 'yyyy-MM-dd');\n"
        "  const hex = crypto.getRandomValues(new Uint8Array(4)).length;\n"
        "  return {uuid: id.length === 36, day, hex, cloned: structuredClone({n: 1}).n};\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "javascript", _execute_payload("javascript", code))
    assert body["status"] == "completed", body
    assert body["result"] == {"uuid": True, "day": "2020-01-02", "hex": 4, "cloned": 1}


@pytest.mark.asyncio
async def test_csharp_json_serializer_roundtrip(sandbox_services) -> None:
    code = (
        "using System.Collections.Generic;\n"
        "using System.Text.Json;\n"
        "using System.Threading.Tasks;\n\n"
        "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
        "{\n"
        "    var json = JsonSerializer.Serialize(new Dictionary<string, int> { [\"n\"] = 1 });\n"
        "    return new Dictionary<string, object?> { [\"json\"] = json };\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "csharp", _execute_payload("csharp", code))
    assert body["status"] == "completed", body
    result = body["result"]
    assert isinstance(result, dict)
    json_text = result.get("json")
    assert isinstance(json_text, str)
    assert '"n":1' in json_text.replace(" ", "")


@pytest.mark.asyncio
async def test_python_execute_frozenset_hash_slice_and_stdlib(sandbox_services) -> None:
    code = (
        "import hmac\n"
        "import secrets\n"
        "import tomllib\n"
        "from contextlib import nullcontext\n"
        "\n"
        "async def run(args, state):\n"
        "    frozen = frozenset({1, 2})\n"
        "    with nullcontext():\n"
        "        parsed = tomllib.loads('n = 1\\n')\n"
        "    return {\n"
        "        'frozen': sorted(frozen),\n"
        "        'hashed': hash('x') == hash('x'),\n"
        "        'sliced': list(range(5)[slice(1, 3)]),\n"
        "        'hex': hmac.new(b'k', b'm', 'sha256').hexdigest()[:8],\n"
        "        'token_len': len(secrets.token_hex(4)),\n"
        "        'toml_n': parsed['n'],\n"
        "    }\n"
    )
    body = await _post_execute(sandbox_services, "python", _execute_payload("python", code))
    assert body["status"] == "completed", body
    result = body["result"]
    assert isinstance(result, dict)
    assert result["frozen"] == [1, 2]
    assert result["hashed"] is True
    assert result["sliced"] == [1, 2]
    assert isinstance(result["hex"], str) and len(result["hex"]) == 8
    assert result["token_len"] == 8
    assert result["toml_n"] == 1


@pytest.mark.asyncio
async def test_javascript_typed_array_and_intl(sandbox_services) -> None:
    code = (
        "async function run(args, state) {\n"
        "  const bytes = new Uint8Array(new ArrayBuffer(2));\n"
        "  bytes[0] = 7;\n"
        "  const formatted = new Intl.NumberFormat('en-US').format(1234);\n"
        "  return {len: bytes.byteLength, first: bytes[0], formatted};\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "javascript", _execute_payload("javascript", code))
    assert body["status"] == "completed", body
    assert body["result"] == {"len": 2, "first": 7, "formatted": "1,234"}


@pytest.mark.asyncio
async def test_csharp_regex_ismatch(sandbox_services) -> None:
    code = (
        "using System.Collections.Generic;\n"
        "using System.Text.RegularExpressions;\n"
        "using System.Threading.Tasks;\n\n"
        "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
        "{\n"
        "    return new Dictionary<string, object?> { [\"ok\"] = Regex.IsMatch(\"abc123\", @\"\\d+\") };\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "csharp", _execute_payload("csharp", code))
    assert body["status"] == "completed", body
    result = body["result"]
    assert isinstance(result, dict)
    assert result.get("ok") is True


@pytest.mark.asyncio
async def test_go_execute_encoding_xml(sandbox_services) -> None:
    code = (
        "package main\n\n"
        'import "encoding/xml"\n\n'
        "func run(args map[string]any, state map[string]any) (any, error) {\n"
        "    type row struct {\n"
        "        XMLName xml.Name `xml:\"row\"`\n"
        "        Name    string   `xml:\"name\"`\n"
        "    }\n"
        "    payload, err := xml.Marshal(row{Name: \"ok\"})\n"
        "    if err != nil {\n"
        "        return nil, err\n"
        "    }\n"
        "    return map[string]any{\"xml\": string(payload)}, nil\n"
        "}\n"
    )
    body = await _post_execute(sandbox_services, "go", _execute_payload("go", code))
    assert body["status"] == "completed", body
    result = body["result"]
    assert isinstance(result, dict)
    assert "<name>ok</name>" in str(result.get("xml"))
