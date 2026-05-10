"""Парсинг тела и движок Markdown-форматирования (батч generate)."""

from __future__ import annotations

from typing import Any

import torch
from fastapi import HTTPException

from apps.provider_litserve.llm.local_causal_lm import ensure_local_causal_lm
from apps.provider_litserve.markdown_format.chunking import split_text_into_markdown_chunks
from apps.provider_litserve.runtime_models import allowed_api_model_ids, resolve_hf_model_id
from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig

_MARKDOWN_SYSTEM = (
    "You convert plain text into clean, structured Markdown. "
    "Output ONLY the Markdown for this part. No preamble, no explanation, no code fences around the whole answer. "
    "Preserve the source language. Use headings, lists, and emphasis where they improve readability."
)


def parse_format_markdown_body(
    body: dict[str, Any],
    *,
    cfg: ProviderLitserveInfraConfig,
) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail={"reason": "body_must_be_object"})
    text_raw = body.get("text")
    if not isinstance(text_raw, str):
        raise HTTPException(status_code=422, detail={"reason": "text_required"})
    text = text_raw.strip()
    if not text:
        raise HTTPException(status_code=422, detail={"reason": "text_empty"})

    model_raw = body.get("model")
    if model_raw is None:
        model_id = cfg.markdown_default_api_model_id.strip()
    else:
        if not isinstance(model_raw, str):
            raise HTTPException(status_code=422, detail={"reason": "model_invalid"})
        model_id = model_raw.strip()
    if not model_id:
        raise HTTPException(status_code=422, detail={"reason": "model_empty"})

    max_chunk = body.get("max_chunk_chars")
    if max_chunk is None:
        chunk_chars = cfg.markdown_max_chunk_chars
    else:
        if not isinstance(max_chunk, int):
            raise HTTPException(status_code=422, detail={"reason": "max_chunk_chars_invalid"})
        chunk_chars = max_chunk

    max_batch = body.get("max_microbatch")
    if max_batch is None:
        microbatch = cfg.markdown_max_microbatch
    else:
        if not isinstance(max_batch, int):
            raise HTTPException(status_code=422, detail={"reason": "max_microbatch_invalid"})
        microbatch = max_batch

    max_new = body.get("max_new_tokens")
    if max_new is None:
        max_new_tokens = cfg.markdown_max_new_tokens
    else:
        if not isinstance(max_new, int):
            raise HTTPException(status_code=422, detail={"reason": "max_new_tokens_invalid"})
        max_new_tokens = max_new

    chunk_join = body.get("chunk_join")
    if chunk_join is None:
        joiner = cfg.markdown_chunk_join
    else:
        if not isinstance(chunk_join, str):
            raise HTTPException(status_code=422, detail={"reason": "chunk_join_invalid"})
        joiner = chunk_join

    out = {
        "text": text,
        "model_id": model_id,
        "max_chunk_chars": chunk_chars,
        "max_microbatch": microbatch,
        "max_new_tokens": max_new_tokens,
        "chunk_join": joiner,
    }
    validate_markdown_format_params(out)
    return out


def validate_markdown_format_params(parsed: dict[str, Any]) -> None:
    cc = int(parsed["max_chunk_chars"])
    if cc < 512 or cc > 100_000:
        raise HTTPException(status_code=422, detail={"reason": "max_chunk_chars_out_of_range"})
    mb = int(parsed["max_microbatch"])
    if mb < 1 or mb > 16:
        raise HTTPException(status_code=422, detail={"reason": "max_microbatch_out_of_range"})
    mnt = int(parsed["max_new_tokens"])
    if mnt < 64 or mnt > 8192:
        raise HTTPException(status_code=422, detail={"reason": "max_new_tokens_out_of_range"})


class MarkdownFormatEngine:
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._device: str = "cpu"
        self._hf_token: str | None = None

    def setup(self, device: str | None) -> None:
        self._device = str(device) if device else resolve_torch_device(self._cfg)
        self._hf_token = self._cfg.hf_token

    def format_text(self, parsed: dict[str, Any]) -> dict[str, Any]:
        allowed_ids = allowed_api_model_ids("llm", self._cfg)
        req_model = parsed["model_id"]
        req_lower = req_model.lower()
        if not any(a.lower() == req_lower for a in allowed_ids):
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_markdown_model",
                    "model": req_model,
                    "allowed": sorted(allowed_ids),
                },
            )
        hf_model_id = resolve_hf_model_id("llm", req_model, self._cfg)
        if hf_model_id is None:
            raise HTTPException(
                status_code=422,
                detail={"reason": "unknown_markdown_model", "model": req_model},
            )

        chunks = split_text_into_markdown_chunks(parsed["text"], int(parsed["max_chunk_chars"]))
        if not chunks:
            raise HTTPException(status_code=422, detail={"reason": "text_empty"})

        tokenizer, model = ensure_local_causal_lm(
            hf_model_id=hf_model_id,
            device=self._device,
            hf_token=self._hf_token,
        )

        max_microbatch = max(1, int(parsed["max_microbatch"]))
        max_new_tokens = max(1, int(parsed["max_new_tokens"]))
        joiner: str = parsed["chunk_join"]
        tokenizer_max_length = max(256, int(self._cfg.markdown_tokenizer_max_length))

        formatted_parts: list[str] = []
        total = len(chunks)
        old_padding_side = tokenizer.padding_side
        tokenizer.padding_side = "left"
        try:
            for batch_start in range(0, total, max_microbatch):
                batch_chunks = chunks[batch_start : batch_start + max_microbatch]
                prompts: list[str] = []
                for local_i, chunk in enumerate(batch_chunks):
                    global_i = batch_start + local_i
                    messages = [
                        {"role": "system", "content": _MARKDOWN_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"This is part {global_i + 1} of {total}. "
                                "Convert only the following text to Markdown:\n\n"
                                f"{chunk}"
                            ),
                        },
                    ]
                    prompt = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                    prompts.append(prompt)

                encoded = tokenizer(
                    prompts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=tokenizer_max_length,
                )
                encoded = {k: v.to(self._device) for k, v in encoded.items()}
                prompt_width = int(encoded["input_ids"].shape[1])
                pad_id = tokenizer.pad_token_id
                if pad_id is None:
                    pad_id = tokenizer.eos_token_id
                with torch.no_grad():
                    generated = model.generate(
                        **encoded,
                        max_new_tokens=max_new_tokens,
                        do_sample=False,
                        pad_token_id=pad_id,
                    )
                for row_idx in range(generated.shape[0]):
                    new_tokens = generated[row_idx, prompt_width:]
                    piece = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
                    formatted_parts.append(piece)
        finally:
            tokenizer.padding_side = old_padding_side

        markdown = joiner.join(formatted_parts).strip()
        return {
            "markdown": markdown,
            "chunks_total": total,
            "chunks_processed": len(formatted_parts),
            "model": req_model,
        }
