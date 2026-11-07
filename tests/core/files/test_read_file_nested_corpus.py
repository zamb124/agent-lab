"""nested_mode=parts на multimodal-файлах Unstructured example-docs."""

from __future__ import annotations

import pytest
from a2a.types import Part, Role

from core.clients.llm.messages import build_a2a_message, messages_to_openai
from core.files.file_ref import FileRef
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.models import NestedMode, ReadFileArgs
from core.files.reader.parts import nested_image_label, parts_from_file_results
from core.files.types import ext_to_mime
from core.types import require_json_object
from tests.core.files.corpus.manifest import CORPUS_DIR

# Файлы с встроенными картинками из unstructured/example-docs (text-lane, без vision).
_MULTIMODAL_EMBEDDED: tuple[tuple[str, int], ...] = (
    ("pdf/embedded-images.pdf", 3),
    ("pdf/embedded-images-tables.pdf", 1),
    ("contains-pictures.docx", 3),
)


def _corpus_file_ref(relative_path: str) -> FileRef:
    path = CORPUS_DIR / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Файл отсутствует в корпусе: {relative_path}")
    raw = path.read_bytes()
    mime = ext_to_mime(path.suffix.lower())
    if not mime:
        raise ValueError(f"нет MIME для {path.suffix!r}")
    return FileRef(
        original_name=path.name,
        url=str(path),
        content_type=mime,
        file_size=len(raw),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relative_path", "min_nested"),
    _MULTIMODAL_EMBEDDED,
    ids=[relative_path for relative_path, _ in _MULTIMODAL_EMBEDDED],
)
async def test_corpus_parts_yields_interleaved_image_parts(
    relative_path: str,
    min_nested: int,
) -> None:
    file_ref = _corpus_file_ref(relative_path)
    envelope = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(names=[file_ref.original_name], nested_mode=NestedMode.PARTS),
        tool_name="read_file",
    )
    file_result = envelope.files[0]
    assert file_result.success is True
    assert len(file_result.nested) >= min_nested
    md = file_result.results[0].result
    assert "![" in md

    parts = parts_from_file_results(envelope.files)
    assert len(parts) >= min_nested * 2
    assert len(parts) % 2 == 0

    for index in range(0, len(parts), 2):
        label = parts[index]
        image = parts[index + 1]
        nested = file_result.nested[index // 2]
        assert label.text == nested_image_label(nested.anchor)
        assert image.media_type is not None and image.media_type.startswith("image/")
        assert image.filename == nested.original_name
        assert nested.original_name.startswith(file_ref.original_name + "#")
        assert f"![{nested.anchor}]" in md

    envelope_json = '{"tool":"read_file","files":[]}'
    openai_messages = messages_to_openai(
        [
            build_a2a_message(
                role=Role.ROLE_AGENT,
                parts=[Part(text=envelope_json), *parts],
                metadata={"tool_call_id": "call_corpus_read"},
            )
        ]
    )
    assert len(openai_messages) == 2
    tool_wire = require_json_object(openai_messages[0], "tool_wire")
    user_wire = require_json_object(openai_messages[1], "user_wire")
    assert tool_wire["role"] == "tool"
    assert tool_wire["content"] == envelope_json
    assert user_wire["role"] == "user"
    content = user_wire["content"]
    assert isinstance(content, list)
    assert len(content) == len(parts)
    for index in range(0, len(content), 2):
        text_part = require_json_object(content[index], f"user_content[{index}]")
        image_part = require_json_object(content[index + 1], f"user_content[{index + 1}]")
        assert text_part["type"] == "text"
        assert text_part["text"] == parts[index].text
        assert image_part["type"] == "image_url"
        image_url = require_json_object(image_part["image_url"], f"image_url[{index + 1}]")
        url = image_url["url"]
        assert isinstance(url, str)
        assert url.startswith("data:image/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relative_path",
    [relative_path for relative_path, _ in _MULTIMODAL_EMBEDDED],
)
async def test_corpus_refs_keeps_nested_without_parts(
    relative_path: str,
) -> None:
    file_ref = _corpus_file_ref(relative_path)
    envelope = await read_files_to_envelope(
        [file_ref],
        ReadFileArgs(
            names=[file_ref.original_name],
            nested_mode=NestedMode.REFS,
            recursive=False,
        ),
        tool_name="read_file",
    )
    file_result = envelope.files[0]
    assert file_result.success is True
    assert len(file_result.nested) >= 1
    assert "![" in file_result.results[0].result
    assert parts_from_file_results(envelope.files) == []
