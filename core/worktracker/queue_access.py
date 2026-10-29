"""Port for work_queue OpenFGA access (implemented in apps.worktracker)."""

from __future__ import annotations

from typing import Literal, Protocol

WorkQueueMemberRelation = Literal["owner", "member"]


class WorkQueueAccessPort(Protocol):
    async def resolve_company_admin_owner(self, company_id: str) -> str: ...

    async def sync_queue_created(
        self,
        work_queue_id: str,
        *,
        company_id: str,
        owner_user_id: str,
    ) -> None: ...

    async def set_member(
        self,
        work_queue_id: str,
        *,
        user_id: str,
        relation: WorkQueueMemberRelation,
    ) -> None: ...

    async def remove_member(self, work_queue_id: str, *, user_id: str) -> None: ...

    async def sync_queue_deleted(self, work_queue_id: str) -> None: ...

    async def list_member_rows_by_user_id_asc(
        self, work_queue_id: str
    ) -> list[tuple[str, WorkQueueMemberRelation]]: ...

    async def list_viewable_queue_ids(self, *, user_id: str) -> list[str]: ...
