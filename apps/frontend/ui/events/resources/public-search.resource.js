/**
 * Публичный запуск Humanitec Search.
 *
 * Исполнение остаётся в Flows A2A/SSE:
 *   1. frontend выдаёт short-lived embed-session token;
 *   2. flow public_search стримит артефакты `ui_event`;
 *   3. эта фабрика сводит события в SERP-state для UI.
 */
import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest, HttpError } from '@platform/lib/events/http.js';
import { streamEmbedA2A } from '@platform/lib/embed-chat/embed-a2a-stream.js';
import { mapA2aResultToChatRuntimeEvents } from '@platform/lib/flows-chat/a2a-chat-runtime.js';

const SEARCH_RUN_MODES = Object.freeze(new Set(['quick', 'deep', 'research']));
const PUBLIC_SEARCH_SESSION_MODES = Object.freeze(new Set(['quick', 'deep', 'research', 'source']));
const PUBLIC_SEARCH_ERROR_KINDS = Object.freeze(new Set([
    'search_timeout',
    'search_service_unavailable',
    'search_stream_incomplete',
    'search_quota_exhausted',
    'search_failed',
]));
const PUBLIC_SEARCH_STREAM_EVENT = 'frontend/public_search_run/stream_event';
const PUBLIC_SEARCH_SOURCE_STREAM_EVENT = 'frontend/public_search_source_describe/stream_event';
const RUN_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

let activeSearchRun = null;

/** @type {Map<string, ReturnType<typeof _normalizeSession>>} */
const publicSearchSessionByMode = new Map();

const PUBLIC_SEARCH_SESSION_EXPIRY_SKEW_MS = 30_000;

function _emptyStream() {
    return {
        kind: 'public_search_stream',
        version: 1,
        run_id: '',
        query: '',
        mode: 'quick',
        phase: 'idle',
        activity: '',
        task_id: '',
        context_id: '',
        task_primed: false,
        results: [],
        providers: {},
        suggestions: [],
        followups: [],
        result_insights: [],
        answer: '',
        markdown_sources: '',
        completed: false,
        serp_cache_key: '',
        total_count: 0,
        has_more: false,
        results_offset: 0,
        page_limit: 10,
    };
}

function _emptySourceDescribeStream() {
    return {
        kind: 'public_search_source_stream',
        version: 1,
        run_id: '',
        query: '',
        title: '',
        url: '',
        display_url: '',
        provider: '',
        rank: 0,
        phase: 'idle',
        activity: '',
        task_id: '',
        context_id: '',
        task_primed: false,
        answer: '',
        completed: false,
    };
}

function _requireObject(value, label) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`${label} must be an object`);
    }
    return value;
}

function _requireArray(value, label) {
    if (!Array.isArray(value)) {
        throw new Error(`${label} must be an array`);
    }
    return value;
}

function _requireString(value, label) {
    if (typeof value !== 'string') {
        throw new Error(`${label} must be a string`);
    }
    return value;
}

function _requireNonEmptyString(value, label) {
    const text = _requireString(value, label).trim();
    if (text === '') {
        throw new Error(`${label} must be non-empty`);
    }
    return text;
}

function _requireNumber(value, label) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`${label} must be a finite number`);
    }
    return value;
}

function _requireBoolean(value, label) {
    if (value !== true && value !== false) {
        throw new Error(`${label} must be boolean`);
    }
    return value;
}

function _requireNullableString(value, label) {
    if (value === null) {
        return null;
    }
    return _requireString(value, label);
}

function _requireSearchRunMode(value, label) {
    const mode = _requireNonEmptyString(value, label);
    if (!SEARCH_RUN_MODES.has(mode)) {
        throw new Error(`${label} is invalid`);
    }
    return mode;
}

function _requirePublicSearchSessionMode(value, label) {
    const mode = _requireNonEmptyString(value, label);
    if (!PUBLIC_SEARCH_SESSION_MODES.has(mode)) {
        throw new Error(`${label} is invalid`);
    }
    return mode;
}

function _requirePublicSearchErrorKind(value, label) {
    const kind = _requireNonEmptyString(value, label);
    if (!PUBLIC_SEARCH_ERROR_KINDS.has(kind)) {
        throw new Error(`${label} is invalid`);
    }
    return kind;
}

function _normalizeFilePart(value, index) {
    const item = _requireObject(value, `files[${index}]`);
    return {
        name: _requireNonEmptyString(item.name, `files[${index}].name`),
        mimeType: _requireNonEmptyString(item.mimeType, `files[${index}].mimeType`),
        data: _requireNonEmptyString(item.data, `files[${index}].data`),
    };
}

function _normalizeFileParts(value) {
    return _requireArray(value, 'files').map((item, index) => _normalizeFilePart(item, index));
}

function _normalizeResult(value, index) {
    const item = _requireObject(value, `results[${index}]`);
    return {
        title: _requireNonEmptyString(item.title, `results[${index}].title`),
        url: _requireNonEmptyString(item.url, `results[${index}].url`),
        snippet: _requireString(item.snippet, `results[${index}].snippet`),
        display_url: _requireString(item.display_url, `results[${index}].display_url`),
        provider: _requireNonEmptyString(item.provider, `results[${index}].provider`),
        provider_rank: _requireNumber(item.provider_rank, `results[${index}].provider_rank`),
        rank: _requireNumber(item.rank, `results[${index}].rank`),
        score: _requireNumber(item.score, `results[${index}].score`),
        published_at: _requireNullableString(item.published_at, `results[${index}].published_at`),
        source_type: _requireNonEmptyString(item.source_type, `results[${index}].source_type`),
        site_name: _requireString(item.site_name, `results[${index}].site_name`),
        favicon_url: _requireString(item.favicon_url, `results[${index}].favicon_url`),
        preview_image_url: _requireString(item.preview_image_url, `results[${index}].preview_image_url`),
    };
}

function _normalizeResults(value) {
    return _requireArray(value, 'results').map((item, index) => _normalizeResult(item, index));
}

function _normalizeProviders(value) {
    const providers = _requireObject(value, 'providers');
    const out = {};
    for (const [name, raw] of Object.entries(providers)) {
        const status = _requireObject(raw, `providers.${name}`);
        out[name] = {
            ok: _requireBoolean(status.ok, `providers.${name}.ok`),
            latency_ms: _requireNumber(status.latency_ms, `providers.${name}.latency_ms`),
            results_count: _requireNumber(status.results_count, `providers.${name}.results_count`),
            error: _requireNullableString(status.error, `providers.${name}.error`),
            selected: _requireBoolean(status.selected, `providers.${name}.selected`),
            skipped: _requireBoolean(status.skipped, `providers.${name}.skipped`),
            skip_reason: _requireNullableString(status.skip_reason, `providers.${name}.skip_reason`),
        };
    }
    return out;
}

function _normalizeSuggestion(value, index, label) {
    const item = _requireObject(value, `${label}[${index}]`);
    return {
        text: _requireNonEmptyString(item.text, `${label}[${index}].text`),
        kind: _requireNonEmptyString(item.kind, `${label}[${index}].kind`),
        score: _requireNumber(item.score, `${label}[${index}].score`),
    };
}

function _normalizeSuggestions(value, label) {
    return _requireArray(value, label).map((item, index) => _normalizeSuggestion(item, index, label));
}

function _normalizeStringArray(value, label) {
    return _requireArray(value, label).map((item, index) => _requireString(item, `${label}[${index}]`));
}

function _normalizeInsight(value, index) {
    const item = _requireObject(value, `result_insights[${index}]`);
    return {
        title: _requireNonEmptyString(item.title, `result_insights[${index}].title`),
        url: _requireNonEmptyString(item.url, `result_insights[${index}].url`),
        provider: _requireNonEmptyString(item.provider, `result_insights[${index}].provider`),
        rank: _requireNumber(item.rank, `result_insights[${index}].rank`),
        confidence: _requireNumber(item.confidence, `result_insights[${index}].confidence`),
        matched_terms: _normalizeStringArray(item.matched_terms, `result_insights[${index}].matched_terms`),
        relevance_hint: _requireNonEmptyString(item.relevance_hint, `result_insights[${index}].relevance_hint`),
        actions: _normalizeStringArray(item.actions, `result_insights[${index}].actions`),
    };
}

function _normalizeInsights(value) {
    return _requireArray(value, 'result_insights').map((item, index) => _normalizeInsight(item, index));
}

function _normalizeRunPayload(payload) {
    const body = _requireObject(payload, 'frontend/public_search_run payload');
    const runId = _requireNonEmptyString(body.run_id, 'run_id');
    if (!RUN_ID_PATTERN.test(runId)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    const query = _requireNonEmptyString(body.query, 'query');
    const mode = _requireSearchRunMode(body.mode, 'mode');
    const files = Object.prototype.hasOwnProperty.call(body, 'files')
        ? _normalizeFileParts(body.files)
        : [];
    return { run_id: runId, query, mode, files };
}

function _normalizeFailedRunPayload(event) {
    const payload = _requireObject(event.payload, 'failed payload');
    const body = _requireObject(payload.body, 'failed payload body');
    return {
        run_id: _requireNonEmptyString(body.run_id, 'failed payload body.run_id'),
        error_kind: _requirePublicSearchErrorKind(body.error_kind, 'failed payload body.error_kind'),
        detail: _requireString(body.detail, 'failed payload body.detail'),
    };
}

function _normalizeSourceDescribePayload(payload) {
    const body = _requireObject(payload, 'frontend/public_search_source_describe payload');
    const runId = _requireNonEmptyString(body.run_id, 'run_id');
    if (!RUN_ID_PATTERN.test(runId)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    const query = _requireNonEmptyString(body.query, 'query');
    const source = _normalizeResult(body.source, 0);
    return { run_id: runId, query, mode: 'source', source };
}

function _contextIdFromRunId(runId) {
    const value = _requireNonEmptyString(runId, 'run_id');
    if (!RUN_ID_PATTERN.test(value)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    return value;
}

function _streamFromRunPayload(payload) {
    return {
        ..._emptyStream(),
        run_id: payload.run_id,
        query: payload.query,
        mode: payload.mode,
        context_id: _contextIdFromRunId(payload.run_id),
        phase: 'starting',
    };
}

function _sourceStreamFromPayload(payload) {
    return {
        ..._emptySourceDescribeStream(),
        run_id: payload.run_id,
        query: payload.query,
        title: payload.source.title,
        url: payload.source.url,
        display_url: payload.source.display_url,
        provider: payload.source.provider,
        rank: payload.source.rank,
        context_id: _contextIdFromRunId(payload.run_id),
        phase: 'starting',
    };
}

function _normalizeStreamPayload(value) {
    const stream = _requireObject(value, 'stream');
    return {
        kind: 'public_search_stream',
        version: 1,
        run_id: _requireNonEmptyString(stream.run_id, 'stream.run_id'),
        query: _requireNonEmptyString(stream.query, 'stream.query'),
        mode: _requireSearchRunMode(stream.mode, 'stream.mode'),
        phase: _requireNonEmptyString(stream.phase, 'stream.phase'),
        activity: _requireString(stream.activity, 'stream.activity'),
        task_id: _requireString(stream.task_id, 'stream.task_id'),
        context_id: _requireString(stream.context_id, 'stream.context_id'),
        task_primed: _requireBoolean(stream.task_primed, 'stream.task_primed'),
        results: _normalizeResults(stream.results),
        providers: _normalizeProviders(stream.providers),
        suggestions: _normalizeSuggestions(stream.suggestions, 'suggestions'),
        followups: _normalizeSuggestions(stream.followups, 'followups'),
        result_insights: _normalizeInsights(stream.result_insights),
        answer: _requireString(stream.answer, 'stream.answer'),
        markdown_sources: _requireString(stream.markdown_sources, 'stream.markdown_sources'),
        completed: _requireBoolean(stream.completed, 'stream.completed'),
        serp_cache_key: _requireString(stream.serp_cache_key, 'stream.serp_cache_key'),
        total_count: _requireNumber(stream.total_count, 'stream.total_count'),
        has_more: _requireBoolean(stream.has_more, 'stream.has_more'),
        results_offset: _requireNumber(stream.results_offset, 'stream.results_offset'),
        page_limit: _requireNumber(stream.page_limit, 'stream.page_limit'),
    };
}

function _normalizeSourceDescribeStream(value) {
    const stream = _requireObject(value, 'source_stream');
    return {
        kind: 'public_search_source_stream',
        version: 1,
        run_id: _requireNonEmptyString(stream.run_id, 'source_stream.run_id'),
        query: _requireNonEmptyString(stream.query, 'source_stream.query'),
        title: _requireNonEmptyString(stream.title, 'source_stream.title'),
        url: _requireNonEmptyString(stream.url, 'source_stream.url'),
        display_url: _requireString(stream.display_url, 'source_stream.display_url'),
        provider: _requireNonEmptyString(stream.provider, 'source_stream.provider'),
        rank: _requireNumber(stream.rank, 'source_stream.rank'),
        phase: _requireNonEmptyString(stream.phase, 'source_stream.phase'),
        activity: _requireString(stream.activity, 'source_stream.activity'),
        task_id: _requireString(stream.task_id, 'source_stream.task_id'),
        context_id: _requireString(stream.context_id, 'source_stream.context_id'),
        task_primed: _requireBoolean(stream.task_primed, 'source_stream.task_primed'),
        answer: _requireString(stream.answer, 'source_stream.answer'),
        completed: _requireBoolean(stream.completed, 'source_stream.completed'),
    };
}

function _normalizeSession(value) {
    const session = _requireObject(value, 'public search session');
    const tokenType = _requireNonEmptyString(session.token_type, 'session.token_type');
    if (tokenType !== 'Bearer') {
        throw new Error('session.token_type must be Bearer');
    }
    return {
        token: _requireNonEmptyString(session.token, 'session.token'),
        token_type: tokenType,
        expires_at: _requireNonEmptyString(session.expires_at, 'session.expires_at'),
        embed_id: _requireNonEmptyString(session.embed_id, 'session.embed_id'),
        flow_id: _requireNonEmptyString(session.flow_id, 'session.flow_id'),
        branch_id: _requirePublicSearchSessionMode(session.branch_id, 'session.branch_id'),
    };
}

function _windowOrigin() {
    if (typeof window === 'undefined' || !window.location || typeof window.location.origin !== 'string') {
        throw new Error('window.location.origin required for public search');
    }
    return window.location.origin;
}

function _flowsBaseUrl() {
    return `${_windowOrigin()}/flows`;
}

function _publishStream(ctx, eventId, stream) {
    ctx.dispatch(
        PUBLIC_SEARCH_STREAM_EVENT,
        { stream: _normalizeStreamPayload(stream) },
        { causation_id: eventId, source: 'http' },
    );
}

function _publishSourceDescribeStream(ctx, eventId, sourceStream) {
    ctx.dispatch(
        PUBLIC_SEARCH_SOURCE_STREAM_EVENT,
        { source_stream: _normalizeSourceDescribeStream(sourceStream) },
        { causation_id: eventId, source: 'http' },
    );
}

function _replaceActiveSearchRun(runId, controller) {
    const id = _requireNonEmptyString(runId, 'active search run_id');
    if (!(controller instanceof AbortController)) {
        throw new Error('active search controller must be AbortController');
    }
    if (activeSearchRun !== null) {
        activeSearchRun.controller.abort();
    }
    activeSearchRun = { run_id: id, controller };
}

function _clearActiveSearchRun(runId, controller) {
    const id = _requireNonEmptyString(runId, 'active search run_id');
    if (!(controller instanceof AbortController)) {
        throw new Error('active search controller must be AbortController');
    }
    if (
        activeSearchRun !== null
        && activeSearchRun.run_id === id
        && activeSearchRun.controller === controller
    ) {
        activeSearchRun = null;
    }
}

function _applySearchUiEvent(stream, event) {
    const eventType = _requireNonEmptyString(event.type, 'ui_event.type');
    if (eventType.startsWith('files.')) {
        return;
    }
    const payload = _requireObject(event.payload, 'ui_event.payload');
    if (eventType === 'search/serp/results_ready') {
        stream.phase = 'results';
        stream.results = _normalizeResults(payload.results);
        stream.providers = _normalizeProviders(payload.providers);
        stream.total_count = _requireNumber(payload.total_count, 'results_ready.total_count');
        stream.has_more = _requireBoolean(payload.has_more, 'results_ready.has_more');
        stream.results_offset = stream.results.length;
        if (Object.prototype.hasOwnProperty.call(payload, 'serp_cache_key')) {
            const cacheKey = payload.serp_cache_key;
            if (cacheKey === null) {
                stream.serp_cache_key = '';
            } else {
                stream.serp_cache_key = _requireNonEmptyString(cacheKey, 'results_ready.serp_cache_key');
            }
        }
        if (Object.prototype.hasOwnProperty.call(payload, 'limit')) {
            stream.page_limit = _requireNumber(payload.limit, 'results_ready.limit');
        }
        return;
    }
    if (eventType === 'search/serp/suggestions_ready') {
        stream.phase = 'suggestions';
        stream.suggestions = _normalizeSuggestions(payload.suggestions, 'suggestions');
        stream.followups = _normalizeSuggestions(payload.followups, 'followups');
        return;
    }
    if (eventType === 'search/serp/insights_ready') {
        stream.phase = 'insights';
        stream.result_insights = _normalizeInsights(payload.result_insights);
        return;
    }
    if (eventType === 'search/serp/completed') {
        stream.phase = 'completed';
        stream.mode = _requireSearchRunMode(payload.mode, 'completed.mode');
        stream.query = _requireNonEmptyString(payload.query, 'completed.query');
        stream.answer = _requireNonEmptyString(payload.answer, 'completed.answer');
        stream.markdown_sources = _requireNonEmptyString(payload.markdown_sources, 'completed.markdown_sources');
        stream.results = _normalizeResults(payload.results);
        stream.providers = _normalizeProviders(payload.providers);
        stream.suggestions = _normalizeSuggestions(payload.suggestions, 'suggestions');
        stream.followups = _normalizeSuggestions(payload.followups, 'followups');
        stream.result_insights = _normalizeInsights(payload.result_insights);
        stream.completed = true;
        return;
    }
    throw new Error(`Unsupported public search ui_event: ${eventType}`);
}

function _applyRuntimeEvents(stream, events) {
    for (const runtimeEvent of events) {
        if (!runtimeEvent || typeof runtimeEvent !== 'object') {
            throw new Error('A2A runtime event must be object');
        }
        if (runtimeEvent.type === 'task_started') {
            const payload = _requireObject(runtimeEvent.payload, 'task_started.payload');
            stream.task_id = _requireNonEmptyString(payload.task_id, 'task_started.task_id');
            stream.context_id = _requireNonEmptyString(payload.context_id, 'task_started.context_id');
            stream.task_primed = true;
            stream.phase = stream.phase === 'starting' ? 'searching' : stream.phase;
            continue;
        }
        if (runtimeEvent.type === 'activity') {
            const payload = _requireObject(runtimeEvent.payload, 'activity.payload');
            stream.activity = _requireString(payload.text, 'activity.text');
            continue;
        }
        if (runtimeEvent.type === 'content_chunk') {
            const payload = _requireObject(runtimeEvent.payload, 'content_chunk.payload');
            stream.answer = `${stream.answer}${_requireString(payload.text, 'content_chunk.text')}`;
            stream.phase = stream.phase === 'insights' ? 'answering' : stream.phase;
            continue;
        }
        if (runtimeEvent.type === 'ui_event') {
            const payload = _requireObject(runtimeEvent.payload, 'ui_event.payload');
            const uiEvent = _requireObject(payload.event, 'ui_event.payload.event');
            _applySearchUiEvent(stream, uiEvent);
            continue;
        }
        if (runtimeEvent.type === 'files_event') {
            continue;
        }
        if (runtimeEvent.type === 'failed') {
            const payload = _requireObject(runtimeEvent.payload, 'failed.payload');
            throw new Error(_requireNonEmptyString(payload.error, 'failed.error'));
        }
    }
}

function _applySourceDescribeRuntimeEvents(stream, events) {
    for (const runtimeEvent of events) {
        if (!runtimeEvent || typeof runtimeEvent !== 'object') {
            throw new Error('A2A runtime event must be object');
        }
        if (runtimeEvent.type === 'task_started') {
            const payload = _requireObject(runtimeEvent.payload, 'task_started.payload');
            stream.task_id = _requireNonEmptyString(payload.task_id, 'task_started.task_id');
            stream.context_id = _requireNonEmptyString(payload.context_id, 'task_started.context_id');
            stream.task_primed = true;
            stream.phase = stream.phase === 'starting' ? 'reading' : stream.phase;
            continue;
        }
        if (runtimeEvent.type === 'activity') {
            const payload = _requireObject(runtimeEvent.payload, 'activity.payload');
            stream.activity = _requireString(payload.text, 'activity.text');
            continue;
        }
        if (runtimeEvent.type === 'content_chunk') {
            const payload = _requireObject(runtimeEvent.payload, 'content_chunk.payload');
            stream.answer = `${stream.answer}${_requireString(payload.text, 'content_chunk.text')}`;
            stream.phase = 'answering';
            continue;
        }
        if (runtimeEvent.type === 'completed') {
            const payload = _requireObject(runtimeEvent.payload, 'completed.payload');
            const content = _requireString(payload.content, 'completed.content');
            if (stream.answer.trim() === '' && content.trim() !== '') {
                stream.answer = content;
            }
            stream.phase = 'completed';
            stream.completed = true;
            continue;
        }
        if (runtimeEvent.type === 'failed') {
            const payload = _requireObject(runtimeEvent.payload, 'failed.payload');
            throw new Error(_requireNonEmptyString(payload.error, 'failed.error'));
        }
    }
}

function _errorMessage(error) {
    if (error instanceof Error && typeof error.message === 'string' && error.message !== '') {
        return error.message;
    }
    return String(error);
}

function _publicSearchErrorKind(detail, transportStatus, errorBody = null) {
    const message = _requireString(detail, 'public search error detail');
    if (message === 'search_quota_exhausted') {
        return 'search_quota_exhausted';
    }
    if (errorBody !== null && typeof errorBody === 'object' && !Array.isArray(errorBody)) {
        const errorCode = errorBody.error_code;
        if (typeof errorCode === 'string' && errorCode === 'search_quota_exhausted') {
            return 'search_quota_exhausted';
        }
    }
    if (transportStatus === 429 && message === 'search_quota_exhausted') {
        return 'search_quota_exhausted';
    }
    if (message.startsWith("Нода '") && message.includes('превышен лимит времени выполнения')) {
        return 'search_timeout';
    }
    if (message === 'All connection attempts failed') {
        return 'search_service_unavailable';
    }
    if (message === 'A2A stream finished before search/serp/completed') {
        return 'search_stream_incomplete';
    }
    if (transportStatus === 502 || transportStatus === 503) {
        return 'search_service_unavailable';
    }
    return 'search_failed';
}

function _publicSearchErrorStatus(kind, transportStatus) {
    const errorKind = _requirePublicSearchErrorKind(kind, 'public search error kind');
    if (errorKind === 'search_timeout') {
        return 504;
    }
    if (errorKind === 'search_service_unavailable') {
        return 503;
    }
    if (errorKind === 'search_quota_exhausted') {
        return 429;
    }
    if (typeof transportStatus !== 'number' || !Number.isFinite(transportStatus)) {
        throw new Error('public search transport status must be finite number');
    }
    return transportStatus;
}

function _isPublicSearchSessionFresh(session, mode) {
    const sessionMode = _requirePublicSearchSessionMode(mode, 'public search session mode');
    if (session.branch_id !== sessionMode) {
        return false;
    }
    const expiresAtMs = Date.parse(session.expires_at);
    if (!Number.isFinite(expiresAtMs)) {
        throw new Error('session.expires_at must be parseable ISO datetime');
    }
    return Date.now() < expiresAtMs - PUBLIC_SEARCH_SESSION_EXPIRY_SKEW_MS;
}

function _rememberPublicSearchSession(session) {
    publicSearchSessionByMode.set(session.branch_id, session);
}

async function _issuePublicSearchSession(mode, { force = false, consumeSearchQuota = true } = {}) {
    const sessionMode = _requirePublicSearchSessionMode(mode, 'public search session mode');
    if (!force) {
        const cachedSession = publicSearchSessionByMode.get(sessionMode);
        if (cachedSession !== undefined && _isPublicSearchSessionFresh(cachedSession, sessionMode)) {
            return cachedSession;
        }
    }
    const session = _normalizeSession(await httpRequest({
        method: 'POST',
        url: '/frontend/api/public/search/session',
        credentials: 'same-origin',
        body: {
            mode: sessionMode,
            origin: _windowOrigin(),
            expires_in_seconds: 300,
            consume_search_quota: consumeSearchQuota,
        },
    }));
    _rememberPublicSearchSession(session);
    return session;
}

async function _runPublicSearch({ payload, ctx, event }) {
    if (!ctx || typeof ctx.dispatch !== 'function') {
        throw new Error('frontend/public_search_run: ctx.dispatch required');
    }
    if (!event || typeof event.id !== 'string' || event.id === '') {
        throw new Error('frontend/public_search_run: event.id required');
    }
    const request = _normalizeRunPayload(payload);
    const session = await _issuePublicSearchSession(request.mode, { force: true, consumeSearchQuota: true });
    const stream = _streamFromRunPayload(request);
    _publishStream(ctx, event.id, stream);

    let streamError = null;
    const controller = new AbortController();
    _replaceActiveSearchRun(request.run_id, controller);
    const onEvent = (frame) => {
        if (streamError !== null) {
            return;
        }
        try {
            const envelope = _requireObject(frame, 'A2A SSE frame');
            if (Object.prototype.hasOwnProperty.call(envelope, 'error')) {
                const rawError = envelope.error;
                const message = rawError && typeof rawError === 'object' && typeof rawError.message === 'string'
                    ? rawError.message
                    : 'A2A stream error';
                throw new Error(message);
            }
            const result = _requireObject(envelope.result, 'A2A SSE result');
            const mapped = mapA2aResultToChatRuntimeEvents(result, {
                currentTaskId: stream.task_id,
                contextId: stream.context_id,
                taskPrimed: stream.task_primed,
            });
            if (typeof mapped.nextTaskId === 'string') {
                stream.task_id = mapped.nextTaskId;
            }
            if (mapped.taskPrimed === true) {
                stream.task_primed = true;
            }
            _applyRuntimeEvents(stream, mapped.events);
            _publishStream(ctx, event.id, stream);
        } catch (error) {
            streamError = new Error(_errorMessage(error));
            controller.abort();
        }
    };

    try {
        await streamEmbedA2A({
            baseUrl: _flowsBaseUrl(),
            embedId: session.embed_id,
            branchId: session.branch_id,
            message: request.query,
            contextId: stream.context_id,
            files: request.files,
            metadata: { branch: session.branch_id },
            getHeaders: async () => ({ Authorization: `${session.token_type} ${session.token}` }),
            credentials: 'omit',
            signal: controller.signal,
        }, onEvent);
    } catch (error) {
        if (streamError !== null) {
            throw streamError;
        }
        throw error;
    } finally {
        _clearActiveSearchRun(request.run_id, controller);
    }
    if (streamError !== null) {
        throw streamError;
    }
    if (stream.completed !== true) {
        throw new Error('A2A stream finished before search/serp/completed');
    }
    _publishStream(ctx, event.id, stream);
    return _normalizeStreamPayload(stream);
}

function _sourceDescribeMessage(request) {
    const source = request.source;
    const displayUrl = source.display_url !== '' ? source.display_url : source.url;
    return [
        'AI SOURCE DESCRIBE',
        '',
        `Исходный запрос: ${request.query}`,
        '',
        'Источник:',
        `Title: ${source.title}`,
        `URL: ${source.url}`,
        `Display URL: ${displayUrl}`,
        `Provider: ${source.provider}`,
        `Rank: ${source.rank}`,
        `Snippet: ${source.snippet}`,
        '',
        'Задача: загляни внутрь этого источника и кратко объясни, что там есть и почему это релевантно исходному запросу.',
    ].join('\n');
}

async function _runPublicSearchSourceDescribe({ payload, ctx, event }) {
    if (!ctx || typeof ctx.dispatch !== 'function') {
        throw new Error('frontend/public_search_source_describe: ctx.dispatch required');
    }
    if (!event || typeof event.id !== 'string' || event.id === '') {
        throw new Error('frontend/public_search_source_describe: event.id required');
    }
    const request = _normalizeSourceDescribePayload(payload);
    const session = await _issuePublicSearchSession(request.mode, { consumeSearchQuota: false });
    const sourceStream = _sourceStreamFromPayload(request);
    _publishSourceDescribeStream(ctx, event.id, sourceStream);

    let streamError = null;
    const controller = new AbortController();
    const onEvent = (frame) => {
        if (streamError !== null) {
            return;
        }
        try {
            const envelope = _requireObject(frame, 'A2A SSE frame');
            if (Object.prototype.hasOwnProperty.call(envelope, 'error')) {
                const rawError = envelope.error;
                const message = rawError && typeof rawError === 'object' && typeof rawError.message === 'string'
                    ? rawError.message
                    : 'A2A stream error';
                throw new Error(message);
            }
            const result = _requireObject(envelope.result, 'A2A SSE result');
            const mapped = mapA2aResultToChatRuntimeEvents(result, {
                currentTaskId: sourceStream.task_id,
                contextId: sourceStream.context_id,
                taskPrimed: sourceStream.task_primed,
            });
            if (typeof mapped.nextTaskId === 'string') {
                sourceStream.task_id = mapped.nextTaskId;
            }
            if (mapped.taskPrimed === true) {
                sourceStream.task_primed = true;
            }
            _applySourceDescribeRuntimeEvents(sourceStream, mapped.events);
            _publishSourceDescribeStream(ctx, event.id, sourceStream);
        } catch (error) {
            streamError = new Error(_errorMessage(error));
            controller.abort();
        }
    };

    try {
        await streamEmbedA2A({
            baseUrl: _flowsBaseUrl(),
            embedId: session.embed_id,
            branchId: session.branch_id,
            message: _sourceDescribeMessage(request),
            contextId: sourceStream.context_id,
            files: [],
            metadata: { branch: session.branch_id, source_url: request.source.url },
            getHeaders: async () => ({ Authorization: `${session.token_type} ${session.token}` }),
            credentials: 'omit',
            signal: controller.signal,
        }, onEvent);
    } catch (error) {
        if (streamError !== null) {
            throw streamError;
        }
        throw error;
    }
    if (streamError !== null) {
        throw streamError;
    }
    if (sourceStream.completed !== true) {
        throw new Error('A2A stream finished before source description completed');
    }
    _publishSourceDescribeStream(ctx, event.id, sourceStream);
    return _normalizeSourceDescribeStream(sourceStream);
}

export const publicSearchRunOp = createAsyncOp({
    name: 'frontend/public_search_run',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/search/session' },
    extraInitial: { stream: _emptyStream(), active_run_id: '', error_kind: '', error_detail: '' },
    extraEvents: { STREAM_EVENT: 'stream_event', SERP_APPEND: 'serp_append' },
    actions: { reset: 'reset' },
    extraReducer: (state, event, events) => {
        if (event.type === events.RESET) {
            return {
                ...state,
                stream: _emptyStream(),
                active_run_id: '',
                error_kind: '',
                error_detail: '',
                lastResult: null,
                error: null,
            };
        }
        if (event.type === events.SERP_APPEND) {
            const payload = _requireObject(event.payload, 'serp_append payload');
            const stream = _requireObject(state.stream, 'stream state');
            const appended = _normalizeResults(payload.results);
            const hasMore = _requireBoolean(payload.has_more, 'serp_append.has_more');
            const totalCount = _requireNumber(payload.total_count, 'serp_append.total_count');
            const mergedResults = [..._normalizeResults(stream.results), ...appended];
            return {
                ...state,
                stream: {
                    ...stream,
                    results: mergedResults,
                    has_more: hasMore,
                    total_count: totalCount,
                    results_offset: mergedResults.length,
                },
            };
        }
        if (event.type === events.REQUESTED) {
            const request = _normalizeRunPayload(event.payload);
            return {
                ...state,
                active_run_id: request.run_id,
                stream: _streamFromRunPayload(request),
                error_kind: '',
                error_detail: '',
            };
        }
        if (event.type === events.STREAM_EVENT) {
            const payload = _requireObject(event.payload, 'stream event payload');
            const stream = _normalizeStreamPayload(payload.stream);
            if (stream.run_id !== state.active_run_id) {
                return state;
            }
            return { ...state, stream };
        }
        if (event.type === events.SUCCEEDED) {
            const payload = _requireObject(event.payload, 'succeeded payload');
            const stream = _normalizeStreamPayload(payload.result);
            if (stream.run_id !== state.active_run_id) {
                return {
                    ...state,
                    busy: state.active_run_id !== '',
                    error: null,
                };
            }
            return { ...state, active_run_id: '', stream, error_kind: '', error_detail: '' };
        }
        if (event.type === events.FAILED) {
            const failed = _normalizeFailedRunPayload(event);
            if (failed.run_id !== state.active_run_id) {
                return {
                    ...state,
                    busy: state.active_run_id !== '',
                    error: null,
                };
            }
            return {
                ...state,
                active_run_id: '',
                error_kind: failed.error_kind,
                error_detail: failed.detail,
            };
        }
        return state;
    },
    request: async (args) => {
        const request = _normalizeRunPayload(args.payload);
        try {
            return await _runPublicSearch({ ...args, payload: request });
        } catch (error) {
            const detail = _errorMessage(error);
            const transportStatus = error instanceof HttpError ? error.status : 502;
            const errorBody = error instanceof HttpError ? error.body : null;
            const errorKind = _publicSearchErrorKind(detail, transportStatus, errorBody);
            const status = _publicSearchErrorStatus(errorKind, transportStatus);
            throw new HttpError(errorKind, status, {
                detail,
                error_kind: errorKind,
                run_id: request.run_id,
            });
        }
    },
});

export const publicSearchSerpMoreOp = createAsyncOp({
    name: 'frontend/public_search_serp_more',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/search/serp/more' },
    request: async ({ payload, ctx, event }) => {
        if (!ctx || typeof ctx.dispatch !== 'function') {
            throw new Error('frontend/public_search_serp_more: ctx.dispatch required');
        }
        if (!event || typeof event.id !== 'string' || event.id === '') {
            throw new Error('frontend/public_search_serp_more: event.id required');
        }
        const body = _requireObject(payload, 'serp_more payload');
        const mode = _requirePublicSearchSessionMode(body.mode, 'serp_more.mode');
        const serpCacheKey = _requireNonEmptyString(body.serp_cache_key, 'serp_more.serp_cache_key');
        const offset = _requireNumber(body.offset, 'serp_more.offset');
        const limit = _requireNumber(body.limit, 'serp_more.limit');
        const session = await _issuePublicSearchSession(mode, { consumeSearchQuota: false });
        const response = _requireObject(await httpRequest({
            method: 'POST',
            url: '/frontend/api/public/search/serp/more',
            credentials: 'same-origin',
            headers: { Authorization: `${session.token_type} ${session.token}` },
            body: {
                serp_cache_key: serpCacheKey,
                offset,
                limit,
            },
        }), 'serp_more response');
        ctx.dispatch(
            'frontend/public_search_run/serp_append',
            {
                results: response.results,
                has_more: response.has_more,
                total_count: response.total_count,
            },
            { causation_id: event.id, source: 'http' },
        );
        return {
            results: _normalizeResults(response.results),
            has_more: _requireBoolean(response.has_more, 'serp_more.has_more'),
            total_count: _requireNumber(response.total_count, 'serp_more.total_count'),
        };
    },
});

export const publicSearchSourceDescribeOp = createAsyncOp({
    name: 'frontend/public_search_source_describe',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/search/session' },
    extraInitial: {
        source_stream: _emptySourceDescribeStream(),
        descriptions: {},
        active_url: '',
    },
    extraEvents: { STREAM_EVENT: 'stream_event' },
    actions: { reset: 'reset' },
    extraReducer: (state, event, events) => {
        if (event.type === events.RESET) {
            return {
                ...state,
                source_stream: _emptySourceDescribeStream(),
                descriptions: {},
                active_url: '',
                lastResult: null,
                error: null,
            };
        }
        if (event.type === events.REQUESTED) {
            const request = _normalizeSourceDescribePayload(event.payload);
            const sourceStream = _sourceStreamFromPayload(request);
            const descriptions = _requireObject(state.descriptions, 'source descriptions state');
            return {
                ...state,
                source_stream: sourceStream,
                descriptions: { ...descriptions, [sourceStream.url]: sourceStream },
                active_url: sourceStream.url,
            };
        }
        if (event.type === events.STREAM_EVENT) {
            const payload = _requireObject(event.payload, 'source stream event payload');
            const sourceStream = _normalizeSourceDescribeStream(payload.source_stream);
            const descriptions = _requireObject(state.descriptions, 'source descriptions state');
            return {
                ...state,
                source_stream: sourceStream,
                descriptions: { ...descriptions, [sourceStream.url]: sourceStream },
                active_url: sourceStream.url,
            };
        }
        if (event.type === events.SUCCEEDED) {
            const payload = _requireObject(event.payload, 'source succeeded payload');
            const sourceStream = _normalizeSourceDescribeStream(payload.result);
            const descriptions = _requireObject(state.descriptions, 'source descriptions state');
            return {
                ...state,
                source_stream: sourceStream,
                descriptions: { ...descriptions, [sourceStream.url]: sourceStream },
                active_url: sourceStream.url,
            };
        }
        return state;
    },
    request: async (args) => {
        try {
            return await _runPublicSearchSourceDescribe(args);
        } catch (error) {
            if (error instanceof HttpError) {
                throw error;
            }
            const message = _errorMessage(error);
            throw new HttpError(message, 502, { detail: message });
        }
    },
});
