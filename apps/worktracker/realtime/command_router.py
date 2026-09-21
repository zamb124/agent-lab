"""Регистрация WS command-handler'ов worktracker в `core.websocket`."""

from __future__ import annotations

from apps.worktracker.container import WorktrackerContainer, get_worktracker_container
from apps.worktracker.realtime.operations import (
    BoardIdPayload,
    BoardsListPayload,
    BoardUpdatePayload,
    WorkItemAssignPayload,
    WorkItemCommentPayload,
    WorkItemCompletePayload,
    WorkItemIdPayload,
    WorkItemMovePayload,
    WorkItemsListPayload,
    WorkItemsMineSummaryPayload,
    WorkItemUpdatePayload,
    WorkQueueIdPayload,
    WorkQueueMemberAddPayload,
    WorkQueueMemberRemovePayload,
    WorkQueuesListPayload,
    WorkQueueUpdatePayload,
    op_boards_create,
    op_boards_get,
    op_boards_list,
    op_boards_update,
    op_work_items_assign,
    op_work_items_cancel,
    op_work_items_claim,
    op_work_items_comment,
    op_work_items_comments_list,
    op_work_items_complete,
    op_work_items_create,
    op_work_items_get,
    op_work_items_list,
    op_work_items_mine_summary,
    op_work_items_move,
    op_work_items_update,
    op_work_queues_create,
    op_work_queues_delete,
    op_work_queues_list,
    op_work_queues_member_add,
    op_work_queues_member_remove,
    op_work_queues_members_list,
    op_work_queues_update,
)
from core.logging import get_logger
from core.websocket import Operation, RegisteredOperation, register_service_operations
from core.worktracker.requests import (
    BoardCreateRequest,
    WorkItemCreateRequest,
    WorkQueueCreateRequest,
)

logger = get_logger(__name__)

WORKTRACKER_OPERATIONS: dict[str, RegisteredOperation[WorktrackerContainer]] = {
    "worktracker/work_items/list_requested": Operation(
        payload_model=WorkItemsListPayload, fn=op_work_items_list
    ),
    "worktracker/work_items/mine_summary_requested": Operation(
        payload_model=WorkItemsMineSummaryPayload, fn=op_work_items_mine_summary
    ),
    "worktracker/work_items/item_requested": Operation(
        payload_model=WorkItemIdPayload, fn=op_work_items_get
    ),
    "worktracker/work_items/create_requested": Operation(
        payload_model=WorkItemCreateRequest, fn=op_work_items_create
    ),
    "worktracker/work_items/update_requested": Operation(
        payload_model=WorkItemUpdatePayload, fn=op_work_items_update
    ),
    "worktracker/work_items/assign_requested": Operation(
        payload_model=WorkItemAssignPayload, fn=op_work_items_assign
    ),
    "worktracker/work_items/move_requested": Operation(
        payload_model=WorkItemMovePayload, fn=op_work_items_move
    ),
    "worktracker/work_items/claim_requested": Operation(
        payload_model=WorkItemIdPayload, fn=op_work_items_claim
    ),
    "worktracker/work_items/comment_requested": Operation(
        payload_model=WorkItemCommentPayload, fn=op_work_items_comment
    ),
    "worktracker/work_items/comments_list_requested": Operation(
        payload_model=WorkItemIdPayload, fn=op_work_items_comments_list
    ),
    "worktracker/work_items/complete_requested": Operation(
        payload_model=WorkItemCompletePayload, fn=op_work_items_complete
    ),
    "worktracker/work_items/cancel_requested": Operation(
        payload_model=WorkItemIdPayload, fn=op_work_items_cancel
    ),
    "worktracker/boards/list_requested": Operation(
        payload_model=BoardsListPayload, fn=op_boards_list
    ),
    "worktracker/boards/item_requested": Operation(
        payload_model=BoardIdPayload, fn=op_boards_get
    ),
    "worktracker/boards/create_requested": Operation(
        payload_model=BoardCreateRequest, fn=op_boards_create
    ),
    "worktracker/boards/update_requested": Operation(
        payload_model=BoardUpdatePayload, fn=op_boards_update
    ),
    "worktracker/work_queues/list_requested": Operation(
        payload_model=WorkQueuesListPayload, fn=op_work_queues_list
    ),
    "worktracker/work_queues/create_requested": Operation(
        payload_model=WorkQueueCreateRequest, fn=op_work_queues_create
    ),
    "worktracker/work_queues/update_requested": Operation(
        payload_model=WorkQueueUpdatePayload, fn=op_work_queues_update
    ),
    "worktracker/work_queues/remove_requested": Operation(
        payload_model=WorkQueueIdPayload, fn=op_work_queues_delete
    ),
    "worktracker/work_queues/members_list_requested": Operation(
        payload_model=WorkQueueIdPayload, fn=op_work_queues_members_list
    ),
    "worktracker/work_queues/member_add_requested": Operation(
        payload_model=WorkQueueMemberAddPayload, fn=op_work_queues_member_add
    ),
    "worktracker/work_queues/member_remove_requested": Operation(
        payload_model=WorkQueueMemberRemovePayload, fn=op_work_queues_member_remove
    ),
}


def register_worktracker_ws_commands() -> None:
    register_service_operations(WORKTRACKER_OPERATIONS, get_worktracker_container)
    logger.info("worktracker.ws.command.handlers", WORKTRACKER_OPERATIONS_count=len(WORKTRACKER_OPERATIONS))
