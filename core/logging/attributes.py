"""
Канонические имена ключей для structured-логов.

Имена выровнены с OpenTelemetry semantic conventions
(https://opentelemetry.io/docs/specs/semconv/) и с core.tracing.attributes
там, где есть пересечение по доменам (LLM, HTTP, биллинг). Использовать
только эти константы в hot-path кода — иначе схему не получится
анализировать в едином агрегаторе.
"""

# Сервис / окружение
LOG_SERVICE_NAME = "service.name"
LOG_SERVICE_VERSION = "service.version"
LOG_DEPLOYMENT_ENVIRONMENT = "deployment.environment"

# Запрос / контекст
LOG_REQUEST_ID = "request_id"
LOG_TRACE_ID = "trace_id"
LOG_SPAN_ID = "span_id"

LOG_USER_ID = "user_id"
LOG_COMPANY_ID = "company_id"
LOG_COMPANY_SUBDOMAIN = "company_subdomain"
LOG_SESSION_ID = "session_id"  # JWT / WebSocket — авторизационная сессия
LOG_SESSION_AGENT = "session_agent"  # flow_id:context_id — сессия исполнения агента flows
LOG_NAMESPACE = "namespace"

# HTTP (OTel: http.request.method, http.route, http.response.status_code)
LOG_HTTP_METHOD = "http.method"
LOG_HTTP_ROUTE = "http.route"
LOG_HTTP_PATH = "http.path"
LOG_HTTP_STATUS_CODE = "http.status_code"
LOG_HTTP_DURATION_MS = "http.duration_ms"
LOG_HTTP_REQUEST_SIZE = "http.request.size"
LOG_HTTP_RESPONSE_SIZE = "http.response.size"
LOG_HTTP_USER_AGENT = "http.user_agent"
LOG_HTTP_CLIENT_IP = "http.client_ip"

# WebSocket
LOG_WS_PATH = "ws.path"
LOG_WS_COMMAND = "ws.command"
LOG_WS_REQUEST_ID = "ws.request_id"

# Задача TaskIQ
LOG_TASK_ID = "task.id"
LOG_TASK_NAME = "task.name"
LOG_TASK_QUEUE = "task.queue"
LOG_TASK_DURATION_MS = "task.duration_ms"
LOG_TASK_RETRY = "task.retry"
LOG_TASK_KIND = "task.kind"

# DB
LOG_DB_SYSTEM = "db.system"
LOG_DB_OPERATION = "db.operation"
LOG_DB_STATEMENT = "db.statement"
LOG_DB_DURATION_MS = "db.duration_ms"

# LLM (синхронизировано с core/tracing/attributes.py платформенными ключами)
LOG_LLM_PROVIDER = "llm.provider"
LOG_LLM_MODEL = "llm.model"
LOG_LLM_SOURCE = "llm.source"
LOG_LLM_INPUT_TOKENS = "llm.tokens.input"
LOG_LLM_OUTPUT_TOKENS = "llm.tokens.output"
LOG_LLM_TOTAL_TOKENS = "llm.tokens.total"
LOG_LLM_DURATION_MS = "llm.duration_ms"
LOG_LLM_HAS_TOOL_CALLS = "llm.has_tool_calls"
LOG_LLM_STREAM = "llm.stream"
LOG_LLM_URL = "llm.url"

# Файлы
LOG_FILE_ID = "file.id"
LOG_FILE_SIZE = "file.size"
LOG_FILE_MIME = "file.mime"

# Исключение
LOG_EXCEPTION_TYPE = "exception.type"
LOG_EXCEPTION_MESSAGE = "exception.message"
LOG_EXCEPTION_STACKTRACE = "exception.stacktrace"

# Канонические имена событий (используются как `event=`)
EVENT_HTTP_REQUEST = "http_request"
EVENT_HTTP_REQUEST_FAILED = "http_request_failed"
EVENT_TASK_STARTED = "task_started"
EVENT_TASK_FINISHED = "task_finished"
EVENT_TASK_FAILED = "task_failed"
EVENT_TASK_SCHEDULED = "task_scheduled"
EVENT_WS_CONNECTED = "ws_connected"
EVENT_WS_DISCONNECTED = "ws_disconnected"
EVENT_WS_COMMAND = "ws_command"
EVENT_LLM_REQUEST = "llm_request"
EVENT_LLM_RESPONSE = "llm_response"
EVENT_LLM_STREAM_RESPONSE = "llm_stream_response"
EVENT_UI_EVENT_PUBLISHED = "ui_event_published"
EVENT_UI_EVENT_RECEIVED = "ui_event_received"
EVENT_BACKGROUND_TASK_STARTED = "background_task_started"
EVENT_BACKGROUND_TASK_FAILED = "background_task_failed"

# Crawl / RuNet indexing (flat snake_case keys for Loki LogQL)
LOG_CRAWL_PROFILE_ID = "crawl_profile_id"
LOG_SEARCH_INDEX_ID = "search_index_id"
LOG_CRAWL_JOB_ID = "crawl_job_id"
LOG_CRAWL_DOMAIN_ID = "crawl_domain_id"
LOG_CRAWL_URL_ID = "crawl_url_id"
LOG_CRAWL_DOMAIN = "domain"
LOG_CRAWL_CANONICAL_URL = "canonical_url"
LOG_CRAWL_OUTCOME = "crawl_outcome"
LOG_CRAWL_SKIP_REASON = "crawl_skip_reason"
LOG_CRAWL_FETCH_TRANSPORT = "fetch_transport"
LOG_CRAWL_FETCH_DURATION_MS = "fetch_duration_ms"
LOG_CRAWL_BROWSER_FALLBACK = "browser_fallback"
LOG_CRAWL_EXTRACT_CHARS = "extract_chars"
LOG_CRAWL_CONTENT_HASH_CHANGED = "content_hash_changed"
LOG_CRAWL_FETCH_ATTEMPTS = "fetch_attempts"
LOG_CRAWL_URLS_DISCOVERED = "urls_discovered"
LOG_CRAWL_URLS_INSERTED = "urls_inserted"
LOG_CRAWL_URLS_UPDATED = "urls_updated"
LOG_CRAWL_DOMAINS_SCHEDULED = "domains_scheduled"
LOG_CRAWL_PENDING_URLS = "pending_urls"
LOG_CRAWL_PARALLEL_FETCH_ENQUEUED = "parallel_fetch_enqueued"
LOG_CRAWL_SITEMAP_ERROR_KIND = "sitemap_error_kind"
LOG_CRAWL_ENRICHMENT_MODEL = "enrichment_model"
LOG_CRAWL_ENRICHMENT_PROVIDER = "enrichment_provider"
LOG_CRAWL_ENRICHMENT_CHUNK_COUNT = "enrichment_chunk_count"
LOG_CRAWL_ENRICHMENT_PROMPT_VERSION = "enrichment_prompt_version"
LOG_CRAWL_ENRICHMENT_DURATION_MS = "enrichment_duration_ms"
LOG_CRAWL_DOCUMENT_ID = "document_id"
LOG_CRAWL_RAG_NAMESPACE_ID = "rag_namespace_id"
LOG_CRAWL_INGEST_DURATION_MS = "ingest_duration_ms"
LOG_CRAWL_SEED_IMPORTED = "seed_imported"
LOG_CRAWL_SEED_SKIPPED = "seed_skipped"
LOG_CRAWL_RECLAIMED_FETCHING = "reclaimed_fetching"
LOG_CRAWL_REQUEUED_FAILED = "requeued_failed"
LOG_CRAWL_STALE_JOBS_FINISHED = "stale_jobs_finished"
LOG_CRAWL_TRIGGER = "crawl_trigger"
LOG_CRAWL_BOOTSTRAP_ACTION = "action"
LOG_CRAWL_DOMAIN_COUNT = "domain_count"
LOG_CRAWL_URL_BUDGET = "url_budget"

EVENT_CRAWL_BOOTSTRAP = "crawl.bootstrap"
EVENT_CRAWL_TICK_STARTED = "crawl.tick.started"
EVENT_CRAWL_TICK_COMPLETED = "crawl.tick.completed"
EVENT_CRAWL_TICK_FAILED = "crawl.tick.failed"
EVENT_CRAWL_DISCOVER_COMPLETED = "crawl.discover.completed"
EVENT_CRAWL_DISCOVER_FAILED = "crawl.discover.failed"
EVENT_CRAWL_FETCH_COMPLETED = "crawl.fetch.completed"
EVENT_CRAWL_FETCH_FAILED = "crawl.fetch.failed"
EVENT_CRAWL_URL_OUTCOME = "crawl.url.outcome"
EVENT_CRAWL_INGEST_COMPLETED = "crawl.ingest.completed"
EVENT_CRAWL_INGEST_FAILED = "crawl.ingest.failed"
EVENT_CRAWL_ENRICH_COMPLETED = "crawl.enrich.completed"
EVENT_CRAWL_ENRICH_FAILED = "crawl.enrich.failed"
EVENT_CRAWL_REINGEST_COMPLETED = "crawl.reingest.completed"
EVENT_CRAWL_SEED_COMPLETED = "crawl.seed.completed"
EVENT_CRAWL_RECLAIM_COMPLETED = "crawl.reclaim.completed"
EVENT_CRAWL_DOMAIN_SCHEDULED = "crawl.domain.scheduled"
EVENT_BROWSER_CRAWL_FETCH_COMPLETED = "browser.crawl_fetch.completed"
EVENT_BROWSER_CRAWL_FETCH_FAILED = "browser.crawl_fetch.failed"
EVENT_CRAWL_SCHEDULE_EXISTS = "crawl.schedule.exists"
EVENT_CRAWL_SCHEDULE_CREATED = "crawl.schedule.created"
EVENT_CRAWL_SCHEDULE_RESUMED = "crawl.schedule.resumed"
EVENT_CRAWL_SCHEDULE_RECONCILED = "crawl.schedule.reconciled"
LOG_SCHEDULE_TASK_ID = "schedule_task_id"
LOG_SCHEDULE_ID = "schedule_id"
LOG_CRAWL_SCHEDULE_RECREATE = "recreate_schedule"
