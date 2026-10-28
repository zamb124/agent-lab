/**
 * Сборка retrieval-опций RAG в HTTP body (канон `RAGSearchOptions` / `SEARCH_REQUEST_OPTION_KEYS`).
 *
 * Используется RAG UI, Office catalog semantic search и любым клиентом,
 * который шлёт POST .../search с advanced retrieval overrides.
 */

import { isPlainRecord } from '../events/payload.js';

export const SEARCH_REQUEST_OPTION_KEYS: readonly string[] = Object.freeze([
    'channels',
    'rrf_k',
    'per_channel_top_k',
    'rerank',
    'rerank_max_candidates',
    'retrieval',
    'freshness_weight',
    'freshness_half_life_days',
]);

export function packSearchRequestOptions(payload: Record<string, unknown> | null | undefined): Record<string, unknown> {
    if (payload === null || payload === undefined) {
        return {};
    }
    const packed: Record<string, unknown> = {};
    for (const key of SEARCH_REQUEST_OPTION_KEYS) {
        if (Object.prototype.hasOwnProperty.call(payload, key) && payload[key] !== undefined && payload[key] !== null) {
            packed[key] = payload[key];
        }
    }
    return packed;
}

export type RetrievalMode = 'platform' | 'hybrid' | 'semantic' | 'lexical';

function retrievalModeOf(value: unknown): RetrievalMode {
    if (value === undefined || value === null) return 'platform';
    if (value === 'platform' || value === 'hybrid' || value === 'semantic' || value === 'lexical') return value;
    throw new Error(`pack_search_request_options: unsupported retrievalMode ${JSON.stringify(value)}`);
}

interface ChannelFlags {
    semantic?: boolean;
    lexical?: boolean;
}

function isChannelFlags(value: unknown): value is ChannelFlags {
    if (!isPlainRecord(value)) return false;
    if (value.semantic !== undefined && typeof value.semantic !== 'boolean') return false;
    if (value.lexical !== undefined && typeof value.lexical !== 'boolean') return false;
    return true;
}

export function channelsFromRetrievalMode(mode: RetrievalMode): { semantic: boolean; lexical: boolean } | null {
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

export function packAdvancedRetrievalPayload(payload: Record<string, unknown>): Record<string, unknown> {
    if (payload.usePlatformDefaults === true) {
        return {};
    }
    const channels = channelsFromRetrievalMode(retrievalModeOf(payload.retrievalMode));
    const merged: Record<string, unknown> = { ...packSearchRequestOptions(payload) };
    if (channels !== null) {
        merged.channels = channels;
    }
    return merged;
}

export function buildAdvancedRetrievalPayloadFromPanel(panelValue: Record<string, unknown>): Record<string, unknown> {
    if (!panelValue || typeof panelValue !== 'object') {
        return {};
    }
    const payload: Record<string, unknown> = {
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

export function panelValueFromSearchOptions(searchOptions: Record<string, unknown> | null | undefined): Record<string, unknown> {
    if (!searchOptions || typeof searchOptions !== 'object') {
        return defaultRetrievalPanelValue();
    }
    const rawChannels = searchOptions.channels;
    if (rawChannels !== undefined && rawChannels !== null && !isChannelFlags(rawChannels)) {
        throw new Error('pack_search_request_options: channels must be an object');
    }
    const channels = rawChannels === undefined || rawChannels === null ? null : rawChannels;
    let retrievalMode = 'platform';
    if (channels !== null) {
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

export function defaultRetrievalPanelValue(): Record<string, unknown> {
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

function _stringOrEmpty(raw: unknown): string {
    if (typeof raw === 'number' && Number.isFinite(raw)) {
        return String(raw);
    }
    if (typeof raw === 'string' && raw.length > 0) {
        return raw;
    }
    return '';
}

function _optionalPositiveInt(raw: unknown): number | undefined {
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

function _optionalUnitFloat(raw: unknown): number | undefined {
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
