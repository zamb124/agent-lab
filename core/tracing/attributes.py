"""
Semantic Conventions для Platform трейсинга.

Все атрибуты имеют префикс 'platform.' для namespace изоляции.
"""

# Журнал по сущности (дублируются в колонках spans при сохранении, плюс иерархия OTEL)
ATTR_EVENT_TYPE = "platform.event_type"
ATTR_RESOURCE_TYPE = "platform.resource.type"
ATTR_RESOURCE_ID = "platform.resource.id"

ATTR_TENANT_COMPANY_ID = "platform.tenant.company_id"
ATTR_TENANT_NAMESPACE = "platform.tenant.namespace"
ATTR_SERVICE_NAME = "platform.service_name"

# Идентификаторы пользователя
ATTR_USER_ID = "platform.user.id"
ATTR_USER_NAME = "platform.user.name"
ATTR_USER_GROUPS = "platform.user.groups"

# Сессии
ATTR_SESSION_AUTH = "platform.session.auth"
ATTR_SESSION_AGENT = "platform.session.agent"

# Основные идентификаторы
ATTR_TASK_ID = "platform.task_id"
ATTR_CONTEXT_ID = "platform.context_id"
ATTR_CHANNEL = "platform.channel"
ATTR_IS_RESUME = "platform.is_resume"

# Агент
ATTR_FLOW_ID = "platform.flow_id"
ATTR_FLOW_ENTRY = "platform.flow.entry_node"
ATTR_FLOW_VARIABLES_COUNT = "platform.flow.variables_count"
ATTR_BRANCH_ID = "platform.branch_id"

# Нода
ATTR_NODE_ID = "platform.node_id"
ATTR_NODE_TYPE = "platform.node_type"
ATTR_NODE_ITERATION = "platform.node.iteration"

# Durable workflow runtime
ATTR_WORKFLOW_SESSION_ID = "platform.workflow.session_id"
ATTR_WORKFLOW_EXECUTION_BRANCH_ID = "platform.workflow.execution_branch_id"
ATTR_WORKFLOW_NODE_SCHEDULE_SEQUENCE = "platform.workflow.node_schedule_sequence"

# Agent handoff между flows (не HITL handoff_mode)
ATTR_HANDOFF_PARENT_SESSION_ID = "platform.handoff.parent_session_id"
ATTR_HANDOFF_CHILD_SESSION_ID = "platform.handoff.child_session_id"
ATTR_HANDOFF_TARGET_FLOW_ID = "platform.handoff.target_flow_id"
ATTR_HANDOFF_DEPTH = "platform.handoff.depth"
ATTR_HANDOFF_PHASE = "platform.handoff.phase"
ATTR_HANDOFF_TRACE_ID = "platform.handoff.trace_id"

# HITL
ATTR_HITL_COMMAND_ID = "platform.hitl.command_id"
ATTR_HITL_CORRELATION_ID = "platform.hitl.correlation_id"
ATTR_HITL_QUEUE_SLUG = "platform.hitl.queue_slug"
ATTR_HITL_WORK_ITEM_ID = "platform.hitl.work_item_id"

# Память
ATTR_MEMORY_CURSOR_KEY = "platform.memory.cursor_key"
ATTR_MEMORY_CURSOR_START = "platform.memory.cursor_start"
ATTR_MEMORY_CURSOR_END = "platform.memory.cursor_end"
ATTR_MEMORY_SCOPE = "platform.memory.scope"
ATTR_MEMORY_COMPACTION = "platform.memory.compaction"
ATTR_MEMORY_SUMMARIZE_MS = "platform.memory.summarize_ms"

# Рефлексия
ATTR_REFLECTION_POLICY_ID = "platform.reflection.policy_id"
ATTR_REFLECTION_GATE = "platform.reflection.gate"
ATTR_REFLECTION_TARGET = "platform.reflection.target"

# MCP
ATTR_MCP_SERVER_ID = "platform.mcp.server_id"
ATTR_MCP_METHOD = "platform.mcp.method"
ATTR_MCP_PROTOCOL_VERSION = "platform.mcp.protocol_version"
ATTR_MCP_HAS_SESSION = "platform.mcp.has_session"
ATTR_MCP_NOTIFICATION = "platform.mcp.notification"
ATTR_MCP_REQUEST_PREVIEW = "platform.mcp.request_preview"
ATTR_MCP_TOOL_NAME = "platform.mcp.tool_name"
ATTR_MCP_TOOL_ARGS_KEYS = "platform.mcp.tool_args_keys"
ATTR_MCP_RESPONSE_CONTENT_TYPE = "platform.mcp.response_content_type"
ATTR_MCP_RESPONSE_BYTES = "platform.mcp.response_bytes"
ATTR_MCP_RESPONSE_SHA256 = "platform.mcp.response_sha256"
ATTR_MCP_RESPONSE_PREVIEW = "platform.mcp.response_preview"
ATTR_MCP_RESPONSE_SESSION_ID = "platform.mcp.response_session_id"

# Агент
ATTR_AGENT_NAME = "platform.agent.name"
ATTR_AGENT_ID = "platform.agent.id"
ATTR_AGENT_PROMPT_LENGTH = "platform.agent.prompt_length"
ATTR_AGENT_TOOLS_COUNT = "platform.agent.tools_count"

# ReAct
ATTR_REACT_ITERATION = "platform.react.iteration"
ATTR_LLM_NODE_LABEL = "platform.llm_node.label"

# LLM
ATTR_LLM_MODEL = "platform.llm.model"
ATTR_LLM_PROVIDER = "platform.llm.provider"
ATTR_LLM_REQUESTED_MODEL = "platform.llm.requested_model"
ATTR_LLM_CANDIDATE_SOURCE = "platform.llm.candidate_source"
# Стоимость из ответа провайдера (OpenRouter: usage.cost в USD; расширения OpenAI-совместимых API)
ATTR_LLM_PROVIDER_REPORTED_COST = "platform.llm.provider_reported_cost"
# OpenRouter BYOK: поле usage.cost_details.upstream_inference_cost
ATTR_LLM_PROVIDER_UPSTREAM_INFERENCE_COST = "platform.llm.provider_upstream_inference_cost"
ATTR_LLM_INPUT_TOKENS = "platform.llm.input_tokens"
ATTR_LLM_OUTPUT_TOKENS = "platform.llm.output_tokens"
ATTR_LLM_TOTAL_TOKENS = "platform.llm.total_tokens"
ATTR_LLM_DURATION_MS = "platform.llm.duration_ms"
ATTR_LLM_TTFT_MS = "platform.llm.ttft_ms"
ATTR_LLM_OUTPUT_TPS = "platform.llm.output_tokens_per_second"
ATTR_LLM_HAS_TOOL_CALLS = "platform.llm.has_tool_calls"
ATTR_LLM_STREAM = "platform.llm.stream"
ATTR_LLM_REQUEST = "platform.llm.request"
ATTR_LLM_RESPONSE = "platform.llm.response"
ATTR_LLM_CONTEXT = "platform.llm.context"
ATTR_LLM_CONTEXT_ENABLED = "platform.llm.context.enabled"
ATTR_LLM_CONTEXT_SELECTED_BLOCKS_COUNT = "platform.llm.context.selected_blocks_count"
ATTR_LLM_CONTEXT_DROPPED_BLOCKS_COUNT = "platform.llm.context.dropped_blocks_count"
ATTR_LLM_CONTEXT_TOTAL_INPUT_TOKENS = "platform.llm.context.total_input_tokens"
ATTR_LLM_CONTEXT_MAX_INPUT_TOKENS = "platform.llm.context.max_input_tokens"
ATTR_LLM_CONTEXT_MODEL_CONTEXT_LENGTH = "platform.llm.context.model_context_length"
ATTR_LLM_CONTEXT_COMPILE_MS = "platform.llm.context.compile_ms"
ATTR_LLM_CONTEXT_TOOL_BLOCKS_COMPACTED = "platform.llm.context.tool_blocks_compacted"
# число LLM-попыток внутри одной операции (retry) и тип последней ошибки попытки
ATTR_LLM_ATTEMPTS = "platform.llm.attempts"
ATTR_LLM_ATTEMPT_ERROR = "platform.llm.attempt_error"

ATTR_TASK_QUEUE_WAIT_MS = "platform.task.queue_wait_ms"
ATTR_TASK_LOCK_WAIT_MS = "platform.task.lock_wait_ms"

# Инструмент (tool)
ATTR_TOOL_NAME = "platform.tool.name"
ATTR_TOOL_CALL_ID = "platform.tool.call_id"
ATTR_TOOL_ARGS = "platform.tool.args"
ATTR_TOOL_RESULT = "platform.tool.result"
ATTR_TOOL_DURATION_MS = "platform.tool.duration_ms"
ATTR_TOOL_IS_AGENT = "platform.tool.is_agent"
ATTR_TOOL_ERROR = "platform.tool.error"

# Прерывание (interrupt)
ATTR_INTERRUPT_QUESTION = "platform.interrupt.question"
ATTR_INTERRUPT_TOOL = "platform.interrupt.tool"
ATTR_INTERRUPT_PATH_DEPTH = "platform.interrupt.path_depth"

# Статус
ATTR_STATUS = "platform.status"
ATTR_ERROR_MESSAGE = "platform.error.message"
ATTR_ERROR_TYPE = "platform.error.type"

# Файлы
ATTR_FILES_COUNT = "platform.files.count"
ATTR_FILES_FILE_ID = "platform.files.file_id"
ATTR_FILES_FILE_NAME = "platform.files.file_name"
ATTR_FILES_FILE_TYPE = "platform.files.file_type"
ATTR_FILES_MIME = "platform.files.mime"
ATTR_FILES_BYTES = "platform.files.bytes"
ATTR_FILES_SOURCE = "platform.files.source"
# cache lookup: hit / miss / store
ATTR_FILES_CACHE = "platform.files.cache"
# лейн чтения страницы: text / vision / hybrid
ATTR_FILES_LANE = "platform.files.lane"
ATTR_FILES_PAGE_INDEX = "platform.files.page_index"
ATTR_FILES_PAGES_COUNT = "platform.files.pages_count"
# вид nested-актива (изображение, вложение, …)
ATTR_FILES_ASSET_KIND = "platform.files.asset_kind"
ATTR_FILES_ASSETS_COUNT = "platform.files.assets_count"
ATTR_FILES_BATCH_INDEX = "platform.files.batch_index"
ATTR_FILES_BATCHES_COUNT = "platform.files.batches_count"
ATTR_FILES_CHARS = "platform.files.chars"
ATTR_FILES_HAS_IMAGES = "platform.files.has_images"
# режим суммаризации: structural / llm
ATTR_FILES_SUMMARY_MODE = "platform.files.summary_mode"
# байты payload после prepare_visual_payload — фактический вход vision LLM (до base64)
ATTR_FILES_PAYLOAD_BYTES = "platform.files.payload_bytes"
# nested в FileResult конверта: число элементов и суммарный размер bytes_b64
ATTR_FILES_NESTED_COUNT = "platform.files.nested_count"
ATTR_FILES_NESTED_BYTES = "platform.files.nested_bytes"

# Capability gateway
ATTR_CAPABILITY_NAME = "platform.capability.name"

# Состояние
ATTR_STATE_SNAPSHOT = "platform.state.snapshot"

# Биллинг / SaaS (связь с UsageType и resource_name в metadata usage)
ATTR_BILLING_USAGE_TYPE = "platform.billing.usage_type"
ATTR_BILLING_RESOURCE_NAME = "platform.billing.resource_name"
ATTR_BILLING_QUANTITY = "platform.billing.quantity"
# Целые рубли для settlement, если провайдер отдал USD (OpenRouter): round(usd * billing.usd_to_rub_rate)
ATTR_BILLING_SETTLEMENT_QUANTITY_RUB = "platform.billing.settlement_quantity_rub"
ATTR_BILLING_PENDING_SETTLEMENT = "platform.billing.pending_settlement"
# "platform" (стандартное списание) или "company" (BYOK / custom провайдер — биллинга нет)
ATTR_BILLING_COST_ORIGIN = "platform.billing.cost_origin"
# id custom OpenAI-compatible провайдера компании, если использовался (для аналитики)
ATTR_BILLING_CUSTOM_PROVIDER_ID = "platform.billing.custom_provider_id"
ATTR_OPERATION_CATEGORY = "platform.operation.category"
ATTR_OPERATION_LOG_MIRROR = "platform.operation.log_mirror"

# RAG / embeddings
ATTR_EMBED_MODEL = "platform.embed.model"
ATTR_EMBED_BATCH_SIZE = "platform.embed.batch_size"
ATTR_EMBED_TEXT_COUNT = "platform.embed.text_count"
ATTR_RAG_DOCUMENT_ID = "platform.rag.document_id"
ATTR_RAG_STAGE = "platform.rag.stage"

# Sync / STT / звонки
ATTR_SYNC_COMMAND_TYPE = "platform.sync.command_type"
ATTR_STT_PROVIDER = "platform.stt.provider"
ATTR_STT_AUDIO_BYTES = "platform.stt.audio_bytes"
ATTR_STT_CHUNK_COUNT = "platform.stt.chunk_count"
ATTR_STT_DURATION_MS = "platform.stt.duration_ms"
ATTR_STT_MODEL = "platform.stt.model"
ATTR_STT_MODE = "platform.stt.mode"
ATTR_STT_TEXT_LENGTH = "platform.stt.text_length"

ATTR_TTS_PROVIDER = "platform.tts.provider"
ATTR_TTS_VOICE = "platform.tts.voice"
ATTR_TTS_LANGUAGE = "platform.tts.language"
ATTR_TTS_TEXT_LENGTH = "platform.tts.text_length"
ATTR_TTS_AUDIO_BYTES = "platform.tts.audio_bytes"
ATTR_TTS_DURATION_MS = "platform.tts.duration_ms"
ATTR_TTS_TTFA_MS = "platform.tts.ttfa_ms"

ATTR_FLOW_FIRST_CHUNK_MS = "platform.flow.first_content_chunk_ms"
ATTR_LIVEKIT_OPERATION = "platform.livekit.operation"
ATTR_LIVEKIT_ROOM = "platform.livekit.room_name"
ATTR_LIVEKIT_EGRESS_ID = "platform.livekit.egress_id"
ATTR_CALL_ID = "platform.call.id"
ATTR_CHANNEL_ID = "platform.sync.channel_id"

# CRM
ATTR_CRM_QUERY_MODE = "platform.crm.query_mode"
ATTR_CRM_ENTITY_TYPE = "platform.crm.entity_type"

# Prompt
ATTR_PROMPT_NODE_ID = "platform.prompt.node_id"
ATTR_PROMPT_TEMPLATE_LENGTH = "platform.prompt.template_length"
ATTR_PROMPT_RENDERED_LENGTH = "platform.prompt.rendered_length"
ATTR_PROMPT_VARIABLES_COUNT = "platform.prompt.variables_count"
ATTR_PROMPT_HASH = "platform.prompt.hash"
ATTR_PROMPT_VARIABLES = "platform.prompt.variables"
