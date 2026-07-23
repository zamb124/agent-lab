"""Declaration-модуль Sync realtime задач (очередь ``sync``).

Лёгкий: только объявления. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``).
"""

from core.tasks import declare_task

SYNC_FINALIZE_RECORDING = declare_task("sync_finalize_recording", queue="sync")
SYNC_TRANSCRIBE_AUDIO_MESSAGE = declare_task("sync_transcribe_audio_message", queue="sync")
SYNC_TRANSCRIBE_VIDEO_MESSAGE = declare_task("sync_transcribe_video_message", queue="sync")
SYNC_AGGREGATE_CALL_TRANSCRIPT = declare_task(
    "sync_aggregate_call_transcript", queue="sync"
)
SYNC_SPEECH_TO_CHAT_POLL = declare_task("sync_speech_to_chat_poll", queue="sync")
DELIVER_CHANNEL_MESSAGE_NOTIFICATION = declare_task(
    "deliver_channel_message_notification", queue="sync"
)
DELIVER_SYNC_MENTION_NOTIFICATION = declare_task(
    "deliver_sync_mention_notification", queue="sync"
)

__all__ = [
    "DELIVER_CHANNEL_MESSAGE_NOTIFICATION",
    "DELIVER_SYNC_MENTION_NOTIFICATION",
    "SYNC_AGGREGATE_CALL_TRANSCRIPT",
    "SYNC_FINALIZE_RECORDING",
    "SYNC_SPEECH_TO_CHAT_POLL",
    "SYNC_TRANSCRIBE_AUDIO_MESSAGE",
    "SYNC_TRANSCRIBE_VIDEO_MESSAGE",
]
