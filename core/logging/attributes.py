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
LOG_TEST_SCOPE = "test_scope"  # метка теста для MockLLM (TESTING)
LOG_CONTEXT_ID = "context_id"  # context_id исполнения flow (A2A / code_agent)
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
LOG_TASK_QUEUE_WAIT_MS = "task.queue_wait_ms"
LOG_TASK_LOCK_WAIT_MS = "task.lock_wait_ms"
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
LOG_LLM_TTFT_MS = "llm.ttft_ms"
LOG_LLM_OUTPUT_TPS = "llm.output_tokens_per_second"
LOG_LLM_HAS_TOOL_CALLS = "llm.has_tool_calls"
LOG_LLM_STREAM = "llm.stream"
LOG_LLM_URL = "llm.url"

# Файлы
LOG_FILE_ID = "file.id"
LOG_FILE_SIZE = "file.size"
LOG_FILE_MIME = "file.mime"

# Voice STT / TTS (синхронизировано с core/tracing/attributes.py)
LOG_STT_PROVIDER = "stt.provider"
LOG_STT_MODEL = "stt.model"
LOG_STT_AUDIO_BYTES = "stt.audio_bytes"
LOG_STT_DURATION_MS = "stt.duration_ms"
LOG_STT_TEXT_LENGTH = "stt.text_length"
LOG_STT_MODE = "stt.mode"
LOG_STT_CHUNK_COUNT = "stt.chunk_count"

LOG_TTS_PROVIDER = "tts.provider"
LOG_TTS_VOICE = "tts.voice"
LOG_TTS_LANGUAGE = "tts.language"
LOG_TTS_TEXT_LENGTH = "tts.text_length"
LOG_TTS_AUDIO_BYTES = "tts.audio_bytes"
LOG_TTS_DURATION_MS = "tts.duration_ms"
LOG_TTS_TTFA_MS = "tts.ttfa_ms"

# Flows product SLI
LOG_FLOW_ID = "flow.id"
LOG_FLOW_FIRST_CHUNK_MS = "flow.first_content_chunk_ms"
LOG_FLOW_TERMINAL_MS = "flow.terminal_ms"
LOG_FLOW_TERMINAL_STATE = "flow.terminal_state"
LOG_FLOW_MEMORY_SUMMARIZE_MS = "flow.memory.summarize_ms"
LOG_FLOW_MEMORY_COMPACTION = "flow.memory.compaction"
LOG_FLOW_REACT_ITERATIONS = "flow.react.iterations"
LOG_FLOW_REACT_MAX_ITERATIONS = "flow.react.max_iterations"
LOG_FLOW_REACT_INTERRUPTED = "flow.react.interrupted"

# Generic operation mirror (Loki product metrics)
LOG_OPERATION_NAME = "operation_name"
LOG_OPERATION_CATEGORY = "operation_category"
LOG_OPERATION_DURATION_MS = "operation_duration_ms"
LOG_OPERATION_STATUS = "operation_status"

# Tool call
LOG_TOOL_NAME = "platform.tool.name"
LOG_TOOL_DURATION_MS = "platform.tool.duration_ms"
LOG_TOOL_ERROR = "platform.tool.error"
LOG_TOOL_IS_AGENT = "platform.tool.is_agent"

# MCP (mirror from spans)
LOG_MCP_SERVER_ID = "platform.mcp.server_id"
LOG_MCP_METHOD = "platform.mcp.method"
LOG_MCP_TOOL_NAME = "platform.mcp.tool_name"

# Node execution
LOG_NODE_TYPE = "platform.node_type"
LOG_NODE_ID = "platform.node_id"
LOG_GUEST_RUNTIME_ID = "guest_runtime.id"
LOG_GUEST_LEASE_ID = "guest_lease.id"

# Handoff / HITL
LOG_HANDOFF_WALL_MS = "platform.handoff.wall_ms"
LOG_HANDOFF_DEPTH = "platform.handoff.depth"
LOG_HANDOFF_TARGET_FLOW_ID = "platform.handoff.target_flow_id"
LOG_HITL_WAIT_MS = "platform.hitl.wait_ms"
LOG_HITL_QUEUE_SLUG = "platform.hitl.queue_slug"
LOG_HITL_WORK_ITEM_ID = "platform.hitl.work_item_id"

# RAG
LOG_RAG_DOCUMENT_ID = "platform.rag.document_id"
LOG_RAG_STAGE = "platform.rag.stage"
LOG_RAG_SEARCH_POOL_SIZE = "platform.rag.search_pool_size"

# LLM context compile
LOG_LLM_CONTEXT_COMPILE_MS = "platform.llm.context.compile_ms"
LOG_LLM_CONTEXT_SELECTED_BLOCKS = "platform.llm.context.selected_blocks_count"
LOG_LLM_CONTEXT_DROPPED_BLOCKS = "platform.llm.context.dropped_blocks_count"

# Billing settlement
LOG_BILLING_SETTLEMENT_LAG_MS = "platform.billing.settlement_lag_ms"

# WS command duration
LOG_WS_COMMAND_DURATION_MS = "ws.command_duration_ms"
LOG_WS_COMMAND_STATUS = "ws.command_status"
LOG_WS_ONLINE_USERS = "ws.online_users"
LOG_WS_ACTIVE_CHANNELS = "ws.active_channels"
LOG_WS_PRESENCE_DURATION_MS = "ws.presence_duration_ms"

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
EVENT_TASK_LOCK_ACQUIRED = "task_lock_acquired"
EVENT_WS_CONNECTED = "ws_connected"
EVENT_WS_DISCONNECTED = "ws_disconnected"
EVENT_WS_COMMAND = "ws_command"
EVENT_WS_PRESENCE_SNAPSHOT = "ws_presence_snapshot"
EVENT_LLM_REQUEST = "llm_request"
EVENT_LLM_RESPONSE = "llm_response"
EVENT_LLM_STREAM_RESPONSE = "llm_stream_response"
EVENT_VOICE_STT_RESPONSE = "voice_stt_response"
EVENT_VOICE_TTS_RESPONSE = "voice_tts_response"
EVENT_FLOW_TASK_ENQUEUED = "flow_task_enqueued"
EVENT_FLOW_FIRST_CONTENT_CHUNK = "flow_first_content_chunk"
EVENT_FLOW_MEMORY_SUMMARIZE = "flow_memory_summarize"
EVENT_FLOW_TERMINAL = "flow_terminal"
EVENT_FLOW_REACT_COMPLETED = "flow_react_completed"
EVENT_OPERATION_FINISHED = "operation_finished"
EVENT_TOOL_CALL_FINISHED = "tool_call_finished"
EVENT_LLM_CONTEXT_COMPILED = "llm_context_compiled"
EVENT_HANDOFF_WALL_TIME = "handoff_wall_time"
EVENT_HITL_OPERATOR_RESPONDED = "hitl_operator_responded"
EVENT_BILLING_SETTLEMENT_LAG = "billing_settlement_lag"
EVENT_WS_COMMAND_FINISHED = "ws_command_finished"
EVENT_PLATFORM_EVENT_PUBLISHED = "platform_event_published"
EVENT_PLATFORM_EVENT_RECEIVED = "platform_event_received"
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

# SERP quality (flat snake_case keys for Loki LogQL)
LOG_SERP_CACHE_KEY = "serp_cache_key"
LOG_SERP_QUERY = "serp_query"
LOG_SERP_MODE = "serp_mode"
LOG_SERP_RESULTS_COUNT = "serp_results_count"
LOG_SERP_TOTAL_COUNT = "serp_total_count"
LOG_SERP_PROVIDERS_SELECTED = "serp_providers_selected"
LOG_SERP_CLICK_URL = "serp_click_url"
LOG_SERP_CLICK_POSITION = "serp_click_position"
LOG_SERP_CLICK_PROVIDER = "serp_click_provider"

EVENT_SEARCH_SERP_SERVED = "search.serp.served"
EVENT_SEARCH_SERP_CLICK = "search.serp.click"

EVENT_REDIS_INVENTORY_TICK_STARTED = "redis.inventory.tick_started"
EVENT_REDIS_INVENTORY_TICK_COMPLETED = "redis.inventory.tick_completed"
EVENT_REDIS_INVENTORY_TICK_FAILED = "redis.inventory.tick_failed"
EVENT_REDIS_INVENTORY_DB_SUMMARY = "redis.inventory.db_summary"
EVENT_REDIS_INVENTORY_STREAM_LENGTH = "redis.inventory.stream_length"
EVENT_REDIS_INVENTORY_PREFIX_STATS = "redis.inventory.prefix_stats"

LOG_REDIS_DB = "redis_db"
LOG_REDIS_URL_LABEL = "redis_url_label"
LOG_REDIS_DBSIZE = "dbsize"
LOG_REDIS_USED_MEMORY_BYTES = "used_memory_bytes"
LOG_REDIS_MAXMEMORY_BYTES = "maxmemory_bytes"
LOG_REDIS_KEYS_SCANNED = "keys_scanned"
LOG_REDIS_NO_TTL_TOTAL = "no_ttl_total"
LOG_REDIS_SCAN_MISMATCH = "scan_dbsize_mismatch"
LOG_REDIS_STREAM_NAME = "stream_name"
LOG_REDIS_STREAM_XLEN = "stream_xlen"
LOG_REDIS_STREAM_MAXLEN = "stream_maxlen"
LOG_REDIS_PREFIX = "redis_prefix"
LOG_REDIS_PREFIX_KEY_COUNT = "prefix_key_count"
LOG_REDIS_PREFIX_NO_TTL_COUNT = "prefix_no_ttl_count"
LOG_REDIS_PREFIX_SAMPLE_MEMORY_BYTES = "prefix_sample_memory_bytes"
LOG_REDIS_PLATFORM_SCHEDULES_COUNT = "platform_schedules_count"
LOG_REDIS_INVENTORY_DURATION_MS = "redis_inventory_duration_ms"

LOG_SCHEDULE_TASK_ID = "schedule_task_id"
LOG_SCHEDULE_ID = "schedule_id"
LOG_CRAWL_SCHEDULE_RECREATE = "recreate_schedule"
