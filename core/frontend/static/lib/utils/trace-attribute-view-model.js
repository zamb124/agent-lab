/**
 * View-model для человекочитаемого просмотра span.attributes.
 * Атрибуты трейсинга часто хранят JSON как строку, поэтому здесь вся
 * нормализация держится отдельно от Lit-компонента.
 */

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
export function isTracePlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {{ ok: true, value: unknown, source: 'native'|'json' }|{ ok: false, value: null, error: string, raw: string }}
 */
export function parseTraceJsonValue(value) {
    if (isTracePlainObject(value) || Array.isArray(value)) {
        return { ok: true, value, source: 'native' };
    }
    if (typeof value !== 'string') {
        return { ok: false, value: null, error: 'not_string', raw: '' };
    }
    const raw = value.trim();
    if (raw.length === 0) {
        return { ok: false, value: null, error: 'empty', raw };
    }
    const first = raw[0];
    if (first !== '{' && first !== '[') {
        return { ok: false, value: null, error: 'not_json', raw };
    }
    try {
        return { ok: true, value: JSON.parse(raw), source: 'json' };
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return { ok: false, value: null, error: message, raw };
    }
}

/**
 * @param {string} ch
 * @returns {string}
 */
function decodeJsonEscape(ch) {
    switch (ch) {
        case '"': return '"';
        case '\\': return '\\';
        case '/': return '/';
        case 'b': return '\b';
        case 'f': return '\f';
        case 'n': return '\n';
        case 'r': return '\r';
        case 't': return '\t';
        default: return ch;
    }
}

/**
 * @param {string} raw
 * @param {number} quoteIndex
 * @returns {{ text: string, endIndex: number, closed: boolean }}
 */
function readJsonStringLoose(raw, quoteIndex) {
    if (raw[quoteIndex] !== '"') {
        throw new Error('readJsonStringLoose: quoteIndex must point to "');
    }
    let out = '';
    let i = quoteIndex + 1;
    while (i < raw.length) {
        const ch = raw[i];
        if (ch === '"') {
            return { text: out, endIndex: i, closed: true };
        }
        if (ch === '\\') {
            const next = raw[i + 1];
            if (next === undefined) {
                return { text: out, endIndex: i, closed: false };
            }
            if (next === 'u') {
                const hex = raw.slice(i + 2, i + 6);
                if (/^[0-9a-fA-F]{4}$/.test(hex)) {
                    out += String.fromCharCode(parseInt(hex, 16));
                    i += 6;
                    continue;
                }
            }
            out += decodeJsonEscape(next);
            i += 2;
            continue;
        }
        out += ch;
        i += 1;
    }
    return { text: out, endIndex: raw.length, closed: false };
}

/**
 * @param {string} raw
 * @param {string} propertyName
 * @returns {{ text: string, endIndex: number, closed: boolean }|null}
 */
function readJsonStringPropertyLoose(raw, propertyName) {
    const escapedName = propertyName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`"${escapedName}"\\s*:\\s*"`);
    const match = re.exec(raw);
    if (!match) {
        return null;
    }
    return readJsonStringLoose(raw, match.index + match[0].length - 1);
}

/**
 * @param {string} raw
 * @returns {string}
 */
function decodeCommonJsonEscapes(raw) {
    let out = '';
    for (let i = 0; i < raw.length; i += 1) {
        const ch = raw[i];
        if (ch !== '\\') {
            out += ch;
            continue;
        }
        const next = raw[i + 1];
        if (next === undefined) {
            out += ch;
            continue;
        }
        if (next === 'u') {
            const hex = raw.slice(i + 2, i + 6);
            if (/^[0-9a-fA-F]{4}$/.test(hex)) {
                out += String.fromCharCode(parseInt(hex, 16));
                i += 5;
                continue;
            }
        }
        out += decodeJsonEscape(next);
        i += 1;
    }
    return out;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function prettyTraceJsonText(value) {
    if (isTracePlainObject(value) || Array.isArray(value)) {
        return JSON.stringify(value, null, 2);
    }
    const raw = traceScalarText(value);
    if (raw.length === 0) {
        return '';
    }
    const recovered = recoverLlmResponseEnvelope(raw);
    if (recovered !== null) {
        return JSON.stringify(recovered.envelope, null, 2);
    }
    const parsed = parseTraceJsonValue(raw);
    if (parsed.ok) {
        return JSON.stringify(parsed.value, null, 2);
    }
    return decodeCommonJsonEscapes(raw);
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function traceScalarText(value) {
    if (typeof value === 'string') {
        return value;
    }
    if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
        return String(value);
    }
    if (value === null || value === undefined) {
        return '';
    }
    return JSON.stringify(value, null, 2);
}

/**
 * @param {Record<string, unknown>} attrs
 * @param {string} key
 * @returns {unknown}
 */
function attr(attrs, key) {
    return Object.prototype.hasOwnProperty.call(attrs, key) ? attrs[key] : undefined;
}

/**
 * @param {Record<string, unknown>} span
 * @param {Record<string, unknown>} attrs
 * @param {string} spanKey
 * @param {string} attrKey
 * @returns {unknown}
 */
function spanOrAttr(span, attrs, spanKey, attrKey) {
    const direct = span[spanKey];
    if (direct !== null && direct !== undefined && direct !== '') {
        return direct;
    }
    return attr(attrs, attrKey);
}

/**
 * @param {unknown[]} out
 * @param {string} key
 * @param {unknown} value
 */
function pushField(out, key, value) {
    const text = traceScalarText(value);
    if (text.length > 0) {
        out.push({ key, value: text });
    }
}

/**
 * @param {unknown} part
 * @returns {string}
 */
function messagePartText(part) {
    if (typeof part === 'string') {
        return part;
    }
    if (!isTracePlainObject(part)) {
        return traceScalarText(part);
    }
    const text = part.text;
    if (typeof text === 'string') {
        return text;
    }
    const content = part.content;
    if (typeof content === 'string') {
        return content;
    }
    return traceScalarText(part);
}

/**
 * @param {unknown} message
 * @returns {string}
 */
function messageText(message) {
    if (!isTracePlainObject(message)) {
        return traceScalarText(message);
    }
    const content = message.content;
    if (typeof content === 'string') {
        return content;
    }
    if (Array.isArray(content)) {
        return content.map((part) => messagePartText(part)).filter((text) => text.length > 0).join('\n');
    }
    const parts = message.parts;
    if (Array.isArray(parts)) {
        return parts.map((part) => messagePartText(part)).filter((text) => text.length > 0).join('\n');
    }
    return traceScalarText(message);
}

/**
 * @param {unknown} message
 * @param {number} index
 * @returns {{ index: number, role: string, id: string, text: string, system: boolean }}
 */
function normalizeMessage(message, index) {
    if (!isTracePlainObject(message)) {
        return {
            index,
            role: '',
            id: '',
            text: messageText(message),
            system: false,
        };
    }
    const metadata = isTracePlainObject(message.metadata) ? message.metadata : {};
    const role = typeof message.role === 'string' ? message.role : '';
    const id = typeof message.messageId === 'string' ? message.messageId : '';
    return {
        index,
        role,
        id,
        text: messageText(message),
        system: metadata.system === true,
    };
}

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
function objectOrEmpty(value) {
    return isTracePlainObject(value) ? value : {};
}

/**
 * @param {unknown} span
 * @returns {Record<string, unknown>}
 */
function normalizeSpan(span) {
    return isTracePlainObject(span) ? span : {};
}

/**
 * @param {Record<string, unknown>} attrs
 * @returns {ReturnType<typeof parseTraceJsonValue>|null}
 */
function parsedAttr(attrs, key) {
    const value = attr(attrs, key);
    if (value === null || value === undefined || value === '') {
        return null;
    }
    return parseTraceJsonValue(value);
}

/**
 * @param {string} raw
 * @returns {{ envelope: Record<string, unknown>, content: unknown, toolCalls: unknown[], contentClosed: boolean }|null}
 */
function recoverLlmResponseEnvelope(raw) {
    const content = readJsonStringPropertyLoose(raw, 'content');
    if (content === null) {
        return null;
    }
    const contentParsed = parseTraceJsonValue(content.text);
    const contentValue = contentParsed.ok ? contentParsed.value : content.text;
    let toolCalls = [];
    const toolCallsIdx = raw.indexOf('"tool_calls"', content.endIndex);
    if (toolCallsIdx >= 0) {
        const arrayStart = raw.indexOf('[', toolCallsIdx);
        const arrayEnd = raw.indexOf(']', arrayStart);
        if (arrayStart >= 0 && arrayEnd > arrayStart) {
            const parsedToolCalls = parseTraceJsonValue(raw.slice(arrayStart, arrayEnd + 1));
            if (parsedToolCalls.ok && Array.isArray(parsedToolCalls.value)) {
                toolCalls = parsedToolCalls.value;
            }
        }
    }
    return {
        envelope: {
            content: contentValue,
            tool_calls: toolCalls,
        },
        content: contentValue,
        toolCalls,
        contentClosed: content.closed,
    };
}

/**
 * @param {Record<string, unknown>} attrs
 */
export function buildLlmRequestView(attrs) {
    const rawValue = attr(attrs, 'platform.llm.request');
    const parsed = parsedAttr(attrs, 'platform.llm.request');
    if (parsed === null) {
        return null;
    }
    const request = parsed.ok && isTracePlainObject(parsed.value) ? parsed.value : {};
    const rawMessages = Array.isArray(request.messages) ? request.messages : [];
    const rawTools = Array.isArray(request.tools) ? request.tools : [];
    const responseFormat = request.response_format;
    return {
        parsed,
        raw: traceScalarText(rawValue),
        prettyRaw: prettyTraceJsonText(rawValue),
        messages: rawMessages.map((message, index) => normalizeMessage(message, index)),
        tools: rawTools,
        responseFormat,
    };
}

/**
 * @param {unknown} content
 */
export function buildStructuredContentView(content) {
    const parsed = parseTraceJsonValue(content);
    if (!parsed.ok || !isTracePlainObject(parsed.value)) {
        return {
            parsed,
            summary: '',
            entities: [],
            highlights: [],
            keyEvents: [],
            statistics: {},
        };
    }
    const data = parsed.value;
    const entities = Array.isArray(data.entities) ? data.entities.map((v) => traceScalarText(v)).filter((v) => v.length > 0) : [];
    const highlights = Array.isArray(data.highlights) ? data.highlights.map((v) => traceScalarText(v)).filter((v) => v.length > 0) : [];
    const keyEvents = Array.isArray(data.key_events) ? data.key_events.map((v) => traceScalarText(v)).filter((v) => v.length > 0) : [];
    const statistics = isTracePlainObject(data.statistics) ? data.statistics : {};
    return {
        parsed,
        summary: typeof data.summary === 'string' ? data.summary : '',
        entities,
        highlights,
        keyEvents,
        statistics,
    };
}

/**
 * @param {Record<string, unknown>} attrs
 */
export function buildLlmResponseView(attrs) {
    const rawValue = attr(attrs, 'platform.llm.response');
    const parsed = parsedAttr(attrs, 'platform.llm.response');
    if (parsed === null) {
        return null;
    }
    const raw = traceScalarText(rawValue);
    const recovered = parsed.ok ? null : recoverLlmResponseEnvelope(raw);
    const response = parsed.ok && isTracePlainObject(parsed.value) ? parsed.value : {};
    const content = recovered !== null ? recovered.content : response.content;
    const toolCalls = recovered !== null
        ? recovered.toolCalls
        : (Array.isArray(response.tool_calls) ? response.tool_calls : []);
    return {
        parsed,
        recovered: recovered !== null,
        raw,
        prettyRaw: prettyTraceJsonText(rawValue),
        content,
        contentText: traceScalarText(content),
        structuredContent: buildStructuredContentView(content),
        toolCalls,
    };
}

/**
 * @param {Record<string, unknown>} attrs
 */
function buildToolView(attrs) {
    const fields = [];
    pushField(fields, 'tool_name', attr(attrs, 'platform.tool.name'));
    pushField(fields, 'tool_call_id', attr(attrs, 'platform.tool.call_id'));
    pushField(fields, 'tool_duration', attr(attrs, 'platform.tool.duration_ms'));
    pushField(fields, 'tool_is_agent', attr(attrs, 'platform.tool.is_agent'));
    pushField(fields, 'mcp_tool_name', attr(attrs, 'platform.mcp.tool_name'));
    pushField(fields, 'mcp_response_bytes', attr(attrs, 'platform.mcp.response_bytes'));
    const args = attr(attrs, 'platform.tool.args');
    const result = attr(attrs, 'platform.tool.result');
    const mcpPreview = attr(attrs, 'platform.mcp.response_preview');
    const hasToolData = fields.length > 0 || args !== undefined || result !== undefined || mcpPreview !== undefined;
    if (!hasToolData) {
        return null;
    }
    return {
        fields,
        args: {
            raw: traceScalarText(args),
            parsed: parseTraceJsonValue(args),
        },
        result: {
            raw: traceScalarText(result),
            parsed: parseTraceJsonValue(result),
        },
        mcpPreview: traceScalarText(mcpPreview),
    };
}

/**
 * @param {Record<string, unknown>} attrs
 */
function buildPromptView(attrs) {
    const fields = [];
    pushField(fields, 'prompt_node', attr(attrs, 'platform.prompt.node_id'));
    pushField(fields, 'prompt_template_length', attr(attrs, 'platform.prompt.template_length'));
    pushField(fields, 'prompt_rendered_length', attr(attrs, 'platform.prompt.rendered_length'));
    pushField(fields, 'prompt_variables_count', attr(attrs, 'platform.prompt.variables_count'));
    pushField(fields, 'prompt_hash', attr(attrs, 'platform.prompt.hash'));
    const variables = attr(attrs, 'platform.prompt.variables');
    if (fields.length === 0 && variables === undefined) {
        return null;
    }
    return {
        fields,
        variables: {
            raw: traceScalarText(variables),
            parsed: parseTraceJsonValue(variables),
        },
    };
}

/**
 * @param {Record<string, unknown>} attrs
 */
function buildStateView(attrs) {
    const snapshot = attr(attrs, 'platform.state.snapshot');
    if (snapshot === undefined) {
        return null;
    }
    return {
        raw: traceScalarText(snapshot),
        parsed: parseTraceJsonValue(snapshot),
    };
}

/**
 * @param {Record<string, unknown>} attrs
 * @param {Record<string, unknown>} span
 */
function buildErrorView(attrs, span) {
    const fields = [];
    const status = typeof span.status === 'string' ? span.status.toUpperCase() : '';
    if (status === 'ERROR') {
        pushField(fields, 'status', span.status);
    }
    pushField(fields, 'status_message', span.status_message);
    pushField(fields, 'platform_status', attr(attrs, 'platform.status'));
    pushField(fields, 'error_type', attr(attrs, 'platform.error.type'));
    pushField(fields, 'error_message', attr(attrs, 'platform.error.message'));
    pushField(fields, 'tool_error', attr(attrs, 'platform.tool.error'));
    return fields.length > 0 ? { fields } : null;
}

/**
 * @param {Record<string, unknown>} attrs
 */
function buildInterruptView(attrs) {
    const fields = [];
    pushField(fields, 'interrupt_question', attr(attrs, 'platform.interrupt.question'));
    pushField(fields, 'interrupt_tool', attr(attrs, 'platform.interrupt.tool'));
    pushField(fields, 'interrupt_path_depth', attr(attrs, 'platform.interrupt.path_depth'));
    return fields.length > 0 ? { fields } : null;
}

/**
 * @param {Record<string, unknown>} span
 * @param {Record<string, unknown>} attrs
 */
function buildQuickFacts(span, attrs) {
    const facts = [];
    pushField(facts, 'operation', span.operation_name);
    pushField(facts, 'span_id', span.span_id);
    pushField(facts, 'trace_id', span.trace_id);
    pushField(facts, 'service', span.service_name);
    pushField(facts, 'status', span.status);
    pushField(facts, 'user', spanOrAttr(span, attrs, 'user_name', 'platform.user.name'));
    pushField(facts, 'user_id', spanOrAttr(span, attrs, 'user_id', 'platform.user.id'));
    pushField(facts, 'flow', spanOrAttr(span, attrs, 'flow_id', 'platform.flow_id'));
    pushField(facts, 'branch', spanOrAttr(span, attrs, 'branch_id', 'platform.branch_id'));
    pushField(facts, 'node', spanOrAttr(span, attrs, 'node_id', 'platform.node_id'));
    pushField(facts, 'task', spanOrAttr(span, attrs, 'task_id', 'platform.task_id'));
    pushField(facts, 'context', spanOrAttr(span, attrs, 'context_id', 'platform.context_id'));
    pushField(facts, 'channel', spanOrAttr(span, attrs, 'channel', 'platform.channel'));
    pushField(facts, 'model', attr(attrs, 'platform.llm.model'));
    pushField(facts, 'provider', attr(attrs, 'platform.llm.provider'));
    pushField(facts, 'tool', attr(attrs, 'platform.tool.name'));
    return facts;
}

/**
 * @param {Record<string, unknown>} span
 * @param {Record<string, unknown>} attrs
 */
function buildMetrics(span, attrs) {
    const metrics = [];
    pushField(metrics, 'duration', span.duration_ms);
    pushField(metrics, 'messages', attr(attrs, 'llm.messages_count'));
    pushField(metrics, 'tools', attr(attrs, 'llm.tools_count'));
    pushField(metrics, 'input_tokens', attr(attrs, 'platform.llm.input_tokens'));
    pushField(metrics, 'output_tokens', attr(attrs, 'platform.llm.output_tokens'));
    pushField(metrics, 'total_tokens', attr(attrs, 'platform.llm.total_tokens'));
    pushField(metrics, 'llm_duration', attr(attrs, 'platform.llm.duration_ms'));
    pushField(metrics, 'provider_cost', attr(attrs, 'platform.llm.provider_reported_cost'));
    pushField(metrics, 'upstream_cost', attr(attrs, 'platform.llm.provider_upstream_inference_cost'));
    pushField(metrics, 'billing_quantity', attr(attrs, 'platform.billing.quantity'));
    pushField(metrics, 'prompt_template_length', attr(attrs, 'platform.prompt.template_length'));
    pushField(metrics, 'prompt_rendered_length', attr(attrs, 'platform.prompt.rendered_length'));
    pushField(metrics, 'embed_text_count', attr(attrs, 'platform.embed.text_count'));
    pushField(metrics, 'embed_batch_size', attr(attrs, 'platform.embed.batch_size'));
    return metrics;
}

/**
 * @param {unknown} span
 */
export function buildSpanAttributeViewModel(span) {
    const normalizedSpan = normalizeSpan(span);
    const attrs = objectOrEmpty(normalizedSpan.attributes);
    return {
        span: normalizedSpan,
        attrs,
        quickFacts: buildQuickFacts(normalizedSpan, attrs),
        metrics: buildMetrics(normalizedSpan, attrs),
        llmRequest: buildLlmRequestView(attrs),
        llmResponse: buildLlmResponseView(attrs),
        tool: buildToolView(attrs),
        prompt: buildPromptView(attrs),
        state: buildStateView(attrs),
        error: buildErrorView(attrs, normalizedSpan),
        interrupt: buildInterruptView(attrs),
    };
}
