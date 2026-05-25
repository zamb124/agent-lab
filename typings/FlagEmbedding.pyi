from collections.abc import Sequence

type RerankDeviceSpec = str | int | Sequence[str] | Sequence[int]
type RerankSentencePair = tuple[str, str]


class FlagLLMReranker:
    def __init__(
        self,
        model_name_or_path: str,
        *,
        peft_path: str | None = ...,
        use_fp16: bool = ...,
        use_bf16: bool = ...,
        query_instruction_for_rerank: str = ...,
        query_instruction_format: str = ...,
        passage_instruction_for_rerank: str = ...,
        passage_instruction_format: str = ...,
        cache_dir: str | None = ...,
        trust_remote_code: bool = ...,
        devices: RerankDeviceSpec | None = ...,
        prompt: str | None = ...,
        batch_size: int = ...,
        query_max_length: int | None = ...,
        max_length: int = ...,
        normalize: bool = ...,
    ) -> None: ...

    def compute_score(
        self,
        sentence_pairs: Sequence[RerankSentencePair] | RerankSentencePair,
        *,
        batch_size: int = ...,
        max_length: int = ...,
    ) -> list[float]: ...
