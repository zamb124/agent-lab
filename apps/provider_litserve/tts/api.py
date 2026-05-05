"""LitServe API для TTS: POST /v1/audio/speech (OpenAI-совместимое).

Список моделей и их параметры (для Kokoro поле ``lang`` в конфиге — ``lang_code`` для ``kokoro.KPipeline``, не ISO; голоса вроде ``af_heart``) — в ``cfg.tts_models``.
Никаких хардкодов в этом модуле. При ``setup()`` воркера — прогрев дефолтной TTS-модели (загрузка ``KPipeline`` без синтеза речи).

Аннотация ``request: fastapi.Request`` обязательна для LitServe — см.
комментарий в ``apps/provider_litserve/stt/api.py`` (тот же контракт).

Без ``from __future__ import annotations`` — см. ``stt/api.py``
(совпадение аннотации с ``Request`` для LitServe / pickle).
"""

from typing import Any

import litserve as ls
from fastapi import HTTPException, Request

from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger

from .engines import get_local_tts_engine, parse_tts_body

logger = get_logger(__name__)


class TTSLitAPI(ls.LitAPI):
    """OpenAI-совместимый эндпоинт /v1/audio/speech."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/audio/speech")
        self._cfg = cfg
        self._engine = get_local_tts_engine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)
        info = self._engine.warmup_pipeline(None)
        logger.info(
            "tts_litapi.worker_warmup api_model_id=%s hf_model_id=%s cached_before=%s load_seconds=%s",
            info["api_model_id"],
            info["hf_model_id"],
            info["cached_before"],
            info["load_seconds"],
        )

    def decode_request(self, request: Request, **kwargs: Any) -> dict[str, Any]:
        try:
            return parse_tts_body(
                request,
                default_api_model_id=self._cfg.tts_default_api_model_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def predict(self, x: dict[str, Any], **kwargs: Any) -> bytes:
        try:
            return self._engine.synthesize(
                text=x["text"],
                api_model_id=x["model"],
                voice_override=x.get("voice_override"),
                response_format=x.get("response_format", "wav"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "tts_litapi.predict_failed",
                api_model_id=x.get("model"),
                voice_override=x.get("voice_override"),
                text_chars=len(x.get("text") or ""),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def encode_response(self, output: Any, **kwargs: Any) -> bytes:
        if isinstance(output, bytes):
            return output
        raise HTTPException(status_code=500, detail="TTS: неожиданный тип ответа")
