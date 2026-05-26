from typing import Literal

from chonkie.types import Chunk

class _Chunker:
    def __call__(self, text: str, *args: bool | int, **kwargs: bool | int) -> list[Chunk]: ...


class TokenChunker(_Chunker):
    def __init__(
        self,
        tokenizer: str = "character",
        chunk_size: int = 2048,
        chunk_overlap: int | float = 0,
    ) -> None: ...


class FastChunker(_Chunker):
    def __init__(
        self,
        chunk_size: int = 4096,
        delimiters: str = "\n.?",
        pattern: str | None = None,
        prefix: bool = False,
        consecutive: bool = False,
        forward_fallback: bool = False,
    ) -> None: ...


class SemanticChunker(_Chunker):
    def __init__(
        self,
        embedding_model: str = "minishlab/potion-base-32M",
        threshold: float = 0.8,
        chunk_size: int = 2048,
        similarity_window: int = 3,
        min_sentences_per_chunk: int = 1,
        min_characters_per_sentence: int = 24,
        delim: str | list[str] = [". ", "! ", "? ", "\n"],
        include_delim: Literal["prev", "next"] | None = "prev",
        skip_window: int = 0,
        filter_window: int = 5,
        filter_polyorder: int = 3,
        filter_tolerance: float = 0.2,
    ) -> None: ...


class RecursiveChunker(_Chunker):
    def __init__(
        self,
        tokenizer: str = "character",
        chunk_size: int = 2048,
        min_characters_per_chunk: int = 24,
    ) -> None: ...


class SentenceChunker(_Chunker):
    def __init__(
        self,
        tokenizer: str = "character",
        chunk_size: int = 2048,
        chunk_overlap: int = 0,
        min_sentences_per_chunk: int = 1,
        min_characters_per_sentence: int = 12,
        approximate: bool = False,
        delim: str | list[str] = [". ", "! ", "? ", "\n"],
        include_delim: Literal["prev", "next"] | None = "prev",
    ) -> None: ...


class CodeChunker(_Chunker):
    def __init__(
        self,
        tokenizer: str = "character",
        chunk_size: int = 2048,
        language: Literal["auto"] | str = "auto",
        include_nodes: bool = False,
    ) -> None: ...


class TableChunker(_Chunker):
    def __init__(self, tokenizer: str = "row", chunk_size: int = 3) -> None: ...
