"""Парсинг тела и движок Markdown-форматирования (батч generate)."""

from __future__ import annotations

import gc
import time
from collections.abc import Sequence
from typing import TypedDict

import torch
from fastapi import HTTPException
from transformers import GenerationConfig

from apps.provider_litserve.llm.local_causal_lm import (
    ensure_local_causal_lm,
    require_causal_lm_generated_tensor,
)
from apps.provider_litserve.markdown_format.chunking import split_text_into_markdown_chunks
from apps.provider_litserve.runtime_models import allowed_api_model_ids, resolve_hf_model_id
from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


class MarkdownFormatParams(TypedDict):
    text: str
    model_id: str
    max_chunk_chars: int
    max_microbatch: int
    max_new_tokens: int
    chunk_join: str


class MarkdownUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class MarkdownFormatResult(TypedDict):
    markdown: str
    chunks_total: int
    chunks_processed: int
    model: str
    usage: MarkdownUsage


def normalize_litserve_eos_token_id(
    raw: int | Sequence[int] | torch.Tensor | None,
) -> int | list[int] | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, torch.Tensor):
        flat = raw.detach().cpu().flatten().long()
        count = int(flat.numel())
        if count == 0:
            return None
        if count == 1:
            return int(flat[0].item())
        return [int(flat[index].item()) for index in range(count)]
    if len(raw) == 0:
        return None
    ints = [int(item) for item in raw]
    return ints[0] if len(ints) == 1 else ints

_MARKDOWN_SYSTEM = (
    "You convert plain text into clean, structured Markdown. "
    "Output ONLY the Markdown for this part. No preamble, no explanation, no code fences around the whole answer. "
    "Preserve the source language. Use headings, lists, and emphasis where they improve readability."
)


def parse_format_markdown_body(
    body: JsonObject,
    *,
    cfg: ProviderLitserveInfraConfig,
) -> MarkdownFormatParams:
    text_raw = body.get("text")
    if not isinstance(text_raw, str):
        raise HTTPException(status_code=422, detail={"reason": "text_required"})
    text = text_raw.strip()
    if not text:
        raise HTTPException(status_code=422, detail={"reason": "text_empty"})

    model_raw = body.get("model")
    if model_raw is None:
        configured = cfg.markdown_default_api_model_id.strip()
        primary_llm = cfg.llm_model_id.strip()
        model_id = configured if configured else primary_llm
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

    out: MarkdownFormatParams = {
        "text": text,
        "model_id": model_id,
        "max_chunk_chars": chunk_chars,
        "max_microbatch": microbatch,
        "max_new_tokens": max_new_tokens,
        "chunk_join": joiner,
    }
    validate_markdown_format_params(out)
    return out


def markdown_trim_generated_token_ids(
    new_tokens_1d: torch.Tensor,
    *,
    eos_token_id: int | list[int] | None,
    pad_token_id: int | None,
) -> torch.Tensor:
    row = new_tokens_1d.flatten().long().clone()
    if eos_token_id is not None:
        for i in range(row.numel()):
            tid = int(row[i].item())
            at_eos = tid == eos_token_id if isinstance(eos_token_id, int) else tid in eos_token_id
            if at_eos:
                row = row[:i]
                break
    if pad_token_id is not None and row.numel() > 0:
        while row.numel() > 0 and int(row[-1].item()) == pad_token_id:
            row = row[:-1]
    return row


def validate_markdown_format_params(parsed: MarkdownFormatParams) -> None:
    cc = parsed["max_chunk_chars"]
    if cc < 512 or cc > 100_000:
        raise HTTPException(status_code=422, detail={"reason": "max_chunk_chars_out_of_range"})
    mb = parsed["max_microbatch"]
    if mb < 1 or mb > 16:
        raise HTTPException(status_code=422, detail={"reason": "max_microbatch_out_of_range"})
    mnt = parsed["max_new_tokens"]
    if mnt < 64 or mnt > 8192:
        raise HTTPException(status_code=422, detail={"reason": "max_new_tokens_out_of_range"})


class MarkdownFormatEngine:
    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._device: str = "cpu"
        self._hf_token: str | None = None

    def setup(self, device: str | None) -> None:
        self._device = str(device) if device else resolve_torch_device(self._cfg)
        self._hf_token = self._cfg.hf_token

    def format_text(self, parsed: MarkdownFormatParams) -> MarkdownFormatResult:
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

        requested_mb = max(1, int(parsed["max_microbatch"]))
        peak_cap = max(1, int(self._cfg.markdown_microbatch_peak_cap))
        max_microbatch = min(requested_mb, peak_cap)
        if max_microbatch < requested_mb:
            logger.info(
                "markdown_format_microbatch_capped",
                requested=requested_mb,
                effective=max_microbatch,
                peak_cap=peak_cap,
            )
        max_new_tokens = max(1, int(parsed["max_new_tokens"]))
        joiner: str = parsed["chunk_join"]
        tokenizer_max_length = max(256, int(self._cfg.markdown_tokenizer_max_length))

        formatted_parts: list[str] = []
        total = len(chunks)
        prompt_tokens_acc = 0
        completion_tokens_acc = 0
        logger.info(
            "markdown_format_started",
            chunks_total=total,
            max_microbatch=max_microbatch,
            max_new_tokens=max_new_tokens,
            hf_model_id=hf_model_id,
        )
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

                unpadded = tokenizer(prompts, add_special_tokens=True, truncation=False)
                batch_ids = unpadded["input_ids"]
                for local_i, ids in enumerate(batch_ids):
                    ln = len(ids)
                    if ln > tokenizer_max_length:
                        global_part = batch_start + local_i + 1
                        logger.warning(
                            "markdown_format_prompt_token_length_exceeded",
                            chunk_part_index=global_part,
                            chunks_total=total,
                            actual_length=ln,
                            max_length=tokenizer_max_length,
                        )
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "reason": "markdown_prompt_token_length_exceeded",
                                "max_length": tokenizer_max_length,
                                "actual_length": ln,
                                "chunk_part_index": global_part,
                                "chunks_total": total,
                            },
                        )

                encoded = tokenizer(
                    prompts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=tokenizer_max_length,
                )
                encoded = {k: v.to(self._device) for k, v in encoded.items()}
                attn = encoded.get("attention_mask")
                if attn is not None:
                    prompt_tokens_acc += int(attn.sum().item())
                    max_prompt_tokens = int(attn.sum(dim=1).max().item())
                else:
                    prompt_tokens_acc += int(encoded["input_ids"].numel())
                    max_prompt_tokens = int(encoded["input_ids"].shape[1])
                prompt_width = int(encoded["input_ids"].shape[1])
                slack = max(384, max_prompt_tokens // 4)
                adaptive_budget = max_prompt_tokens + slack
                batch_max_new_tokens = min(max_new_tokens, adaptive_budget)
                if batch_max_new_tokens < 64:
                    batch_max_new_tokens = 64
                if batch_max_new_tokens < max_new_tokens:
                    logger.info(
                        "markdown_format_new_tokens_adaptive_cap",
                        configured_max_new_tokens=max_new_tokens,
                        effective_max_new_tokens=batch_max_new_tokens,
                        max_prompt_tokens=max_prompt_tokens,
                        slack=slack,
                    )
                pad_id = tokenizer.pad_token_id
                if pad_id is None:
                    pad_id = tokenizer.eos_token_id
                eos_raw = getattr(model.generation_config, "eos_token_id", None)
                if eos_raw is None:
                    eos_raw = tokenizer.eos_token_id
                eos_gen = normalize_litserve_eos_token_id(eos_raw)
                rep_penalty = float(self._cfg.markdown_format_repetition_penalty)
                gen_cfg = GenerationConfig(
                    max_new_tokens=batch_max_new_tokens,
                    do_sample=False,
                    pad_token_id=pad_id,
                    repetition_penalty=rep_penalty,
                    temperature=None,
                    top_p=None,
                    top_k=None,
                )
                if eos_gen is not None:
                    gen_cfg.eos_token_id = eos_gen
                logger.info(
                    "markdown_format_generate_begin",
                    batch_chunks=len(batch_chunks),
                    prompt_seq_width=prompt_width,
                    max_prompt_tokens=max_prompt_tokens,
                    max_new_tokens=batch_max_new_tokens,
                    hf_model_id=hf_model_id,
                )
                gen_t0 = time.monotonic()
                with torch.no_grad():
                    generated = require_causal_lm_generated_tensor(
                        model.generate(
                            inputs=encoded["input_ids"],
                            attention_mask=encoded.get("attention_mask"),
                            token_type_ids=encoded.get("token_type_ids"),
                            generation_config=gen_cfg,
                        )
                    )
                gen_ms = (time.monotonic() - gen_t0) * 1000.0
                logger.info(
                    "markdown_format_generate_done",
                    duration_ms=round(gen_ms, 2),
                    batch_chunks=len(batch_chunks),
                    max_new_tokens=batch_max_new_tokens,
                    hf_model_id=hf_model_id,
                )
                for row_idx in range(generated.shape[0]):
                    new_tokens = generated[row_idx, prompt_width:]
                    trimmed = markdown_trim_generated_token_ids(
                        new_tokens,
                        eos_token_id=eos_gen,
                        pad_token_id=pad_id,
                    )
                    completion_tokens_acc += int(trimmed.numel())
                    piece = tokenizer.decode(trimmed, skip_special_tokens=True).strip()
                    formatted_parts.append(piece)
                logger.info(
                    "markdown_format_batch_done",
                    chunks_done=len(formatted_parts),
                    chunks_total=total,
                    batch_chunks=len(batch_chunks),
                    hf_model_id=hf_model_id,
                )
                del generated, encoded, gen_cfg
                _ = gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                elif torch.backends.mps.is_available():
                    torch.mps.empty_cache()
        finally:
            tokenizer.padding_side = old_padding_side

        markdown = joiner.join(formatted_parts).strip()
        total_tok = prompt_tokens_acc + completion_tokens_acc
        usage: MarkdownUsage = {
            "prompt_tokens": prompt_tokens_acc,
            "completion_tokens": completion_tokens_acc,
            "total_tokens": total_tok,
        }
        return {
            "markdown": markdown,
            "chunks_total": total,
            "chunks_processed": len(formatted_parts),
            "model": req_model,
            "usage": usage,
        }
