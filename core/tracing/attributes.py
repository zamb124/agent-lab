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

# Agent
ATTR_FLOW_ID = "platform.flow_id"
ATTR_FLOW_ENTRY = "platform.flow.entry_node"
ATTR_FLOW_VARIABLES_COUNT = "platform.flow.variables_count"
ATTR_BRANCH_ID = "platform.branch_id"

# Node
ATTR_NODE_ID = "platform.node_id"
ATTR_NODE_TYPE = "platform.node_type"
ATTR_NODE_ITERATION = "platform.node.iteration"

# Agent
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
# OpenRouter BYOK: usage.cost_details.upstream_inference_cost
ATTR_LLM_PROVIDER_UPSTREAM_INFERENCE_COST = "platform.llm.provider_upstream_inference_cost"
ATTR_LLM_INPUT_TOKENS = "platform.llm.input_tokens"
ATTR_LLM_OUTPUT_TOKENS = "platform.llm.output_tokens"
ATTR_LLM_TOTAL_TOKENS = "platform.llm.total_tokens"
ATTR_LLM_DURATION_MS = "platform.llm.duration_ms"
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

# Tool
ATTR_TOOL_NAME = "platform.tool.name"
ATTR_TOOL_CALL_ID = "platform.tool.call_id"
ATTR_TOOL_ARGS = "platform.tool.args"
ATTR_TOOL_RESULT = "platform.tool.result"
ATTR_TOOL_DURATION_MS = "platform.tool.duration_ms"
ATTR_TOOL_IS_AGENT = "platform.tool.is_agent"
ATTR_TOOL_ERROR = "platform.tool.error"

# Interrupt
ATTR_INTERRUPT_QUESTION = "platform.interrupt.question"
ATTR_INTERRUPT_TOOL = "platform.interrupt.tool"
ATTR_INTERRUPT_PATH_DEPTH = "platform.interrupt.path_depth"

# Status
ATTR_STATUS = "platform.status"
ATTR_ERROR_MESSAGE = "platform.error.message"
ATTR_ERROR_TYPE = "platform.error.type"

# Files
ATTR_FILES_COUNT = "platform.files.count"

# State
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

# RAG / embeddings
ATTR_EMBED_MODEL = "platform.embed.model"
ATTR_EMBED_BATCH_SIZE = "platform.embed.batch_size"
ATTR_EMBED_TEXT_COUNT = "platform.embed.text_count"
ATTR_RAG_DOCUMENT_ID = "platform.rag.document_id"
ATTR_RAG_STAGE = "platform.rag.stage"

# Sync / STT / calls
ATTR_SYNC_COMMAND_TYPE = "platform.sync.command_type"
ATTR_STT_PROVIDER = "platform.stt.provider"
ATTR_STT_AUDIO_BYTES = "platform.stt.audio_bytes"
ATTR_STT_CHUNK_COUNT = "platform.stt.chunk_count"
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
