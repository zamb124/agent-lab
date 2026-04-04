"""API роутер для тредов (Threads)."""

from fastapi import APIRouter, Depends

from apps.sync.container import get_sync_container
from apps.sync.models.common import PaginationRequest
from apps.sync.models.threads import ThreadRead, ThreadCreate, ThreadRow
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.config import get_settings
from core.context import get_context

router = APIRouter()


@router.get("/")
async def list_threads(
    channel_id: str,
    pagination: PaginationRequest = Depends(),
) -> list[ThreadRow]:
    """Список тредов в канале."""
    context = get_context()
    container = get_sync_container()
    threads = await container.thread_repository.list_by_channel(
        channel_id, limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    return [
        ThreadRow(
            id=t.thread_id,
            channel_id=t.channel_id,
            root_message_id=t.root_message_id,
            title=t.title,
            created_at=t.created_at,
            created_by_user_id=t.created_by_user_id,
        )
        for t in threads
    ]


@router.post("/", status_code=201)
async def create_thread(channel_id: str, body: ThreadCreate) -> ThreadRead:
    """Создание треда через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="threads.create",
        payload={"body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(
        timeout=get_settings().sync_taskiq_wait_result_timeout_seconds,
    )
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return ThreadRead.model_validate(res.return_value["result"])


@router.get("/{thread_id}")
async def get_thread(thread_id: str) -> ThreadRow:
    """Получение треда по ID."""
    container = get_sync_container()
    thread = await container.thread_repository.get(thread_id)
    if thread is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadRow(
        id=thread.thread_id,
        channel_id=thread.channel_id,
        root_message_id=thread.root_message_id,
        title=thread.title,
        created_at=thread.created_at,
        created_by_user_id=thread.created_by_user_id,
    )
