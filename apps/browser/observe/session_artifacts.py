"""
Артефакты control-сессий: запись JSON событий по шагам в artifacts_dir.

Цель:
- обеспечить дебаг каждой session_id без необходимости ручной записи артефактов в тестах.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TypeAlias, cast

from pydantic import BaseModel

from core.types import JsonObject, JsonValue, require_json_object

SessionArtifactObject: TypeAlias = BaseModel | Mapping[str, JsonValue]


def _artifact_object(value: SessionArtifactObject, field_name: str) -> JsonObject:
    if isinstance(value, BaseModel):
        return require_json_object(cast(object, value.model_dump(mode="json")), field_name)
    return require_json_object(dict(value), field_name)


def _optional_artifact_object(value: SessionArtifactObject | None, field_name: str) -> JsonObject | None:
    if value is None:
        return None
    return _artifact_object(value, field_name)


class ControlSessionArtifactsWriter:
    """
    Пишет шаги сессии в JSON файлы:
    `artifacts_dir/sessions/<session_id>/events/<seq>_<op>.json`.

    Инварианты:
    - шаги нумеруются монотонно per-session (in-process).
    - запись артефактов не должна менять поведение API: ошибки пробрасываются наружу,
      а ошибки записи артефактов тоже считаются ошибкой (zero-guess).
    """

    def __init__(self, *, artifacts_dir: str) -> None:
        if not artifacts_dir:
            raise ValueError("artifacts_dir обязателен")
        self._root: Path = Path(artifacts_dir)
        self._seq_by_session: dict[str, int] = {}

    def forget(self, session_id: str) -> None:
        _ = self._seq_by_session.pop(session_id, None)

    def _next_seq(self, session_id: str) -> int:
        if not session_id:
            raise ValueError("session_id обязателен")
        cur = self._seq_by_session.get(session_id, 0)
        nxt = cur + 1
        self._seq_by_session[session_id] = nxt
        return nxt

    def write_event(
        self,
        *,
        session_id: str,
        op: str,
        request: SessionArtifactObject,
        response: SessionArtifactObject | None,
        error: SessionArtifactObject | None,
        meta: JsonObject,
    ) -> str:
        if not session_id:
            raise ValueError("session_id обязателен")
        if not op:
            raise ValueError("op обязателен")

        seq = self._next_seq(session_id)
        out_dir = self._root / "sessions" / session_id / "events"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_op = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in op)
        path = out_dir / f"{seq:04d}_{safe_op}.json"

        payload: JsonObject = {
            "schema": "browser.control.session_event.v1",
            "ts_ms": int(time.time() * 1000),
            "seq": seq,
            "session_id": session_id,
            "op": op,
            "request": _artifact_object(request, "request"),
            "response": _optional_artifact_object(response, "response"),
            "error": _optional_artifact_object(error, "error"),
            "meta": meta,
        }
        _ = path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def write_sidecar_text_for_event(
        self,
        *,
        event_json_path: str,
        ext: str,
        content: str,
    ) -> str:
        if not event_json_path:
            raise ValueError("event_json_path обязателен")
        if not ext:
            raise ValueError("ext обязателен")
        if not ext.startswith("."):
            raise ValueError("ext должен начинаться с '.'")
        src = Path(event_json_path)
        if src.suffix != ".json":
            raise ValueError("event_json_path должен указывать на .json")
        out = src.with_suffix(ext)
        _ = out.write_text(content, encoding="utf-8")
        return str(out)

    def patch_event_meta(self, *, event_json_path: str, meta_patch: JsonObject) -> None:
        """
        Обновить `meta` у уже записанного session-event JSON.

        Используется для записи ссылок на sidecar-артефакты (html/console/errors),
        которые появляются после `write_event()` и требуют знать итоговый путь файла.
        """
        if not event_json_path:
            raise ValueError("event_json_path обязателен")
        if not meta_patch:
            raise ValueError("meta_patch обязателен")

        path = Path(event_json_path)
        if not path.exists():
            raise FileNotFoundError(event_json_path)
        if path.suffix != ".json":
            raise ValueError("event_json_path должен указывать на .json")

        payload = require_json_object(
            cast(object, json.loads(path.read_text(encoding="utf-8"))),
            "event JSON",
        )
        meta_obj = require_json_object(payload.get("meta"), "event JSON meta")
        meta_obj.update(meta_patch)
        payload["meta"] = meta_obj
        _ = path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_jsonl_for_session(
        self,
        *,
        session_id: str,
        filename: str,
        record: SessionArtifactObject,
    ) -> str:
        """
        Добавить запись в JSONL-лог сессии.

        Формат: одна JSON-строка на запись.
        """
        if not session_id:
            raise ValueError("session_id обязателен")
        if not filename:
            raise ValueError("filename обязателен")
        if "/" in filename or "\\" in filename:
            raise ValueError("filename не должен содержать пути")
        out_dir = self._root / "sessions" / session_id / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename
        line = json.dumps(_artifact_object(record, "record"), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            _ = f.write(line)
            _ = f.write("\n")
        return str(path)
