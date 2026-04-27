"""
Артефакты control-сессий: запись JSON событий по шагам в artifacts_dir.

Цель:
- обеспечить дебаг каждой session_id без необходимости ручной записи артефактов в тестах.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    return str(obj)


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
        self._root = Path(artifacts_dir)
        self._seq_by_session: dict[str, int] = {}

    def forget(self, session_id: str) -> None:
        self._seq_by_session.pop(session_id, None)

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
        request: Any,
        response: Any,
        error: Any,
        meta: dict[str, Any],
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

        payload = {
            "schema": "browser.control.session_event.v1",
            "ts_ms": int(time.time() * 1000),
            "seq": seq,
            "session_id": session_id,
            "op": op,
            "request": _jsonable(request),
            "response": _jsonable(response),
            "error": _jsonable(error),
            "meta": _jsonable(meta),
        }
        path.write_text(
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
        if content is None:
            raise ValueError("content обязателен")

        src = Path(event_json_path)
        if src.suffix != ".json":
            raise ValueError("event_json_path должен указывать на .json")
        out = src.with_suffix(ext)
        out.write_text(content, encoding="utf-8")
        return str(out)

    def patch_event_meta(self, *, event_json_path: str, meta_patch: dict[str, Any]) -> None:
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

        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            raise ValueError("event JSON: meta должен быть object")
        meta.update(_jsonable(meta_patch))
        payload["meta"] = meta
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_jsonl_for_session(
        self,
        *,
        session_id: str,
        filename: str,
        record: Any,
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
        if record is None:
            raise ValueError("record обязателен")

        out_dir = self._root / "sessions" / session_id / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename
        line = json.dumps(_jsonable(record), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
        return str(path)

