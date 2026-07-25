"""ToolReference: editor payload (type/code + mapping) → runtime validate."""

from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.tool_reference import ToolReference


def test_tool_reference_accepts_editor_code_payload_with_mapping() -> None:
    ref = ToolReference.model_validate(
        {
            "tool_id": "ask_user",
            "type": "code",
            "name": "ask_user",
            "code": "async def ask_user(args, state):\n    return args\n",
            "language": "python",
            "parameters_schema": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
            "input_mapping": {"question": "как дела?"},
        }
    )
    assert ref.tool_id == "ask_user"
    assert ref.input_mapping == {"question": "как дела?"}
    assert ref.code is not None
    assert "ask_user" in ref.code
    assert ref.code_mode == CodeMode.INLINE_CODE


def test_tool_reference_strips_mcp_type_for_inline_shaped_ref() -> None:
    ref = ToolReference.model_validate(
        {
            "tool_id": "calculator",
            "type": "mcp",
            "code": "async def calculator(args, state):\n    return args\n",
            "input_mapping": {"query": "hello"},
            "state_mapping": {"result": "out"},
        }
    )
    assert ref.tool_id == "calculator"
    assert ref.input_mapping == {"query": "hello"}
    assert ref.state_mapping == {"result": "out"}
