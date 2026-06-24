"""
Типы для каналов коммуникации.
"""

from typing import TypeAlias

from a2a.types import Message
from pydantic import Field

from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.models.context_models import Context
from core.state import ExecutionTaskState, InterruptData
from core.types import JsonObject

ChannelRequestContext: TypeAlias = Context | JsonObject | None


class FlowTaskResult(StrictBaseModel):
    """Результат выполнения flow на границе channel -> task."""

    response: str
    task_state: ExecutionTaskState
    interrupt: InterruptData | None = None
    breakpoint_hit: str | None = Field(default=None, min_length=1)
    breakpoint_state: JsonObject | None = None


class PreparedTaskParams:
    """Подготовленные параметры для process_task."""

    task_id: str
    context_id: str
    session_id: str
    content: str
    branch_id: str
    is_resume: bool
    files_data: list[FileRef]
    message: Message | None
    metadata: JsonObject | None
    user_id: str
    is_takeover_user_reply: bool
    takeover_work_item_id: str | None

    def __init__(
        self,
        task_id: str,
        context_id: str,
        session_id: str,
        content: str,
        branch_id: str,
        is_resume: bool,
        files_data: list[FileRef],
        message: Message | None,
        metadata: JsonObject | None,
        user_id: str | None = None,
        is_takeover_user_reply: bool = False,
        takeover_work_item_id: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.context_id = context_id
        self.session_id = session_id
        self.content = content
        self.branch_id = branch_id
        self.is_resume = is_resume
        self.files_data = files_data
        self.message = message
        self.metadata = metadata
        self.user_id = user_id or context_id
        self.is_takeover_user_reply = is_takeover_user_reply
        self.takeover_work_item_id = takeover_work_item_id
