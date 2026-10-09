/**
 * Публичный запуск Humanitec Search.
 *
 * Исполнение остаётся в Flows A2A/SSE:
 *   1. frontend выдаёт short-lived embed-session token;
 *   2. code-ноды flow public_search пишут staged-поля state (`serp_results`, `serp_completed`,
 *      `research_*`), которые приходят артефактом `state` (snapshot + RFC 6902 патчи),
 *      а текст ответа — артефактом `response`;
 *   3. эта фабрика сводит их в SERP-state для UI.
 */
import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest, HttpError } from '@platform/lib/events/http.js';
import { a2aEndpointUrl, buildSendMessageBody, buildUserMessage } from '@platform/lib/flow-ui/protocol/a2a-codec.js';
import {
    consumeA2AStream as consumeA2aStream,
    isTerminalTaskState,
    unwrapA2aStreamResult,
} from '@platform/lib/flow-ui/protocol/a2a-stream.js';
import { RESPONSE_ARTIFACT_NAME, STATE_ARTIFACT_ID } from '@platform/lib/flow-ui/protocol/constants.js';
import { applyJsonPatch, decodePart, textFromParts } from '@platform/lib/flow-ui/protocol/parts.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import {
    takePendingPublicSearchRunFiles,
    uploadPublicSearchFilesForA2a,
} from '../../_helpers/public-search-files.js';

const SEARCH_RUN_MODES = Object.freeze(new Set(['quick', 'deep', 'research']));
const PUBLIC_SEARCH_SESSION_MODES = Object.freeze(new Set(['quick', 'deep', 'research', 'source']));
const PUBLIC_SEARCH_ERROR_KINDS = Object.freeze(new Set([
    'search_timeout',
    'search_service_unavailable',
    'search_runtime_unavailable',
    'search_stream_incomplete',
    'search_quota_exhausted',
    'search_failed',
]));
const PUBLIC_SEARCH_STREAM_EVENT = 'frontend/public_search_run/stream_event';
const PUBLIC_SEARCH_SOURCE_STREAM_EVENT = 'frontend/public_search_source_describe/stream_event';
const RUN_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

let activeSearchRun: { run_id: string; controller: AbortController } | null = null;

/** @type {Map<string, ReturnType<typeof _normalizeSession>>} */
const publicSearchSessionByMode = new Map();

const PUBLIC_SEARCH_SESSION_EXPIRY_SKEW_MS = 30_000;
const PUBLIC_SEARCH_STREAM_THROTTLE_MS = 90;

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
        rank_stage: 'preview',
        total_count: 0,
        has_more: false,
        results_offset: 0,
        page_limit: 10,
        research_brief: '',
        research_sub_questions: [],
        research_outline: [],
        research_steps: [],
        research_sources: [],
        report: '',
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

function _requireObject(value: unknown, label: string) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`${label} must be an object`);
    }
    return value;
}

function _requireArray(value: unknown, label: string) {
    if (!Array.isArray(value)) {
        throw new Error(`${label} must be an array`);
    }
    return value;
}

function _requireString(value: unknown, label: string) {
    if (typeof value !== 'string') {
        throw new Error(`${label} must be a string`);
    }
    return value;
}

function _requireNonEmptyString(value: unknown, label: string) {
    const text = _requireString(value, label).trim();
    if (text === '') {
        throw new Error(`${label} must be non-empty`);
    }
    return text;
}

function _requireNumber(value: unknown, label: string) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`${label} must be a finite number`);
    }
    return value;
}

function _requireBoolean(value: unknown, label: string) {
    if (value !== true && value !== false) {
        throw new Error(`${label} must be boolean`);
    }
    return value;
}

function _requireNullableString(value: unknown, label: string) {
    if (value === null) {
        return null;
    }
    return _requireString(value, label);
}

function _requireRankStage(value: unknown, label: string) {
    if (value === undefined) {
        return 'preview';
    }
    const stage = _requireNonEmptyString(value, label);
    if (stage !== 'preview' && stage !== 'refined') {
        throw new Error(`${label} is invalid`);
    }
    return stage;
}

function _requireSearchRunMode(value: unknown, label: string) {
    const mode = _requireNonEmptyString(value, label);
    if (!SEARCH_RUN_MODES.has(mode)) {
        throw new Error(`${label} is invalid`);
    }
    return mode;
}

function _requirePublicSearchSessionMode(value: unknown, label: string) {
    const mode = _requireNonEmptyString(value, label);
    if (!PUBLIC_SEARCH_SESSION_MODES.has(mode)) {
        throw new Error(`${label} is invalid`);
    }
    return mode;
}

function _requirePublicSearchErrorKind(value: unknown, label: string) {
    const kind = _requireNonEmptyString(value, label);
    if (!PUBLIC_SEARCH_ERROR_KINDS.has(kind)) {
        throw new Error(`${label} is invalid`);
    }
    return kind;
}

function _normalizeRunPayload(payload: any) {
    const body = _requireObject(payload, 'frontend/public_search_run payload');
    const runId = _requireNonEmptyString((body as Record<string, any>).run_id, 'run_id');
    if (!RUN_ID_PATTERN.test(runId)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    const query = _requireNonEmptyString((body as Record<string, any>).query, 'query');
    const mode = _requireSearchRunMode((body as Record<string, any>).mode, 'mode');
    if (Object.prototype.hasOwnProperty.call(body, 'files')) {
        throw new Error(
            'frontend/public_search_run: files payload removed; use pending browser Files + chunked upload',
        );
    }
    return { run_id: runId, query, mode };
}

function _normalizeResult(value: unknown, index: number) {
    const item = _requireObject(value, `results[${index}]`);
    return {
        title: _requireNonEmptyString((item as Record<string, any>).title, `results[${index}].title`),
        url: _requireNonEmptyString((item as Record<string, any>).url, `results[${index}].url`),
        snippet: _requireString((item as Record<string, any>).snippet, `results[${index}].snippet`),
        display_url: _requireString((item as Record<string, any>).display_url, `results[${index}].display_url`),
        provider: _requireNonEmptyString((item as Record<string, any>).provider, `results[${index}].provider`),
        provider_rank: _requireNumber((item as Record<string, any>).provider_rank, `results[${index}].provider_rank`),
        rank: _requireNumber((item as Record<string, any>).rank, `results[${index}].rank`),
        score: _requireNumber((item as Record<string, any>).score, `results[${index}].score`),
        published_at: _requireNullableString((item as Record<string, any>).published_at, `results[${index}].published_at`),
        source_type: _requireNonEmptyString((item as Record<string, any>).source_type, `results[${index}].source_type`),
        site_name: _requireString((item as Record<string, any>).site_name, `results[${index}].site_name`),
        favicon_url: _requireString((item as Record<string, any>).favicon_url, `results[${index}].favicon_url`),
        preview_image_url: _requireString((item as Record<string, any>).preview_image_url, `results[${index}].preview_image_url`),
    };
}

function _normalizeResults(value: unknown) {
    return _requireArray(value, 'results').map((item, index) => _normalizeResult(item, index));
}

function _normalizeProviders(value: unknown) {
    const providers = _requireObject(value, 'providers');
    const out: Record<string, any> = {};
    for (const [name, raw] of Object.entries(providers)) {
        const status = _requireObject(raw, `providers.${name}`);
        out[name] = {
            ok: _requireBoolean((status as Record<string, any>).ok, `providers.${name}.ok`),
            latency_ms: _requireNumber((status as Record<string, any>).latency_ms, `providers.${name}.latency_ms`),
            results_count: _requireNumber((status as Record<string, any>).results_count, `providers.${name}.results_count`),
            error: _requireNullableString((status as Record<string, any>).error, `providers.${name}.error`),
            selected: _requireBoolean((status as Record<string, any>).selected, `providers.${name}.selected`),
            skipped: _requireBoolean((status as Record<string, any>).skipped, `providers.${name}.skipped`),
            skip_reason: _requireNullableString((status as Record<string, any>).skip_reason, `providers.${name}.skip_reason`),
        };
    }
    return out;
}

function _normalizeSuggestion(value: unknown, index: number, label: string) {
    const item = _requireObject(value, `${label}[${index}]`);
    return {
        text: _requireNonEmptyString((item as Record<string, any>).text, `${label}[${index}].text`),
        kind: _requireNonEmptyString((item as Record<string, any>).kind, `${label}[${index}].kind`),
        score: _requireNumber((item as Record<string, any>).score, `${label}[${index}].score`),
    };
}

function _normalizeSuggestions(value: unknown, label: string) {
    return _requireArray(value, label).map((item, index) => _normalizeSuggestion(item, index, label));
}

function _normalizeStringArray(value: unknown, label: string) {
    return _requireArray(value, label).map((item, index) => _requireString(item, `${label}[${index}]`));
}

function _normalizeInsight(value: unknown, index: number) {
    const item = _requireObject(value, `result_insights[${index}]`);
    return {
        title: _requireNonEmptyString((item as Record<string, any>).title, `result_insights[${index}].title`),
        url: _requireNonEmptyString((item as Record<string, any>).url, `result_insights[${index}].url`),
        provider: _requireNonEmptyString((item as Record<string, any>).provider, `result_insights[${index}].provider`),
        rank: _requireNumber((item as Record<string, any>).rank, `result_insights[${index}].rank`),
        confidence: _requireNumber((item as Record<string, any>).confidence, `result_insights[${index}].confidence`),
        matched_terms: _normalizeStringArray((item as Record<string, any>).matched_terms, `result_insights[${index}].matched_terms`),
        relevance_hint: _requireNonEmptyString((item as Record<string, any>).relevance_hint, `result_insights[${index}].relevance_hint`),
        actions: _normalizeStringArray((item as Record<string, any>).actions, `result_insights[${index}].actions`),
    };
}

function _normalizeInsights(value: unknown) {
    return _requireArray(value, 'result_insights').map((item, index) => _normalizeInsight(item, index));
}

function _normalizeResearchStep(value: unknown, index: number) {
    const item = _requireObject(value, `research_steps[${index}]`);
    return {
        phase: _requireNonEmptyString((item as Record<string, any>).phase, `research_steps[${index}].phase`),
        count: _requireNumber((item as Record<string, any>).count, `research_steps[${index}].count`),
        title: _requireString((item as Record<string, any>).title, `research_steps[${index}].title`),
    };
}

function _normalizeResearchSteps(value: unknown) {
    return _requireArray(value, 'research_steps').map((item, index) => _normalizeResearchStep(item, index));
}

function _normalizeResearchSource(value: unknown, index: number) {
    const item = _requireObject(value, `research_sources[${index}]`);
    return {
        index: _requireNumber((item as Record<string, any>).index, `research_sources[${index}].index`),
        url: _requireNonEmptyString((item as Record<string, any>).url, `research_sources[${index}].url`),
        title: _requireNonEmptyString((item as Record<string, any>).title, `research_sources[${index}].title`),
        provider: _requireString((item as Record<string, any>).provider, `research_sources[${index}].provider`),
        site_name: _requireString((item as Record<string, any>).site_name, `research_sources[${index}].site_name`),
        snippet: _requireString((item as Record<string, any>).snippet, `research_sources[${index}].snippet`),
    };
}

function _normalizeResearchSources(value: unknown) {
    return _requireArray(value, 'research_sources').map((item, index) => _normalizeResearchSource(item, index));
}

function _normalizeFailedRunPayload(event: PlatformEvent) {
    const payload = _requireObject(event.payload, 'failed payload');
    const body = _requireObject((payload as Record<string, any>).body, 'failed payload body');
    return {
        run_id: _requireNonEmptyString((body as Record<string, any>).run_id, 'failed payload body.run_id'),
        error_kind: _requirePublicSearchErrorKind((body as Record<string, any>).error_kind, 'failed payload body.error_kind'),
        detail: _requireString((body as Record<string, any>).detail, 'failed payload body.detail'),
    };
}

function _normalizeSourceDescribePayload(payload: any) {
    const body = _requireObject(payload, 'frontend/public_search_source_describe payload');
    const runId = _requireNonEmptyString((body as Record<string, any>).run_id, 'run_id');
    if (!RUN_ID_PATTERN.test(runId)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    const query = _requireNonEmptyString((body as Record<string, any>).query, 'query');
    const source = _normalizeResult((body as Record<string, any>).source, 0);
    return { run_id: runId, query, mode: 'source', source };
}

function _contextIdFromRunId(runId: Record<string, any>) {
    const value = _requireNonEmptyString(runId, 'run_id');
    if (!RUN_ID_PATTERN.test(value)) {
        throw new Error('run_id must contain only latin letters, digits, underscore or dash');
    }
    return value;
}

function _streamFromRunPayload(payload: Record<string, any>) {
    return {
        ..._emptyStream(),
        run_id: payload.run_id,
        query: payload.query,
        mode: payload.mode,
        context_id: _contextIdFromRunId(payload.run_id),
        phase: 'starting',
    };
}

function _sourceStreamFromPayload(payload: Record<string, any>) {
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

function _normalizeStreamPayload(value: unknown) {
    const stream = _requireObject(value, 'stream');
    return {
        kind: 'public_search_stream',
        version: 1,
        run_id: _requireNonEmptyString((stream as Record<string, any>).run_id, 'stream.run_id'),
        query: _requireNonEmptyString((stream as Record<string, any>).query, 'stream.query'),
        mode: _requireSearchRunMode((stream as Record<string, any>).mode, 'stream.mode'),
        phase: _requireNonEmptyString((stream as Record<string, any>).phase, 'stream.phase'),
        activity: _requireString((stream as Record<string, any>).activity, 'stream.activity'),
        task_id: _requireString((stream as Record<string, any>).task_id, 'stream.task_id'),
        context_id: _requireString((stream as Record<string, any>).context_id, 'stream.context_id'),
        task_primed: _requireBoolean((stream as Record<string, any>).task_primed, 'stream.task_primed'),
        results: _normalizeResults((stream as Record<string, any>).results),
        providers: _normalizeProviders((stream as Record<string, any>).providers),
        suggestions: _normalizeSuggestions((stream as Record<string, any>).suggestions, 'suggestions'),
        followups: _normalizeSuggestions((stream as Record<string, any>).followups, 'followups'),
        result_insights: _normalizeInsights((stream as Record<string, any>).result_insights),
        answer: _requireString((stream as Record<string, any>).answer, 'stream.answer'),
        markdown_sources: _requireString((stream as Record<string, any>).markdown_sources, 'stream.markdown_sources'),
        completed: _requireBoolean((stream as Record<string, any>).completed, 'stream.completed'),
        serp_cache_key: _requireString((stream as Record<string, any>).serp_cache_key, 'stream.serp_cache_key'),
        rank_stage: _requireRankStage((stream as Record<string, any>).rank_stage, 'stream.rank_stage'),
        total_count: _requireNumber((stream as Record<string, any>).total_count, 'stream.total_count'),
        has_more: _requireBoolean((stream as Record<string, any>).has_more, 'stream.has_more'),
        results_offset: _requireNumber((stream as Record<string, any>).results_offset, 'stream.results_offset'),
        page_limit: _requireNumber((stream as Record<string, any>).page_limit, 'stream.page_limit'),
        research_brief: _requireString((stream as Record<string, any>).research_brief, 'stream.research_brief'),
        research_sub_questions: _normalizeStringArray((stream as Record<string, any>).research_sub_questions, 'stream.research_sub_questions'),
        research_outline: _normalizeStringArray((stream as Record<string, any>).research_outline, 'stream.research_outline'),
        research_steps: _normalizeResearchSteps((stream as Record<string, any>).research_steps),
        research_sources: _normalizeResearchSources((stream as Record<string, any>).research_sources),
        report: _requireString((stream as Record<string, any>).report, 'stream.report'),
    };
}

function _normalizeSourceDescribeStream(value: unknown) {
    const stream = _requireObject(value, 'source_stream');
    return {
        kind: 'public_search_source_stream',
        version: 1,
        run_id: _requireNonEmptyString((stream as Record<string, any>).run_id, 'source_stream.run_id'),
        query: _requireNonEmptyString((stream as Record<string, any>).query, 'source_stream.query'),
        title: _requireNonEmptyString((stream as Record<string, any>).title, 'source_stream.title'),
        url: _requireNonEmptyString((stream as Record<string, any>).url, 'source_stream.url'),
        display_url: _requireString((stream as Record<string, any>).display_url, 'source_stream.display_url'),
        provider: _requireNonEmptyString((stream as Record<string, any>).provider, 'source_stream.provider'),
        rank: _requireNumber((stream as Record<string, any>).rank, 'source_stream.rank'),
        phase: _requireNonEmptyString((stream as Record<string, any>).phase, 'source_stream.phase'),
        activity: _requireString((stream as Record<string, any>).activity, 'source_stream.activity'),
        task_id: _requireString((stream as Record<string, any>).task_id, 'source_stream.task_id'),
        context_id: _requireString((stream as Record<string, any>).context_id, 'source_stream.context_id'),
        task_primed: _requireBoolean((stream as Record<string, any>).task_primed, 'source_stream.task_primed'),
        answer: _requireString((stream as Record<string, any>).answer, 'source_stream.answer'),
        completed: _requireBoolean((stream as Record<string, any>).completed, 'source_stream.completed'),
    };
}

function _normalizeSession(value: unknown) {
    const session = _requireObject(value, 'public search session');
    const tokenType = _requireNonEmptyString((session as Record<string, any>).token_type, 'session.token_type');
    if (tokenType !== 'Bearer') {
        throw new Error('session.token_type must be Bearer');
    }
    return {
        token: _requireNonEmptyString((session as Record<string, any>).token, 'session.token'),
        token_type: tokenType,
        expires_at: _requireNonEmptyString((session as Record<string, any>).expires_at, 'session.expires_at'),
        embed_id: _requireNonEmptyString((session as Record<string, any>).embed_id, 'session.embed_id'),
        flow_id: _requireNonEmptyString((session as Record<string, any>).flow_id, 'session.flow_id'),
        branch_id: _requirePublicSearchSessionMode((session as Record<string, any>).branch_id, 'session.branch_id'),
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

function _publishStream(ctx: Record<string, any>, eventId: string, stream: Record<string, any>) {
    ctx.dispatch(
        PUBLIC_SEARCH_STREAM_EVENT,
        { stream: _normalizeStreamPayload(stream) },
        { causation_id: eventId, source: 'http' },
    );
}

/**
 * Коалесинг публикаций stream'а во время стрима LLM-ответа: `content_chunk`
 * приходят десятками в секунду и без троттлинга каждый вызывает полный re-render
 * страницы (мерцание, layout-shift). Редкие важные кадры (results/suggestions/
 * insights/completed/task_started/failed) публикуются немедленно.
 */
function _createStreamPublisher(ctx: Record<string, any>, eventId: string, publishFn: (ctx: Record<string, any>, eventId: string, stream: Record<string, any>) => void) {
    let timer = 0;
    let pending: Record<string, any> | null = null;
    const flush = () => {
        if (timer !== 0) {
            clearTimeout(timer);
            timer = 0;
        }
        if (pending !== null) {
            const stream = pending;
            pending = null;
            publishFn(ctx, eventId, stream);
        }
    };
    return {
        publish: (stream: Record<string, any>, immediate: boolean) => {
            pending = stream;
            if (immediate === true) {
                flush();
                return;
            }
            if (timer === 0) {
                timer = setTimeout(flush, PUBLIC_SEARCH_STREAM_THROTTLE_MS);
            }
        },
        cancel: () => {
            if (timer !== 0) {
                clearTimeout(timer);
                timer = 0;
            }
            pending = null;
        },
    };
}

function _publishSourceDescribeStream(ctx: Record<string, any>, eventId: string, sourceStream: Record<string, any>) {
    ctx.dispatch(
        PUBLIC_SEARCH_SOURCE_STREAM_EVENT,
        { source_stream: _normalizeSourceDescribeStream(sourceStream) },
        { causation_id: eventId, source: 'http' },
    );
}

function _replaceActiveSearchRun(runId: string, controller: AbortController) {
    const id = _requireNonEmptyString(runId, 'active search run_id');
    if (!(controller instanceof AbortController)) {
        throw new Error('active search controller must be AbortController');
    }
    if (activeSearchRun !== null) {
        activeSearchRun.controller.abort();
    }
    activeSearchRun = { run_id: id, controller };
}

function _clearActiveSearchRun(runId: string, controller: AbortController) {
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

function _applySearchUiEvent(stream: Record<string, any>, event: PlatformEvent) {
    const eventType = _requireNonEmptyString(event.type, 'staged search event type');
    if (eventType.startsWith('files.')) {
        return;
    }
    const payload = _requireObject(event.payload, 'staged search event payload');
    if (eventType === 'search/serp/results_ready') {
        stream.phase = 'results';
        stream.rank_stage = 'preview';
        stream.results = _normalizeResults((payload as Record<string, any>).results);
        stream.providers = _normalizeProviders((payload as Record<string, any>).providers);
        stream.total_count = _requireNumber((payload as Record<string, any>).total_count, 'results_ready.total_count');
        stream.has_more = _requireBoolean((payload as Record<string, any>).has_more, 'results_ready.has_more');
        stream.results_offset = stream.results.length;
        if (Object.prototype.hasOwnProperty.call(payload, 'serp_cache_key')) {
            const cacheKey = (payload as Record<string, any>).serp_cache_key;
            if (cacheKey === null) {
                stream.serp_cache_key = '';
            } else {
                stream.serp_cache_key = _requireNonEmptyString(cacheKey, 'results_ready.serp_cache_key');
            }
        }
        if (Object.prototype.hasOwnProperty.call(payload, 'limit')) {
            stream.page_limit = _requireNumber((payload as Record<string, any>).limit, 'results_ready.limit');
        }
        return;
    }
    if (eventType === 'search/serp/results_refined') {
        // Refined-порядок доранжирования: обновляем результаты и cache key,
        // но НЕ меняем phase — LLM-ответ уже мог стартовать по preview.
        stream.rank_stage = 'refined';
        stream.results = _normalizeResults((payload as Record<string, any>).results);
        if (Object.prototype.hasOwnProperty.call(payload, 'serp_cache_key')) {
            const cacheKey = (payload as Record<string, any>).serp_cache_key;
            if (cacheKey === null) {
                stream.serp_cache_key = '';
            } else {
                stream.serp_cache_key = _requireNonEmptyString(cacheKey, 'results_refined.serp_cache_key');
            }
        }
        return;
    }
    if (eventType === 'search/serp/suggestions_ready') {
        stream.phase = 'suggestions';
        stream.suggestions = _normalizeSuggestions((payload as Record<string, any>).suggestions, 'suggestions');
        stream.followups = _normalizeSuggestions((payload as Record<string, any>).followups, 'followups');
        return;
    }
    if (eventType === 'search/serp/insights_ready') {
        stream.phase = 'insights';
        stream.result_insights = _normalizeInsights((payload as Record<string, any>).result_insights);
        return;
    }
    if (eventType === 'search/research/plan_ready') {
        stream.phase = 'plan';
        stream.report = '';
        stream.query = _requireNonEmptyString((payload as Record<string, any>).query, 'plan_ready.query');
        stream.research_brief = _requireString((payload as Record<string, any>).brief, 'plan_ready.brief');
        stream.research_sub_questions = _normalizeStringArray((payload as Record<string, any>).sub_questions, 'plan_ready.sub_questions');
        stream.research_outline = _normalizeStringArray((payload as Record<string, any>).outline, 'plan_ready.outline');
        const plannedQueries = _normalizeStringArray((payload as Record<string, any>).queries, 'plan_ready.queries');
        stream.research_steps = [...stream.research_steps, { phase: 'plan', count: plannedQueries.length, title: '' }];
        return;
    }
    if (eventType === 'search/research/search_ready') {
        stream.phase = 'searching';
        const found = _requireNumber((payload as Record<string, any>).found, 'search_ready.found');
        stream.research_steps = [...stream.research_steps, { phase: 'search', count: found, title: '' }];
        return;
    }
    if (eventType === 'search/research/source_read') {
        stream.phase = 'reading';
        const sourceIndex = _requireNumber((payload as Record<string, any>).index, 'source_read.index');
        const sourceTitle = _requireNonEmptyString((payload as Record<string, any>).title, 'source_read.title');
        const sourceUrl = _requireNonEmptyString((payload as Record<string, any>).url, 'source_read.url');
        const sourceProvider = _requireString((payload as Record<string, any>).provider, 'source_read.provider');
        const sourceSiteName = _requireString((payload as Record<string, any>).site_name, 'source_read.site_name');
        if (!stream.research_sources.some((item: Record<string, any>) => item.index === sourceIndex)) {
            stream.research_sources = [...stream.research_sources, {
                index: sourceIndex,
                url: sourceUrl,
                title: sourceTitle,
                provider: sourceProvider,
                site_name: sourceSiteName,
                snippet: '',
            }];
        }
        stream.research_steps = [...stream.research_steps, { phase: 'read', count: sourceIndex, title: sourceTitle }];
        return;
    }
    if (eventType === 'search/research/reflection_ready') {
        const needMore = _requireBoolean((payload as Record<string, any>).need_more, 'reflection_ready.need_more');
        stream.phase = needMore ? 'reflecting' : 'synthesizing';
        if (needMore === false) {
            stream.report = '';
        }
        const iteration = _requireNumber((payload as Record<string, any>).iteration, 'reflection_ready.iteration');
        stream.research_steps = [...stream.research_steps, { phase: 'reflect', count: iteration, title: '' }];
        return;
    }
    if (eventType === 'search/serp/completed' && (payload as Record<string, any>).kind === 'public_search_research_report') {
        stream.phase = 'completed';
        stream.mode = 'research';
        stream.query = _requireNonEmptyString((payload as Record<string, any>).query, 'research_completed.query');
        stream.research_brief = _requireString((payload as Record<string, any>).brief, 'research_completed.brief');
        stream.research_outline = _normalizeStringArray((payload as Record<string, any>).outline, 'research_completed.outline');
        stream.research_sub_questions = _normalizeStringArray((payload as Record<string, any>).sub_questions, 'research_completed.sub_questions');
        stream.report = _requireNonEmptyString((payload as Record<string, any>).report, 'research_completed.report');
        stream.research_sources = _normalizeResearchSources((payload as Record<string, any>).sources);
        stream.completed = true;
        return;
    }
    if (eventType === 'search/serp/completed') {
        stream.phase = 'completed';
        stream.mode = _requireSearchRunMode((payload as Record<string, any>).mode, 'completed.mode');
        stream.query = _requireNonEmptyString((payload as Record<string, any>).query, 'completed.query');
        stream.answer = _requireNonEmptyString((payload as Record<string, any>).answer, 'completed.answer');
        stream.markdown_sources = _requireNonEmptyString((payload as Record<string, any>).markdown_sources, 'completed.markdown_sources');
        stream.results = _normalizeResults((payload as Record<string, any>).results);
        stream.providers = _normalizeProviders((payload as Record<string, any>).providers);
        stream.suggestions = _normalizeSuggestions((payload as Record<string, any>).suggestions, 'suggestions');
        stream.followups = _normalizeSuggestions((payload as Record<string, any>).followups, 'followups');
        stream.result_insights = _normalizeInsights((payload as Record<string, any>).result_insights);
        stream.completed = true;
        return;
    }
    throw new Error(`Unsupported public search staged event: ${eventType}`);
}

/** Пути state публичного поиска → staged-события SERP; порядок задаёт приоритет применения. */
const SEARCH_STATE_EVENTS = Object.freeze([
    ['serp_results', 'search/serp/results_ready'],
    ['serp_results_refined', 'search/serp/results_refined'],
    ['serp_suggestions', 'search/serp/suggestions_ready'],
    ['serp_insights', 'search/serp/insights_ready'],
    ['research_plan', 'search/research/plan_ready'],
    ['research_search', 'search/research/search_ready'],
    ['research_reflection', 'search/research/reflection_ready'],
    ['serp_completed', 'search/serp/completed'],
]);

function _createStateFold() {
    return { state: {}, seen: new Map(), sourcesRead: 0 };
}

function _foldStateArtifact(fold: Record<string, any>, artifact: Record<string, any>) {
    for (const part of Array.isArray(artifact.parts) ? artifact.parts : []) {
        const decoded = decodePart(part);
        if (decoded.kind === 'json') {
            fold.state = _requireObject(decoded.value, 'state snapshot');
        } else if (decoded.kind === 'json_patch') {
            fold.state = applyJsonPatch(fold.state, decoded.operations);
        } else {
            throw new Error(`Unsupported state artifact part: ${decoded.kind}`);
        }
    }
}

function _stagedSearchEvents(fold: { state: Record<string, unknown>; seen: Map<string, string>; sourcesRead: number }) {
    const events: any[] = [];
    for (const [path, eventType] of SEARCH_STATE_EVENTS as unknown as ReadonlyArray<readonly [string, string]>) {
        const payload = fold.state[path as string];
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            continue;
        }
        const serialized = JSON.stringify(payload);
        if (fold.seen.get(path) === serialized) {
            continue;
        }
        fold.seen.set(path, serialized);
        events.push({ type: eventType, payload });
    }
    const sourcesRead = fold.state.research_sources_read;
    if (Array.isArray(sourcesRead)) {
        for (const source of sourcesRead.slice(fold.sourcesRead)) {
            events.push({ payload: _requireObject(source, 'research_sources_read[]') });
        }
        fold.sourcesRead = sourcesRead.length;
    }
    return events;
}

function _taskFrame(stream: Record<string, any>, unwrapped: Record<string, any>) {
    const { frameKind, event } = unwrapped;
    const taskId = frameKind === 'task' ? event.id : event.taskId;
    if (typeof taskId === 'string' && taskId !== '') {
        stream.task_id = taskId;
    }
    if (typeof event.contextId === 'string' && event.contextId !== '') {
        stream.context_id = event.contextId;
    }
    if (!stream.task_primed && typeof taskId === 'string' && taskId !== '') {
        stream.task_primed = true;
        return true;
    }
    return false;
}

function _statusFrameError(status: Record<string, any>) {
    const state = _requireNonEmptyString(status.state, 'status.state');
    if (state === 'TASK_STATE_COMPLETED' || !isTerminalTaskState(state)) {
        return null;
    }
    const text = status.message && typeof status.message === 'object' ? textFromParts((status.message as Record<string, any>).parts) : '';
    return new Error(text !== '' ? text : `A2A task ${state}`);
}

/**
 * Один кадр SendStreamingMessage → SERP-stream. Возвращает true, когда кадр
 * требует немедленной публикации (staged-событие, старт Task), false для текстовых чанков.
 */
function _applySearchFrame(stream: Record<string, any>, fold: Record<string, any>, result: Record<string, any>) {
    const unwrapped = unwrapA2aStreamResult(result);
    if (unwrapped === null) {
        throw new Error('A2A SSE result is not a StreamResponse frame');
    }
    const started = _taskFrame(stream, unwrapped);
    if (started && stream.phase === 'starting') {
        stream.phase = 'searching';
    }
    if (unwrapped.frameKind === 'task') {
        return true;
    }
    if (unwrapped.frameKind === 'statusUpdate') {
        const status = _requireObject(unwrapped.event.status, 'statusUpdate.status');
        const error = _statusFrameError(status);
        if (error !== null) {
            throw error;
        }
        if (!isTerminalTaskState((status as Record<string, any>).state) && (status as Record<string, any>).message && typeof (status as Record<string, any>).message === 'object') {
            const activity = textFromParts((status as Record<string, any>).message.parts);
            if (activity !== '') {
                stream.activity = activity;
                return false;
            }
        }
        return true;
    }
    if (unwrapped.frameKind !== 'artifactUpdate') {
        return started;
    }
    const artifact = _requireObject(unwrapped.event.artifact, 'artifactUpdate.artifact');
    if ((artifact as Record<string, any>).artifactId === STATE_ARTIFACT_ID) {
        _foldStateArtifact(fold as Record<string, any>, artifact);
        const staged = _stagedSearchEvents(fold as { state: Record<string, unknown>; seen: Map<string, string>; sourcesRead: number });
        for (const stagedEvent of staged) {
            _applySearchUiEvent(stream, stagedEvent);
        }
        return staged.length > 0 || started;
    }
    if ((artifact as Record<string, any>).name === RESPONSE_ARTIFACT_NAME) {
        const chunk = textFromParts((artifact as Record<string, any>).parts);
        if (chunk === '') {
            return started;
        }
        if (stream.mode === 'research') {
            if (stream.phase === 'synthesizing') {
                stream.report = `${stream.report}${chunk}`;
            }
        } else {
            stream.answer = `${stream.answer}${chunk}`;
            stream.phase = stream.phase === 'insights' ? 'answering' : stream.phase;
        }
        return false;
    }
    return started;
}

function _applySourceDescribeFrame(stream: Record<string, any>, result: Record<string, any>) {
    const unwrapped = unwrapA2aStreamResult(result);
    if (unwrapped === null) {
        throw new Error('A2A SSE result is not a StreamResponse frame');
    }
    const started = _taskFrame(stream, unwrapped);
    if (started && stream.phase === 'starting') {
        stream.phase = 'reading';
    }
    if (unwrapped.frameKind === 'statusUpdate') {
        const status = _requireObject(unwrapped.event.status, 'statusUpdate.status');
        const error = _statusFrameError(status);
        if (error !== null) {
            throw error;
        }
        const messageText = (status as Record<string, any>).message && typeof (status as Record<string, any>).message === 'object' ? textFromParts((status as Record<string, any>).message.parts) : '';
        if ((status as Record<string, any>).state === 'TASK_STATE_COMPLETED') {
            if (stream.answer.trim() === '' && messageText.trim() !== '') {
                stream.answer = messageText;
            }
            stream.phase = 'completed';
            stream.completed = true;
        } else if (messageText !== '') {
            stream.activity = messageText;
        }
        return;
    }
    if (unwrapped.frameKind !== 'artifactUpdate') {
        return;
    }
    const artifact = _requireObject(unwrapped.event.artifact, 'artifactUpdate.artifact');
    if ((artifact as Record<string, any>).name === RESPONSE_ARTIFACT_NAME) {
        const chunk = textFromParts((artifact as Record<string, any>).parts);
        if (chunk !== '') {
            stream.answer = `${stream.answer}${chunk}`;
            stream.phase = 'answering';
        }
    }
}

function _errorMessage(error: any) {
    if (error instanceof Error && typeof error.message === 'string' && error.message !== '') {
        return error.message;
    }
    return String(error);
}

function _publicSearchRuntimeUnavailable(detail: string) {
    return detail.includes('code_runner_python')
        || detail.includes('code_runner_node')
        || detail.includes('code_runner_go')
        || detail.includes('code_runner_csharp')
        || detail.includes('capability_gateway');
}

function _publicSearchErrorKind(detail: string, transportStatus: number, errorBody: unknown = null) {
    const message = _requireString(detail, 'public search error detail');
    if (message === 'search_quota_exhausted') {
        return 'search_quota_exhausted';
    }
    if (errorBody !== null && typeof errorBody === 'object' && !Array.isArray(errorBody)) {
        const errorCode = (errorBody as Record<string, any>).error_code;
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
    if (_publicSearchRuntimeUnavailable(message)) {
        return 'search_runtime_unavailable';
    }
    if (transportStatus === 502 || transportStatus === 503) {
        return 'search_service_unavailable';
    }
    return 'search_failed';
}

function _publicSearchErrorStatus(kind: string, transportStatus: number) {
    const errorKind = _requirePublicSearchErrorKind(kind, 'public search error kind');
    if (errorKind === 'search_timeout') {
        return 504;
    }
    if (errorKind === 'search_service_unavailable') {
        return 503;
    }
    if (errorKind === 'search_runtime_unavailable') {
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

function _isPublicSearchSessionFresh(session: Record<string, any>, mode: string) {
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

function _rememberPublicSearchSession(session: Record<string, any>) {
    publicSearchSessionByMode.set(session.branch_id, session);
}

async function _issuePublicSearchSession(mode: string, { force = false, consumeSearchQuota = true } = {}) {
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

async function _runPublicSearch({ payload, ctx, event }: { payload: unknown; ctx: Record<string, any>; event: PlatformEvent }) {
    if (!ctx || typeof ctx.dispatch !== 'function') {
        throw new Error('frontend/public_search_run: ctx.dispatch required');
    }
    if (!event || typeof event.id !== 'string' || event.id === '') {
        throw new Error('frontend/public_search_run: event.id required');
    }
    const request = _normalizeRunPayload(payload);
    const session = await _issuePublicSearchSession(request.mode, { force: true, consumeSearchQuota: true });
    const pendingFiles = takePendingPublicSearchRunFiles();
    const a2aFiles = pendingFiles.length > 0
        ? await uploadPublicSearchFilesForA2a(pendingFiles, {
            tokenType: session.token_type,
            token: session.token,
        })
        : [];
    const stream = _streamFromRunPayload(request);
    const publisher = _createStreamPublisher(ctx, event.id, _publishStream);
    publisher.publish(stream, true);

    let streamError: Error | null = null;
    const controller = new AbortController();
    const fold = _createStateFold();
    _replaceActiveSearchRun(request.run_id, controller);
    const onEvent = (frame: unknown) => {
        if (streamError !== null) {
            return;
        }
        try {
            const envelope = _requireObject(frame, 'A2A SSE frame');
            if (Object.prototype.hasOwnProperty.call(envelope, 'error')) {
                const rawError = (envelope as Record<string, any>).error;
                const message = rawError && typeof rawError === 'object' && typeof rawError.message === 'string'
                    ? rawError.message
                    : 'A2A stream error';
                throw new Error(message);
            }
            const result = _requireObject((envelope as Record<string, any>).result, 'A2A SSE result');
            const immediate = _applySearchFrame(stream, fold, result);
            publisher.publish(stream, immediate);
        } catch (error) {
            streamError = new Error(_errorMessage(error));
            controller.abort();
        }
    };

    try {
        await consumeA2aStream({
            url: a2aEndpointUrl({ baseUrl: _flowsBaseUrl(), embedId: session.embed_id }),
            body: buildSendMessageBody(
                buildUserMessage({ contextId: stream.context_id, text: request.query, files: a2aFiles }),
                { branchId: session.branch_id },
            ),
            headers: { Authorization: `${session.token_type} ${session.token}` },
            credentials: 'omit',
            signal: controller.signal,
        }, onEvent);
    } catch (error) {
        if (streamError !== null) {
            throw streamError;
        }
        throw error;
    } finally {
        publisher.cancel();
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

function _sourceDescribeMessage(request: Record<string, any>) {
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

async function _runPublicSearchSourceDescribe({ payload, ctx, event }: { payload: unknown; ctx: Record<string, any>; event: PlatformEvent }) {
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

    let streamError: Error | null = null;
    const controller = new AbortController();
    const onEvent = (frame: unknown) => {
        if (streamError !== null) {
            return;
        }
        try {
            const envelope = _requireObject(frame, 'A2A SSE frame');
            if (Object.prototype.hasOwnProperty.call(envelope, 'error')) {
                const rawError = (envelope as Record<string, any>).error;
                const message = rawError && typeof rawError === 'object' && typeof rawError.message === 'string'
                    ? rawError.message
                    : 'A2A stream error';
                throw new Error(message);
            }
            const result = _requireObject((envelope as Record<string, any>).result, 'A2A SSE result');
            _applySourceDescribeFrame(sourceStream, result);
            _publishSourceDescribeStream(ctx, event.id, sourceStream);
        } catch (error) {
            streamError = new Error(_errorMessage(error));
            controller.abort();
        }
    };

    try {
        await consumeA2aStream({
            url: a2aEndpointUrl({ baseUrl: _flowsBaseUrl(), embedId: session.embed_id }),
            body: buildSendMessageBody(
                buildUserMessage({ contextId: sourceStream.context_id, text: _sourceDescribeMessage(request) }),
                { branchId: session.branch_id },
            ),
            headers: { Authorization: `${session.token_type} ${session.token}` },
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
            const appended = _normalizeResults((payload as Record<string, any>).results);
            const hasMore = _requireBoolean((payload as Record<string, any>).has_more, 'serp_append.has_more');
            const totalCount = _requireNumber((payload as Record<string, any>).total_count, 'serp_append.total_count');
            const mergedResults = [..._normalizeResults((stream as Record<string, any>).results), ...appended];
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
            const stream = _normalizeStreamPayload((payload as Record<string, any>).stream);
            if (stream.run_id !== state.active_run_id) {
                return state;
            }
            return { ...state, stream };
        }
        if (event.type === events.SUCCEEDED) {
            const payload = _requireObject(event.payload, 'succeeded payload');
            const stream = _normalizeStreamPayload((payload as Record<string, any>).result);
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
        const mode = _requirePublicSearchSessionMode((body as Record<string, any>).mode, 'serp_more.mode');
        const serpCacheKey = _requireNonEmptyString((body as Record<string, any>).serp_cache_key, 'serp_more.serp_cache_key');
        const offset = _requireNumber((body as Record<string, any>).offset, 'serp_more.offset');
        const limit = _requireNumber((body as Record<string, any>).limit, 'serp_more.limit');
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
                results: (response as Record<string, any>).results,
                has_more: (response as Record<string, any>).has_more,
                total_count: (response as Record<string, any>).total_count,
            },
            { causation_id: event.id, source: 'http' },
        );
        return {
            results: _normalizeResults((response as Record<string, any>).results),
            has_more: _requireBoolean((response as Record<string, any>).has_more, 'serp_more.has_more'),
            total_count: _requireNumber((response as Record<string, any>).total_count, 'serp_more.total_count'),
        };
    },
});

export const publicSearchSerpClickOp = createAsyncOp({
    name: 'frontend/public_search_serp_click',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/public/search/serp/click' },
    request: async ({ payload }) => {
        const body = _requireObject(payload, 'serp_click payload');
        const mode = _requireSearchRunMode((body as Record<string, any>).mode, 'serp_click.mode');
        const query = _requireNonEmptyString((body as Record<string, any>).query, 'serp_click.query');
        const url = _requireNonEmptyString((body as Record<string, any>).url, 'serp_click.url');
        const position = _requireNumber((body as Record<string, any>).position, 'serp_click.position');
        const provider = _requireString((body as Record<string, any>).provider, 'serp_click.provider');
        const searchIndexId = _requireString((body as Record<string, any>).search_index_id, 'serp_click.search_index_id');
        const serpCacheKey = _requireString((body as Record<string, any>).serp_cache_key, 'serp_click.serp_cache_key');
        const session = await _issuePublicSearchSession(mode, { consumeSearchQuota: false });
        await httpRequest({
            method: 'POST',
            url: '/frontend/api/public/search/serp/click',
            credentials: 'same-origin',
            headers: { Authorization: `${session.token_type} ${session.token}` },
            body: {
                query,
                mode,
                url,
                position,
                provider,
                search_index_id: searchIndexId,
                serp_cache_key: serpCacheKey,
            },
        });
        return { logged: true };
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
            const sourceStream = _normalizeSourceDescribeStream((payload as Record<string, any>).source_stream);
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
            const sourceStream = _normalizeSourceDescribeStream((payload as Record<string, any>).result);
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
