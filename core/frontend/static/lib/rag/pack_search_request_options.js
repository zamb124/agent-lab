/**
 * Сборка retrieval-опций RAG в HTTP body (канон `RAGSearchOptions` / `SEARCH_REQUEST_OPTION_KEYS`).
 *
 * Используется RAG UI, Office catalog semantic search и любым клиентом,
 * который шлёт POST .../search с advanced retrieval overrides.
 */

/** @type {readonly string[]} */
export const SEARCH_REQUEST_OPTION_KEYS = Object.freeze([
    'channels',
    'rrf_k',
    'per_channel_top_k',
    'rerank',
    'rerank_max_candidates',
    'retrieval',
    'freshness_weight',
    'freshness_half_life_days',
]);

/**
 * @param {Record<string, unknown> | null | undefined} payload
 * @returns {Record<string, unknown>}
 */
export function packSearchRequestOptions(payload) {
    if (payload === null || payload === undefined) {
        return {};
    }
    /** @type {Record<string, unknown>} */
    const packed = {};
    for (const key of SEARCH_REQUEST_OPTION_KEYS) {
        if (Object.prototype.hasOwnProperty.call(payload, key) && payload[key] !== undefined && payload[key] !== null) {
            packed[key] = payload[key];
        }
    }
    return packed;
}

/**
 * @param {'platform' | 'hybrid' | 'semantic' | 'lexical'} mode
 * @returns {{ semantic: boolean, lexical: boolean } | null}
 */
export function channelsFromRetrievalMode(mode) {
    if (mode === 'hybrid') {
        return { semantic: true, lexical: true };
    }
    if (mode === 'lexical') {
        return { semantic: false, lexical: true };
    }
    if (mode === 'semantic') {
        return { semantic: true, lexical: false };
    }
    return null;
}

/**
 * Собирает advanced retrieval overrides из UI payload.
 *
 * @param {Record<string, unknown>} payload
 * @returns {Record<string, unknown>}
 */
export function packAdvancedRetrievalPayload(payload) {
    if (payload.usePlatformDefaults === true) {
        return {};
    }
    const mode = typeof payload.retrievalMode === 'string' ? payload.retrievalMode : 'platform';
    const channels = channelsFromRetrievalMode(
        /** @type {'platform' | 'hybrid' | 'semantic' | 'lexical'} */ (mode),
    );
    /** @type {Record<string, unknown>} */
    const merged = { ...packSearchRequestOptions(payload) };
    if (channels !== null) {
        merged.channels = channels;
    }
    return merged;
}

/**
 * Сборка retrieval panel state → HTTP/API payload.
 *
 * @param {Record<string, unknown>} panelValue
 * @returns {Record<string, unknown>}
 */
export function buildAdvancedRetrievalPayloadFromPanel(panelValue) {
    if (!panelValue || typeof panelValue !== 'object') {
        return {};
    }
    /** @type {Record<string, unknown>} */
    const payload = {
        usePlatformDefaults: panelValue.usePlatformDefaults === true,
        retrievalMode: typeof panelValue.retrievalMode === 'string' ? panelValue.retrievalMode : 'platform',
    };
    const rrfK = _optionalPositiveInt(panelValue.rrfK ?? panelValue.rrf_k);
    if (rrfK !== undefined) {
        payload.rrf_k = rrfK;
    }
    const perChannelTopK = _optionalPositiveInt(panelValue.perChannelTopK ?? panelValue.per_channel_top_k);
    if (perChannelTopK !== undefined) {
        payload.per_channel_top_k = perChannelTopK;
    }
    const rerankRaw = panelValue.rerank;
    if (rerankRaw === true || rerankRaw === 'true') {
        payload.rerank = true;
    } else if (rerankRaw === false || rerankRaw === 'false') {
        payload.rerank = false;
    }
    const rerankMax = _optionalPositiveInt(
        panelValue.rerankMaxCandidates ?? panelValue.rerank_max_candidates,
    );
    if (rerankMax !== undefined) {
        payload.rerank_max_candidates = rerankMax;
    }
    const freshnessWeight = _optionalUnitFloat(panelValue.freshnessWeight ?? panelValue.freshness_weight);
    if (freshnessWeight !== undefined) {
        payload.freshness_weight = freshnessWeight;
    }
    const freshnessHalfLife = _optionalUnitFloat(
        panelValue.freshnessHalfLifeDays ?? panelValue.freshness_half_life_days,
    );
    if (freshnessHalfLife !== undefined) {
        payload.freshness_half_life_days = freshnessHalfLife;
    }
    return packAdvancedRetrievalPayload(payload);
}

/**
 * Нормализует API search_options в panel state.
 *
 * @param {Record<string, unknown> | null | undefined} searchOptions
 * @returns {Record<string, unknown>}
 */
export function panelValueFromSearchOptions(searchOptions) {
    if (!searchOptions || typeof searchOptions !== 'object') {
        return defaultRetrievalPanelValue();
    }
    const channels = searchOptions.channels;
    let retrievalMode = 'platform';
    if (channels && typeof channels === 'object') {
        const semantic = channels.semantic === true;
        const lexical = channels.lexical === true;
        if (semantic && lexical) {
            retrievalMode = 'hybrid';
        } else if (lexical) {
            retrievalMode = 'lexical';
        } else if (semantic) {
            retrievalMode = 'semantic';
        }
    }
    const hasOverrides = Object.keys(packSearchRequestOptions(searchOptions)).length > 0
        || retrievalMode !== 'platform';
    return {
        usePlatformDefaults: !hasOverrides,
        retrievalMode,
        rrfK: _stringOrEmpty(searchOptions.rrf_k),
        perChannelTopK: _stringOrEmpty(searchOptions.per_channel_top_k),
        rerank: typeof searchOptions.rerank === 'boolean' ? String(searchOptions.rerank) : '',
        rerankMaxCandidates: _stringOrEmpty(searchOptions.rerank_max_candidates),
        freshnessWeight: _stringOrEmpty(searchOptions.freshness_weight),
        freshnessHalfLifeDays: _stringOrEmpty(searchOptions.freshness_half_life_days),
    };
}

/** @returns {Record<string, unknown>} */
export function defaultRetrievalPanelValue() {
    return {
        usePlatformDefaults: true,
        retrievalMode: 'platform',
        rrfK: '',
        perChannelTopK: '',
        rerank: '',
        rerankMaxCandidates: '',
        freshnessWeight: '',
        freshnessHalfLifeDays: '',
    };
}

/**
 * @param {unknown} raw
 * @returns {string}
 */
function _stringOrEmpty(raw) {
    if (typeof raw === 'number' && Number.isFinite(raw)) {
        return String(raw);
    }
    if (typeof raw === 'string' && raw.length > 0) {
        return raw;
    }
    return '';
}

/**
 * @param {unknown} raw
 * @returns {number | undefined}
 */
function _optionalPositiveInt(raw) {
    if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
        return Math.round(raw);
    }
    if (typeof raw !== 'string' || raw.trim().length === 0) {
        return undefined;
    }
    const parsed = parseInt(raw.trim(), 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error('pack_search_request_options: invalid positive integer');
    }
    return parsed;
}

/**
 * @param {unknown} raw
 * @returns {number | undefined}
 */
function _optionalUnitFloat(raw) {
    if (typeof raw === 'number' && Number.isFinite(raw)) {
        return raw;
    }
    if (typeof raw !== 'string' || raw.trim().length === 0) {
        return undefined;
    }
    const parsed = parseFloat(raw.trim());
    if (!Number.isFinite(parsed)) {
        throw new Error('pack_search_request_options: invalid float');
    }
    return parsed;
}
