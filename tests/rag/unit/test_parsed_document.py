"""Контракт ParsedDocument / ParsedBlock (RAG-30)."""

from core.rag.parsed_document import ParsedBlock, ParsedDocument


def test_parsed_document_minimal_roundtrip() -> None:
    doc = ParsedDocument(
        canonical_text="hello",
        blocks=None,
        source_metadata={"parser_engine": "unstructured"},
    )
    dumped = doc.model_dump(mode="json")
    restored = ParsedDocument.model_validate(dumped)
    assert {"canonical_text": restored.canonical_text, "blocks": restored.blocks} == {
        "canonical_text": "hello",
        "blocks": None,
    }


def test_parsed_document_with_blocks() -> None:
    doc = ParsedDocument(
        canonical_text="a\n\nb",
        blocks=[
            ParsedBlock(kind="heading", text="Title", level=1, metadata={"page": 1}),
            ParsedBlock(kind="paragraph", text="Body", level=None, metadata={}),
        ],
        source_metadata={},
    )
    assert {"blocks_len": len(doc.blocks or [])} == {"blocks_len": 2}
