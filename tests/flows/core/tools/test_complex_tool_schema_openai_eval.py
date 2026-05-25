"""
Сложные JSON Schema параметров тулов: канон OpenAI function calling и исполнение в eval.

Проверяем:
- полная схема из Pydantic (вложенные объекты, массивы с items, $ref/$defs, oneOf/discriminator,
  default/minimum/exclusiveMinimum, optional anyOf+null);
- CodeTool.parameters / to_openai_schema();
- materialize из dict (как после merge с tool_repository);
- LlmNodeRunner._build_tools_schema() — тот же payload, что уходит в LLM;
- распаковка аргументов и defaults в CodeTool._apply_defaults + execute_tool.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional, Union

import pytest
from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.models import NodeConfig
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.tools.code_tool import CodeTool
from apps.flows.src.tools.json_schema_parameters import (
    pydantic_model_to_parameters_schema,
    sanitize_parameters_schema_for_llm,
)
from apps.flows.tools.lara_crm import CrmSearchEntitiesArgs
from core.state import ExecutionState


def _json_pointer_resolve(root: Dict[str, Any], pointer: str) -> Dict[str, Any]:
    if not pointer.startswith("#/"):
        raise AssertionError(f"Ожидался pointer с #/: {pointer!r}")
    cur: Any = root
    for part in pointer[2:].split("/"):
        if part not in cur:
            raise AssertionError(f"Pointer {pointer!r}: нет ключа {part!r}")
        cur = cur[part]
    if not isinstance(cur, dict):
        raise AssertionError(f"Pointer {pointer!r}: ожидался object, получили {type(cur)}")
    return cur


def _assert_schema_fragment(fragment: Dict[str, Any], root: Dict[str, Any], *, path: str) -> None:
    """Рекурсивно: фрагмент JSON Schema допустим для parameters функции (OpenAI-style)."""
    if not isinstance(fragment, dict):
        raise AssertionError(f"{path}: ожидался dict")
    if "$ref" in fragment:
        _assert_schema_fragment(
            _json_pointer_resolve(root, fragment["$ref"]), root, path=f"{path}($ref)"
        )
        return
    if "oneOf" in fragment:
        opts = fragment["oneOf"]
        assert isinstance(opts, list) and len(opts) > 0, f"{path}: oneOf непустой список"
        for i, opt in enumerate(opts):
            assert isinstance(opt, dict), f"{path}.oneOf[{i}]"
            _assert_schema_fragment(opt, root, path=f"{path}.oneOf[{i}]")
        return
    if "anyOf" in fragment:
        opts = fragment["anyOf"]
        assert isinstance(opts, list) and len(opts) > 0, f"{path}: anyOf"
        for i, opt in enumerate(opts):
            assert isinstance(opt, dict), f"{path}.anyOf[{i}]"
            _assert_schema_fragment(opt, root, path=f"{path}.anyOf[{i}]")
        return
    if "allOf" in fragment:
        for i, sub in enumerate(fragment["allOf"]):
            assert isinstance(sub, dict), f"{path}.allOf[{i}]"
            _assert_schema_fragment(sub, root, path=f"{path}.allOf[{i}]")
        return
    if "const" in fragment:
        return
    t = fragment.get("type")
    if t == "array":
        assert "items" in fragment, f"{path}: type=array требует items (OpenAI / JSON Schema)"
        assert isinstance(fragment["items"], dict), f"{path}.items"
        _assert_schema_fragment(fragment["items"], root, path=f"{path}.items")
        return
    if t == "object":
        if "properties" in fragment:
            assert isinstance(fragment["properties"], dict), f"{path}.properties"
            for name, prop in fragment["properties"].items():
                assert isinstance(prop, dict), f"{path}.properties.{name}"
                _assert_schema_fragment(prop, root, path=f"{path}.properties.{name}")
        elif "additionalProperties" in fragment:
            ap = fragment["additionalProperties"]
            assert isinstance(ap, (dict, bool)), f"{path}.additionalProperties"
            if isinstance(ap, dict):
                _assert_schema_fragment(ap, root, path=f"{path}.additionalProperties")
        else:
            raise AssertionError(f"{path}: type=object ожидает properties или additionalProperties")
        return
    if t in ("string", "number", "integer", "boolean", "null"):
        return
    if t is None and (
        not any(
            (
                k in fragment
                for k in ("properties", "items", "oneOf", "anyOf", "allOf", "$ref", "const")
            )
        )
    ):
        raise AssertionError(f"{path}: нет type и нет составной конструкции: keys={list(fragment)}")
    if isinstance(t, list):
        for i, tt in enumerate(t):
            assert tt in ("string", "number", "integer", "boolean", "null", "object", "array"), (
                f"{path}.type[{i}]"
            )
        return
    raise AssertionError(f"{path}: неподдерживаемый type={t!r}")


def assert_openai_function_parameters_compatible(parameters: Dict[str, Any]) -> None:
    """Проверка объекта function.parameters для Chat Completions tools."""
    assert parameters.get("type") == "object", "parameters.type должен быть object"
    props = parameters.get("properties")
    assert isinstance(props, dict), "parameters.properties — dict"
    req = parameters.get("required", [])
    assert isinstance(req, list), "parameters.required — list"
    assert all((isinstance(x, str) for x in req)), "required — только строки"
    for name in req:
        assert name in props, f"required ссылается на неизвестное поле {name!r}"
    root = parameters
    for pname, pschema in props.items():
        _assert_schema_fragment(pschema, root, path=f"properties.{pname}")


def assert_openai_tools_list_entry(entry: Dict[str, Any]) -> None:
    assert entry.get("type") == "function"
    fn = entry.get("function")
    assert isinstance(fn, dict), "function — object"
    assert isinstance(fn.get("name"), str) and fn["name"].strip(), "function.name — непустая строка"
    assert isinstance(fn.get("description"), str), "function.description — строка"
    params = fn.get("parameters")
    assert isinstance(params, dict), "function.parameters — object"
    assert_openai_function_parameters_compatible(params)


class Coord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ComplexArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=1000)
    ratio: float = Field(default=0.25, gt=0, lt=1)
    tags: List[str] = Field(min_length=1, max_length=4)
    coord: Coord
    extras: Optional[Dict[str, str]] = None


class VariantA(BaseModel):
    kind: Literal["a"] = "a"
    value_a: str


class VariantB(BaseModel):
    kind: Literal["b"] = "b"
    value_b: int


class RootUnion(BaseModel):
    item: Union[VariantA, VariantB] = Field(discriminator="kind")


COMPLEX_TOOL_CODE = '\nasync def complex_demo(\n    title: str,\n    tags: list,\n    coord: dict,\n    count: int = 10,\n    ratio: float = 0.25,\n    extras: dict | None = None,\n    state=None,\n):\n    import json\n    return json.dumps(\n        {\n            "title": title,\n            "count": count,\n            "ratio": ratio,\n            "tags": tags,\n            "coord": coord,\n            "extras": extras,\n        },\n        ensure_ascii=False,\n    )\n'


def test_sanitize_preserves_defs_and_constraints() -> None:
    raw = pydantic_model_to_parameters_schema(ComplexArgs)
    assert raw["type"] == "object"
    assert "$defs" in raw
    assert "Coord" in raw["$defs"]
    props = raw["properties"]
    assert props["title"].get("minLength") == 1
    assert props["count"].get("default") == 10
    assert props["count"].get("minimum") == 1
    assert props["ratio"].get("exclusiveMinimum") == 0
    assert props["tags"].get("type") == "array"
    assert props["tags"]["items"].get("type") == "string"
    assert props["tags"].get("minItems") == 1
    assert props["coord"].get("$ref") == "#/$defs/Coord"


def test_openai_compatible_complex_parameters_schema() -> None:
    params = pydantic_model_to_parameters_schema(ComplexArgs)
    assert_openai_function_parameters_compatible(params)


def test_openai_compatible_discriminated_union_schema() -> None:
    params = pydantic_model_to_parameters_schema(RootUnion)
    assert params["properties"]["item"].get("discriminator", {}).get("propertyName") == "kind"
    assert "oneOf" in params["properties"]["item"]
    assert_openai_function_parameters_compatible(params)


def test_crm_search_entities_schema_openai_compatible() -> None:
    params = pydantic_model_to_parameters_schema(CrmSearchEntitiesArgs)
    assert_openai_function_parameters_compatible(params)
    lim = params["properties"]["limit"]
    assert lim.get("type") == "integer"
    assert lim.get("default") == 100
    assert lim.get("minimum") == 1
    assert lim.get("maximum") == 1000


def test_tool_reference_rejects_legacy_flat_schema() -> None:
    legacy_key = "args" + "_schema"
    with pytest.raises(ValueError):
        ToolReference.model_validate(
            {
                "tool_id": "legacy_schema",
                "code": "async def run(args, state): return args",
                legacy_key: {"x": {"type": "string"}},
            }
        )


@pytest.mark.asyncio
async def test_code_tool_to_openai_schema_complex_parameters_schema(app) -> None:
    schema = sanitize_parameters_schema_for_llm(pydantic_model_to_parameters_schema(ComplexArgs))
    tool = CodeTool(
        tool_id="complex_openai_tool",
        code=COMPLEX_TOOL_CODE.strip(),
        description="Сложный демо-тул",
        parameters_schema=schema,
    )
    wrapped = tool.to_openai_schema()
    assert_openai_tools_list_entry(wrapped)


@pytest.mark.asyncio
async def test_registry_materialize_merges_full_parameters_schema(app) -> None:
    from apps.flows.src.container import get_container

    schema = sanitize_parameters_schema_for_llm(pydantic_model_to_parameters_schema(ComplexArgs))
    ref = ToolReference(
        tool_id="mat_complex_schema",
        description="materialize complex",
        code=COMPLEX_TOOL_CODE.strip(),
        parameters_schema=schema,
    )
    dumped = ref.model_dump(exclude_none=True)
    tool = await get_container().tool_registry.materialize(dumped)
    assert isinstance(tool, CodeTool)
    assert_openai_tools_list_entry(tool.to_openai_schema())


@pytest.mark.asyncio
async def test_llm_node_runner_build_tools_schema_matches_openai_canon(app) -> None:
    schema = sanitize_parameters_schema_for_llm(pydantic_model_to_parameters_schema(ComplexArgs))
    complex_tool = CodeTool(
        tool_id="runner_complex_tool",
        code=COMPLEX_TOOL_CODE.strip(),
        description="runner complex",
        parameters_schema=schema,
    )
    cfg = NodeConfig(
        node_id="n1",
        type="llm_node",
        name="Agent",
        prompt="p",
        llm=NodeLLMConfig(model="mock-gpt-4", temperature=0.0),
    )
    runner = LlmNodeRunner(node_config=cfg, tools=[complex_tool], llm=None, prompt="p")
    built = runner._build_tools_schema()
    assert len(built) == 1
    assert_openai_tools_list_entry(built[0])
    fn = built[0]["function"]
    assert fn["name"] == "runner_complex_tool"
    lim_props = fn["parameters"]["properties"]
    assert "coord" in lim_props
    assert "$ref" in lim_props["coord"] or "properties" in lim_props.get("coord", {})


@pytest.mark.asyncio
async def test_code_tool_run_applies_json_defaults_and_executes(app) -> None:
    from apps.flows.src.container import get_container

    schema = sanitize_parameters_schema_for_llm(pydantic_model_to_parameters_schema(ComplexArgs))
    tool = CodeTool(
        tool_id="complex_exec",
        code=COMPLEX_TOOL_CODE.strip(),
        description="exec",
        parameters_schema=schema,
        container=get_container(),
    )
    state = ExecutionState.create(task_id="t1", context_id="c1", user_id="u1", session_id="flow:c1")
    payload = {"title": "Заголовок", "tags": ["one", "two"], "coord": {"lat": 55.75, "lon": 37.62}}
    raw = await tool.run(payload, state)
    data = json.loads(raw)
    assert data["title"] == "Заголовок"
    assert data["tags"] == ["one", "two"]
    assert data["coord"] == {"lat": 55.75, "lon": 37.62}
    assert data["count"] == 10
    assert data["ratio"] == 0.25
    assert data["extras"] is None


@pytest.mark.asyncio
async def test_code_tool_explicit_args_override_defaults(app) -> None:
    from apps.flows.src.container import get_container

    schema = sanitize_parameters_schema_for_llm(pydantic_model_to_parameters_schema(ComplexArgs))
    tool = CodeTool(
        tool_id="complex_exec2",
        code=COMPLEX_TOOL_CODE.strip(),
        description="exec2",
        parameters_schema=schema,
        container=get_container(),
    )
    state = ExecutionState.create(task_id="t2", context_id="c2", user_id="u1", session_id="flow:c2")
    payload = {
        "title": "T",
        "tags": ["x"],
        "coord": {"lat": 0.0, "lon": 0.0},
        "count": 42,
        "ratio": 0.9,
        "extras": {"k": "v"},
    }
    raw = await tool.run(payload, state)
    data = json.loads(raw)
    assert data["count"] == 42
    assert data["ratio"] == 0.9
    assert data["extras"] == {"k": "v"}
