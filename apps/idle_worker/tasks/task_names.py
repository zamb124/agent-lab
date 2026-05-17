"""TaskIQ task-name contract для idle worker."""

TASK_PUSH_CONFIG_SET = "push_config_set"
TASK_PUSH_CONFIG_GET = "push_config_get"
TASK_PUSH_CONFIG_LIST = "push_config_list"
TASK_PUSH_CONFIG_DELETE = "push_config_delete"
TASK_PUSH_NOTIFICATION_SEND = "push_notification_send"
TASK_SEND_TASK_UPDATE = "send_task_update"
TASK_SEND_TASK_COMPLETED = "send_task_completed"
TASK_SEND_TASK_FAILED = "send_task_failed"
TASK_SEND_TASK_INPUT_REQUIRED = "send_task_input_required"

__all__ = [
    "TASK_PUSH_CONFIG_SET",
    "TASK_PUSH_CONFIG_GET",
    "TASK_PUSH_CONFIG_LIST",
    "TASK_PUSH_CONFIG_DELETE",
    "TASK_PUSH_NOTIFICATION_SEND",
    "TASK_SEND_TASK_UPDATE",
    "TASK_SEND_TASK_COMPLETED",
    "TASK_SEND_TASK_FAILED",
    "TASK_SEND_TASK_INPUT_REQUIRED",
]
