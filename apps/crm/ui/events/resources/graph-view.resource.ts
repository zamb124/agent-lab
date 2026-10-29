/**
 * Workspace графа CRM — slice для canvas view (3d | mindmap), глубины, выбора, поиска.
 *
 * Панели overlay остаются в `crm/graph_ui`. Персист через crm-persist.effect.js,
 * ключ `crm.graph_view.state`.
 */

import { createSlice } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { CrmGraphViewSlice } from '../crm.types.js';

const DEFAULT_SEARCH_INPUT = Object.freeze({
    query: '',
    mode: 'hybrid',
    minScore: 0,
});

const DEFAULT_SELECTION = Object.freeze({
    nodeId: null,
    edgeId: null,
});

function eventRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

function viewModeOf(value: unknown): '3d' | 'mindmap' | null {
    return value === '3d' || value === 'mindmap' ? value : null;
}

function depthOf(value: unknown): number | null {
    if (typeof value !== 'number' || !Number.isInteger(value)) {
        return null;
    }
    return Math.min(5, Math.max(1, value));
}

function optionalId(value: unknown): string | null {
    if (typeof value !== 'string') {
        return null;
    }
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
}

function selectionFrom(value: unknown): { nodeId: string | null; edgeId: string | null } | null {
    if (!isPlainRecord(value)) {
        return null;
    }
    return {
        nodeId: optionalId(value.nodeId),
        edgeId: optionalId(value.edgeId),
    };
}

function searchFrom(value: unknown): { query: string; mode: string; minScore: number } | null {
    if (!isPlainRecord(value)) {
        return null;
    }
    const queryValue = value.query;
    const mode = value.mode;
    const minScoreValue = value.minScore;
    const query = typeof queryValue === 'string' ? queryValue : '';
    let searchMode = 'hybrid';
    if (mode === 'text' || mode === 'semantic' || mode === 'hybrid') {
        searchMode = mode;
    }
    let minScore = 0;
    if (typeof minScoreValue === 'number' && Number.isFinite(minScoreValue)) {
        minScore = minScoreValue;
    }
    return { query, mode: searchMode, minScore };
}

export const graphViewSlice = createSlice({
    name: 'crm/graph_view',
    extraInitial: {
        viewMode: 'mindmap',
        maxDepth: 4,
        displayDepth: 3,
        selection: DEFAULT_SELECTION,
        searchInput: DEFAULT_SEARCH_INPUT,
    },
    extraEvents: {
        HYDRATED: 'hydrated',
        VIEW_MODE_UPDATED: 'view_mode_updated',
        MAX_DEPTH_UPDATED: 'max_depth_updated',
        DISPLAY_DEPTH_UPDATED: 'display_depth_updated',
        SELECTION_UPDATED: 'selection_updated',
        SEARCH_INPUT_UPDATED: 'search_input_updated',
    },
    actions: {
        hydrate: 'hydrated',
        setViewMode: 'view_mode_updated',
        setMaxDepth: 'max_depth_updated',
        setDisplayDepth: 'display_depth_updated',
        setSelection: 'selection_updated',
        setSearchInput: 'search_input_updated',
    },
    extraReducer: (state: CrmGraphViewSlice, event) => {
        switch (event.type) {
            case 'crm/graph_view/hydrated': {
                const p = eventRecord(event.payload);
                if (p === null) {
                    return state;
                }
                let next = { ...state };
                const viewMode = viewModeOf(p.viewMode);
                if (viewMode !== null) {
                    next = { ...next, viewMode };
                }
                const maxDepth = depthOf(p.maxDepth);
                if (maxDepth !== null) {
                    next = { ...next, maxDepth };
                }
                const displayDepth = depthOf(p.displayDepth);
                if (displayDepth !== null) {
                    next = { ...next, displayDepth };
                }
                const selection = selectionFrom(p.selection);
                if (selection !== null) {
                    next = { ...next, selection: Object.freeze(selection) };
                }
                const searchInput = searchFrom(p.searchInput);
                if (searchInput !== null) {
                    next = { ...next, searchInput: Object.freeze(searchInput) };
                }
                return next;
            }
            case 'crm/graph_view/view_mode_updated': {
                const p = eventRecord(event.payload);
                const viewMode = p === null ? null : viewModeOf(p.viewMode);
                if (viewMode === null) {
                    return state;
                }
                return { ...state, viewMode };
            }
            case 'crm/graph_view/max_depth_updated': {
                const p = eventRecord(event.payload);
                const maxDepth = p === null ? null : depthOf(p.maxDepth);
                if (maxDepth === null) {
                    return state;
                }
                return { ...state, maxDepth };
            }
            case 'crm/graph_view/display_depth_updated': {
                const p = eventRecord(event.payload);
                const displayDepth = p === null ? null : depthOf(p.displayDepth);
                if (displayDepth === null) {
                    return state;
                }
                return { ...state, displayDepth };
            }
            case 'crm/graph_view/selection_updated': {
                const p = eventRecord(event.payload);
                const selection = p === null ? null : selectionFrom(p.selection);
                if (selection === null) {
                    return state;
                }
                return { ...state, selection: Object.freeze(selection) };
            }
            case 'crm/graph_view/search_input_updated': {
                const p = eventRecord(event.payload);
                const searchInput = p === null ? null : searchFrom(p.searchInput);
                if (searchInput === null) {
                    return state;
                }
                return { ...state, searchInput: Object.freeze(searchInput) };
            }
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/graph_view': typeof graphViewSlice;
    }
}
