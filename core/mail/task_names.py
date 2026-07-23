"""Declaration-модуль почтовых задач (очередь ``idle``).

Лёгкий: только объявления. Импортируется producer'ами (core/mail/enqueue.py,
service.py) и impl-модулями idle worker (apps/idle_worker/tasks/mail_*).
"""

from core.tasks import declare_task

MAIL_SYNC_TICK = declare_task("mail_sync_tick", queue="idle", scheduled=True)
MAIL_SYNC_BINDING = declare_task("mail_sync_binding", queue="idle")
MAIL_MARK_SEEN = declare_task("mail_mark_seen", queue="idle")
MAIL_MARK_UNSEEN = declare_task("mail_mark_unseen", queue="idle")
MAIL_SEND = declare_task("mail_send", queue="idle")
MAIL_MOVE = declare_task("mail_move", queue="idle")
MAIL_TRASH = declare_task("mail_trash", queue="idle")
MAIL_ARCHIVE = declare_task("mail_archive", queue="idle")
MAIL_DELETE = declare_task("mail_delete", queue="idle")
MAIL_STAR = declare_task("mail_star", queue="idle")
MAIL_RAG_INDEX = declare_task("mail_rag_index", queue="idle")
MAIL_IDLE_SUPERVISOR = declare_task("mail_idle_supervisor", queue="idle", scheduled=True)

__all__ = [
    "MAIL_ARCHIVE",
    "MAIL_DELETE",
    "MAIL_IDLE_SUPERVISOR",
    "MAIL_MARK_SEEN",
    "MAIL_MARK_UNSEEN",
    "MAIL_MOVE",
    "MAIL_RAG_INDEX",
    "MAIL_SEND",
    "MAIL_STAR",
    "MAIL_SYNC_BINDING",
    "MAIL_SYNC_TICK",
    "MAIL_TRASH",
]
