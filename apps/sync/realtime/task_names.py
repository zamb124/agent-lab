"""TaskIQ task-name contract for Sync realtime tasks."""

SYNC_FINALIZE_RECORDING_TASK_NAME = "apps.sync.realtime.tasks:sync_finalize_recording_task"
SYNC_TRANSCRIBE_AUDIO_MESSAGE_TASK_NAME = (
    "apps.sync.realtime.tasks:sync_transcribe_audio_message_task"
)
SYNC_TRANSCRIBE_VIDEO_MESSAGE_TASK_NAME = (
    "apps.sync.realtime.tasks:sync_transcribe_video_message_task"
)
SYNC_AGGREGATE_CALL_TRANSCRIPT_TASK_NAME = (
    "apps.sync.realtime.tasks:sync_aggregate_call_transcript_task"
)
SYNC_SPEECH_TO_CHAT_POLL_TASK_NAME = "apps.sync.realtime.tasks:sync_speech_to_chat_poll_task"

__all__ = [
    "SYNC_AGGREGATE_CALL_TRANSCRIPT_TASK_NAME",
    "SYNC_FINALIZE_RECORDING_TASK_NAME",
    "SYNC_SPEECH_TO_CHAT_POLL_TASK_NAME",
    "SYNC_TRANSCRIBE_AUDIO_MESSAGE_TASK_NAME",
    "SYNC_TRANSCRIBE_VIDEO_MESSAGE_TASK_NAME",
]
