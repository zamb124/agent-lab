"""Эмулятор osmosis replication-сервера Geofabrik для тестового стека.

Контракт — как у ``download.geofabrik.de/<area>-updates``: последнее
состояние лежит в корне репликации ``GET {base}/state.txt`` и содержит
``sequenceNumber``/``timestamp`` (формат osmosis state, именно его читает
``osmium.replication.server.ReplicationServer.get_state_info``).

``{base}`` может быть любым путём — репликации разных регионов держат
свой корень. Последовательность детерминированная (``5000``), для
``stale``-префикса — ``7`` (регион всегда «актуален»).
"""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

_STATE_TEMPLATE: Final = (
    "#Fri Nov 07 12:00:00 UTC 2025\n"
    "sequenceNumber={seq}\n"
    "timestamp=2025-11-07T20\\:21\\:02Z\n"
)

app = FastAPI(title="platform-replication-emulator")


@app.get("/{base:path}/state.txt")
async def state(base: str) -> PlainTextResponse:
    seq = 7 if base.startswith("stale") else 5000
    return PlainTextResponse(_STATE_TEMPLATE.format(seq=seq))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
