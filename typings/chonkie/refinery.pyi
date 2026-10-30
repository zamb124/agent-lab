from typing import Literal

from chonkie.tokenizer import TokenizerProtocol
from chonkie.types import Chunk

class OverlapRefinery:
    def __init__(
        self,
        tokenizer: str | TokenizerProtocol = "character",
        context_size: int | float = 0.25,
        mode: Literal["token", "recursive"] = "token",
        method: Literal["suffix", "prefix"] = "suffix",
        merge: bool = True,
        inplace: bool = True,
    ) -> None: ...

    def __call__(self, chunks: list[Chunk]) -> list[Chunk]: ...
