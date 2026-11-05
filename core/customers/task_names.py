"""Declaration-модуль задач customer-auth (очередь ``idle``)."""

from core.tasks import declare_task

CUSTOMER_AUTH_TG_POLL = declare_task(
    "customer_auth_tg_poll", queue="idle", scheduled=True, retry=True
)
