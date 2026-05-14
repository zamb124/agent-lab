"""Резолв профиля речи flow + ветки в SpeechOverride и контекст задачи."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.flow_speech_settings import (
    FlowSpeechSettings,
    FlowSpeechSttBlock,
    FlowSpeechTtsBlock,
    FlowSpeechVadBlock,
)
from core.clients.speech_override import SpeechOverride
from core.context import Context

PLATFORM_FLOW_SPEECH_LAYERS_KEY = "platform_flow_speech_layers"


def _merge_optional_str(base: Optional[str], overlay: Optional[str]) -> Optional[str]:
    if overlay is not None and overlay != "":
        return overlay
    return base


def _merge_optional_float(base: Optional[float], overlay: Optional[float]) -> Optional[float]:
    if overlay is not None:
        return overlay
    return base


def _merge_optional_int(base: Optional[int], overlay: Optional[int]) -> Optional[int]:
    if overlay is not None:
        return overlay
    return base


def _merge_stt_block(
    base: Optional[FlowSpeechSttBlock],
    overlay: Optional[FlowSpeechSttBlock],
) -> Optional[FlowSpeechSttBlock]:
    if overlay is None:
        return base
    if base is None:
        return overlay
    return FlowSpeechSttBlock(
        provider=overlay.provider if overlay.provider is not None else base.provider,
        model=_merge_optional_str(base.model, overlay.model),
        language=_merge_optional_str(base.language, overlay.language),
    )


def _merge_tts_block(
    base: Optional[FlowSpeechTtsBlock],
    overlay: Optional[FlowSpeechTtsBlock],
) -> Optional[FlowSpeechTtsBlock]:
    if overlay is None:
        return base
    if base is None:
        return overlay
    return FlowSpeechTtsBlock(
        provider=overlay.provider if overlay.provider is not None else base.provider,
        model=_merge_optional_str(base.model, overlay.model),
        voice=_merge_optional_str(base.voice, overlay.voice),
        language=_merge_optional_str(base.language, overlay.language),
        response_format=overlay.response_format if overlay.response_format is not None else base.response_format,
        sample_rate=_merge_optional_int(base.sample_rate, overlay.sample_rate),
    )


def _merge_vad_block(
    base: Optional[FlowSpeechVadBlock],
    overlay: Optional[FlowSpeechVadBlock],
) -> Optional[FlowSpeechVadBlock]:
    if overlay is None:
        return base
    if base is None:
        return overlay
    return FlowSpeechVadBlock(
        provider=overlay.provider if overlay.provider is not None else base.provider,
        sample_rate=_merge_optional_int(base.sample_rate, overlay.sample_rate),
        threshold=_merge_optional_float(base.threshold, overlay.threshold),
    )


def merge_flow_speech_settings(
    flow_level: Optional[FlowSpeechSettings],
    branch_level: Optional[FlowSpeechSettings],
) -> Optional[FlowSpeechSettings]:
    """Мерж ветки поверх flow; None на уровне ветки — наследование."""
    if flow_level is None and branch_level is None:
        return None
    if branch_level is None:
        return flow_level
    if flow_level is None:
        return branch_level
    return FlowSpeechSettings(
        stt=_merge_stt_block(flow_level.stt, branch_level.stt),
        tts=_merge_tts_block(flow_level.tts, branch_level.tts),
        vad=_merge_vad_block(flow_level.vad, branch_level.vad),
    )


def effective_flow_speech_settings(
    flow_config: FlowConfig,
    branch_id: str,
) -> Optional[FlowSpeechSettings]:
    branch_cfg = None
    if branch_id and branch_id.strip() and flow_config.branches:
        branch_cfg = flow_config.branches.get(branch_id.strip())
    overlay = branch_cfg.speech if branch_cfg else None
    return merge_flow_speech_settings(flow_config.speech, overlay)


def flow_speech_to_triple_override(
    settings: Optional[FlowSpeechSettings],
) -> Tuple[SpeechOverride, SpeechOverride, SpeechOverride]:
    """Три SpeechOverride для STT / TTS / VAD."""
    if settings is None:
        empty = SpeechOverride()
        return empty, empty, empty
    stt_b = settings.stt
    tts_b = settings.tts
    vad_b = settings.vad
    stt_ov = SpeechOverride(
        provider=stt_b.provider if stt_b else None,
        model=stt_b.model if stt_b else None,
        language=stt_b.language if stt_b else None,
    )
    tts_ov = SpeechOverride(
        provider=tts_b.provider if tts_b else None,
        model=tts_b.model if tts_b else None,
        voice=tts_b.voice if tts_b else None,
        language=tts_b.language if tts_b else None,
        response_format=tts_b.response_format if tts_b else None,
        sample_rate=tts_b.sample_rate if tts_b else None,
    )
    vad_ov = SpeechOverride(
        provider=vad_b.provider if vad_b else None,
        sample_rate=vad_b.sample_rate if vad_b else None,
        threshold=vad_b.threshold if vad_b else None,
    )
    return stt_ov, tts_ov, vad_ov


def merge_explicit_over_flow_speech_layer(
    explicit: SpeechOverride,
    flow_layer: SpeechOverride,
) -> SpeechOverride:
    """Явный override побеждает по каждому полю; flow_layer заполняет пробелы."""
    merged: Dict[str, Any] = {}
    for name in SpeechOverride.model_fields:
        ev = getattr(explicit, name)
        fv = getattr(flow_layer, name)
        if ev is not None:
            merged[name] = ev
        elif fv is not None:
            merged[name] = fv
    return SpeechOverride.model_validate(merged)


def triple_to_voice_ws_query_dict(
    stt: SpeechOverride,
    tts: SpeechOverride,
    vad: SpeechOverride,
) -> Dict[str, str]:
    """Ключи query для ``apps/voice/api/session.py`` (только непустые)."""
    out: Dict[str, str] = {}
    if stt.provider is not None and stt.provider != "":
        out["stt_provider_name"] = str(stt.provider)
    if stt.model is not None and stt.model != "":
        out["stt_model"] = stt.model
    if tts.provider is not None and tts.provider != "":
        out["tts_provider_name"] = str(tts.provider)
    if tts.model is not None and tts.model != "":
        out["tts_model"] = tts.model
    if tts.voice is not None and tts.voice != "":
        out["tts_voice"] = tts.voice
    if tts.sample_rate is not None:
        out["tts_sample_rate"] = str(tts.sample_rate)
    if vad.provider is not None and vad.provider != "":
        out["vad_provider_name"] = str(vad.provider)
    if vad.sample_rate is not None:
        out["vad_sample_rate"] = str(vad.sample_rate)
    if vad.threshold is not None:
        out["vad_threshold"] = str(vad.threshold)
    lang_stt = stt.language if stt.language is not None and stt.language != "" else None
    lang_tts = tts.language if tts.language is not None and tts.language != "" else None
    if lang_stt is not None:
        out["language"] = lang_stt
    elif lang_tts is not None:
        out["language"] = lang_tts
    return out


def attach_flow_speech_layers_to_context(
    ctx: Context,
    flow_config: FlowConfig,
    branch_id: str,
) -> None:
    """Кладёт сериализуемые слои STT/TTS/VAD в metadata для TaskIQ и HTTP."""
    settings = effective_flow_speech_settings(flow_config, branch_id)
    stt, tts, vad = flow_speech_to_triple_override(settings)
    ctx.metadata = {
        **ctx.metadata,
        PLATFORM_FLOW_SPEECH_LAYERS_KEY: {
            "stt": stt.model_dump(exclude_none=True),
            "tts": tts.model_dump(exclude_none=True),
            "vad": vad.model_dump(exclude_none=True),
        },
    }


def load_flow_speech_layers_from_context_metadata(
    metadata: Optional[Dict[str, Any]],
) -> Tuple[SpeechOverride, SpeechOverride, SpeechOverride]:
    if not metadata:
        empty = SpeechOverride()
        return empty, empty, empty
    raw = metadata.get(PLATFORM_FLOW_SPEECH_LAYERS_KEY)
    if not isinstance(raw, dict):
        empty = SpeechOverride()
        return empty, empty, empty
    def _block(key: str) -> SpeechOverride:
        b = raw.get(key)
        if not isinstance(b, dict):
            return SpeechOverride()
        return SpeechOverride.model_validate(b)

    return _block("stt"), _block("tts"), _block("vad")


__all__ = [
    "PLATFORM_FLOW_SPEECH_LAYERS_KEY",
    "attach_flow_speech_layers_to_context",
    "effective_flow_speech_settings",
    "flow_speech_to_triple_override",
    "load_flow_speech_layers_from_context_metadata",
    "merge_explicit_over_flow_speech_layer",
    "merge_flow_speech_settings",
    "triple_to_voice_ws_query_dict",
]
