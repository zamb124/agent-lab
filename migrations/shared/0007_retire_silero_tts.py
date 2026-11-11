"""Retire Silero TTS catalog rows: TTS переезжает на Qwen3-TTS CustomVoice.

Строки с ``silero_bundle`` в params не валидны для новой entry-модели —
переводим их в ``deleting``; ops-цикл provider_litserve чистит веса и ставит
tombstone ``deleted``. Новая запись сидится из ``infra.tts_models``.
"""

depends_on = "0006_create_pending_call_status_enum_enum"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "UPDATE provider_litserve_models "
        "SET status = 'deleting', updated_at = now() "
        "WHERE kind = 'tts' AND params ? 'silero_bundle' "
        "AND status NOT IN ('deleting', 'deleted')"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute(
        "UPDATE provider_litserve_models SET status = 'ready', updated_at = now() "
        "WHERE kind = 'tts' AND status = 'deleting' AND params ? 'silero_bundle'"
    )
