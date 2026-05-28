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
