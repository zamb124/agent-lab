"""
Конфигурация для CRM Service.

Расширяет BaseSettings добавляя специфичные для CRM поля.
"""


from pydantic import Field

from core.config import BaseSettings


class CRMSettings(BaseSettings):
    """
    Настройки CRM сервиса.

    Наследуется от BaseSettings, добавляя специфичные для CRM поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    URL сервиса flows берется из server.flows_service_url (SERVER__FLOWS_SERVICE_URL).
    """

    rag_namespace_prefix: str = Field(
        default="crm_",
        description="Префикс namespace для CRM сущностей в RAG"
    )
    max_entities_per_company: int = Field(
        default=10000,
        description="Максимальное количество сущностей на компанию"
    )
    max_notes_per_company: int = Field(
        default=50000,
        description="Максимальное количество заметок на компанию"
    )
    max_tasks_per_company: int = Field(
        default=10000,
        description="Максимальное количество задач на компанию"
    )
    dedup_rag_max_concurrent_searches: int = Field(
        default=16,
        description="Максимум параллельных RAG-поисков при дедупликации извлечённых сущностей",
    )
    dedup_rag_search_limit: int = Field(
        default=5,
        ge=1,
        le=32,
        description="Сколько кандидатов из RAG (top по similarity) на извлечённую сущность при дедупе",
    )
    dedup_llm_max_concurrent_batch_requests: int = Field(
        default=10,
        description="Максимум параллельных A2A-запросов батч-дедупа (чанки пар к deduplicate_batch)",
    )
    dedup_batch_max_pairs_per_request: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Не больше 5 пар в одном вызове skill deduplicate_batch",
    )
    taskiq_sync_timeout_seconds: float = Field(
        default=300.0,
        ge=1.0,
        description="Таймаут ожидания TaskIQ (analyze/apply) при синхронном HTTP: kiq + wait_result",
    )
    analysis_draft_repair_a2a_timeout_seconds: float = Field(
        default=120.0,
        ge=15.0,
        le=600.0,
        description="HTTP-таймаут A2A при починке черновика AI (ветка draft_repair CRM flow), сек.",
    )
    daily_summary_chunk_size: int = Field(
        default=5,
        ge=1,
        le=32,
        description="Размер чанка заметок в map-reduce daily summary (skills summarize_chunk / summarize_merge)",
    )
    daily_summary_map_reduce_max_concurrent: int = Field(
        default=8,
        ge=1,
        le=64,
        description="Максимум параллельных A2A-вызовов на один уровень map-reduce daily summary",
    )
    period_summary_max_days: int = Field(
        default=31,
        ge=1,
        le=366,
        description="Максимум календарных дней в одном запросе period summary (CRM)",
    )
    note_attachment_markdown_format_enabled: bool = Field(
        default=True,
        description=(
            "Фоновое форматирование текста заметки (description) через provider_litserve "
            "POST /v1/text/format_markdown после вставки текста из файла во вложение."
        ),
    )
    note_markdown_format_service_timeout_seconds: float = Field(
        default=120.0,
        ge=10.0,
        le=600.0,
        description="Таймаут HTTP к provider_litserve для задачи форматирования Markdown заметки.",
    )


_crm_settings: CRMSettings | None = None


def get_crm_settings() -> CRMSettings:
    """
    Получает настройки CRM сервиса.

    Создает CRMSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для CRM.
    """
    global _crm_settings
    if _crm_settings is None:
        from core.config import set_settings as core_set_settings
        from core.config.loader import load_merged_config

        merged_config = load_merged_config(service_name="crm", silent=True)
        _crm_settings = CRMSettings(**merged_config)
        core_set_settings(_crm_settings)

    return _crm_settings


def reset_crm_settings():
    """Сбрасывает настройки (для тестов)"""
    global _crm_settings
    _crm_settings = None

