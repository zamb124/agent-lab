"""OpenAI-compat: multimodal tool-result → tool text + user interleaved Image labels."""

from __future__ import annotations

from a2a.types import Part, Role

from core.clients.llm.messages import build_a2a_message, messages_to_openai
from core.files.reader.parts import nested_image_label


def test_nested_image_label_format() -> None:
    assert nested_image_label("p0_n1") == "Image p0_n1:"


def test_messages_to_openai_splits_tool_images_into_user() -> None:
    tool_message = build_a2a_message(
        role=Role.ROLE_AGENT,
        parts=[
            Part(text='{"tool":"read_file","files":[]}'),
            Part(text=nested_image_label("p0_n1")),
            Part(raw=b"\x89PNG\r\n\x1a\n", media_type="image/png", filename="menu.pdf#p0_n1"),
            Part(text=nested_image_label("p0_n2")),
            Part(raw=b"\x89PNG\r\n\x1a\n", media_type="image/png", filename="menu.pdf#p0_n2"),
        ],
        metadata={"tool_call_id": "call_read_1"},
    )
    openai_messages = messages_to_openai([tool_message])
    assert len(openai_messages) == 2
    tool_wire = openai_messages[0]
    user_wire = openai_messages[1]
    assert tool_wire["role"] == "tool"
    assert tool_wire["tool_call_id"] == "call_read_1"
    assert tool_wire["content"] == '{"tool":"read_file","files":[]}'
    assert user_wire["role"] == "user"
    content = user_wire["content"]
    assert isinstance(content, list)
    assert content == [
        {"type": "text", "text": "Image p0_n1:"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
        },
        {"type": "text", "text": "Image p0_n2:"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
        },
    ]


def test_messages_to_openai_tool_text_only_unchanged() -> None:
    tool_message = build_a2a_message(
        role=Role.ROLE_AGENT,
        parts=[Part(text="42")],
        metadata={"tool_call_id": "call_1"},
    )
    assert messages_to_openai([tool_message]) == [
        {"role": "tool", "tool_call_id": "call_1", "content": "42"}
    ]
