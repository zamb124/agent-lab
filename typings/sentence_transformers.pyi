from collections.abc import Iterator
from typing import Literal, Protocol

class SentenceEmbeddingVector(Protocol):
    def __iter__(self) -> Iterator[float]: ...


class SentenceEmbeddingMatrix(Protocol):
    shape: tuple[int, ...]

    def __getitem__(self, index: int) -> SentenceEmbeddingVector: ...


class SentenceTransformer:
    def __init__(
        self,
        model_name_or_path: str,
        *,
        device: str | None = ...,
        model_kwargs: dict[str, Literal["bfloat16"]] | None = ...,
        trust_remote_code: bool = ...,
        local_files_only: bool = ...,
        token: bool | str | None = ...,
    ) -> None: ...

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> SentenceEmbeddingMatrix: ...
