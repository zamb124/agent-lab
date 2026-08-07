"""
Типы для каналов коммуникации.
"""

from dataclasses import dataclass
from typing import TypeAlias

from a2a.types import Message
from pydantic import Field

from apps.flows.src.a2a.interaction_parser import FlowUIInboundCommand
from core.a2a.representation import A2ARepresentationSnapshot
from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.models.context_models import Context
from core.state import ExecutionTaskState, InterruptData
from core.types import JsonObject

ChannelRequestContext: TypeAlias = Context | JsonObject | None


@dataclass(frozen=True)
class FlowExecutionTarget:
    """Явный target для TaskIQ kick после channel routing."""

    flow_id: str
    session_id: str
    context_id: str
    branch_id: str
    is_resume: bool


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
    a2a_representation: A2ARepresentationSnapshot
    flow_ui_command: FlowUIInboundCommand | None
    user_id: str
    initiator_user_id: str | None
    is_takeover_user_reply: bool
    takeover_work_item_id: str | None
    is_handoff_user_reply: bool
    handoff_child_session_id: str | None
    handoff_child_flow_id: str | None
    handoff_child_branch_id: str | None

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
        a2a_representation: A2ARepresentationSnapshot | None = None,
        flow_ui_command: FlowUIInboundCommand | None = None,
        user_id: str | None = None,
        initiator_user_id: str | None = None,
        is_takeover_user_reply: bool = False,
        takeover_work_item_id: str | None = None,
        is_handoff_user_reply: bool = False,
        handoff_child_session_id: str | None = None,
        handoff_child_flow_id: str | None = None,
        handoff_child_branch_id: str | None = None,
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
        self.a2a_representation = a2a_representation or A2ARepresentationSnapshot()
        self.flow_ui_command = flow_ui_command
        self.user_id = user_id or context_id
        self.initiator_user_id = initiator_user_id
        self.is_takeover_user_reply = is_takeover_user_reply
        self.takeover_work_item_id = takeover_work_item_id
        self.is_handoff_user_reply = is_handoff_user_reply
        self.handoff_child_session_id = handoff_child_session_id
        self.handoff_child_flow_id = handoff_child_flow_id
        self.handoff_child_branch_id = handoff_child_branch_id
