/**
 * Workspace графа CRM — slice для canvas view (3d | mindmap), глубины, выбора, поиска.
 *
 * Панели overlay остаются в `crm/graph_ui`. Персист через crm-persist.effect.js,
 * ключ `crm.graph_view.state`.
 */

import { createSlice } from '@platform/lib/events/index.js';

const DEFAULT_SEARCH_INPUT = Object.freeze({
    query: '',
    mode: 'hybrid',
    minScore: 0,
});

const DEFAULT_SELECTION = Object.freeze({
    nodeId: null,
    edgeId: null,
});

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
    extraReducer: (state, event) => {
        switch (event.type) {
            case 'crm/graph_view/hydrated': {
                const p = event.payload;
                if (!p || typeof p !== 'object') {
                    return state;
                }
                let next = { ...state };
                if (p.viewMode === '3d' || p.viewMode === 'mindmap') {
                    next = { ...next, viewMode: p.viewMode };
                }
                if (typeof p.maxDepth === 'number' && Number.isInteger(p.maxDepth)) {
                    const d = Math.min(5, Math.max(1, p.maxDepth));
                    next = { ...next, maxDepth: d };
                }
                if (typeof p.displayDepth === 'number' && Number.isInteger(p.displayDepth)) {
                    const dd = Math.min(5, Math.max(1, p.displayDepth));
                    next = { ...next, displayDepth: dd };
                }
                if (p.selection && typeof p.selection === 'object') {
                    const nodeIdRaw = p.selection.nodeId;
                    const edgeIdRaw = p.selection.edgeId;
                    const nodeId =
                        nodeIdRaw === null || nodeIdRaw === undefined
                            ? null
                            : typeof nodeIdRaw === 'string'
                              ? nodeIdRaw.trim().length > 0
                                  ? nodeIdRaw.trim()
                                  : null
                              : null;
                    const edgeId =
                        edgeIdRaw === null || edgeIdRaw === undefined
                            ? null
                            : typeof edgeIdRaw === 'string'
                              ? edgeIdRaw.trim().length > 0
                                  ? edgeIdRaw.trim()
                                  : null
                              : null;
                    next = {
                        ...next,
                        selection: Object.freeze({ nodeId, edgeId }),
                    };
                }
                if (p.searchInput && typeof p.searchInput === 'object') {
                    const q = p.searchInput.query;
                    const mode = p.searchInput.mode;
                    const ms = p.searchInput.minScore;
                    const query = typeof q === 'string' ? q : '';
                    let searchMode = 'hybrid';
                    if (mode === 'text' || mode === 'semantic' || mode === 'hybrid') {
                        searchMode = mode;
                    }
                    let minScore = 0;
                    if (typeof ms === 'number' && Number.isFinite(ms)) {
                        minScore = ms;
                    }
                    next = {
                        ...next,
                        searchInput: Object.freeze({
                            query,
                            mode: searchMode,
                            minScore,
                        }),
                    };
                }
                return next;
            }
            case 'crm/graph_view/view_mode_updated': {
                const p = event.payload;
                if (!p || (p.viewMode !== '3d' && p.viewMode !== 'mindmap')) {
                    return state;
                }
                return { ...state, viewMode: p.viewMode };
            }
            case 'crm/graph_view/max_depth_updated': {
                const p = event.payload;
                if (!p || typeof p.maxDepth !== 'number' || !Number.isInteger(p.maxDepth)) {
                    return state;
                }
                const d = Math.min(5, Math.max(1, p.maxDepth));
                return { ...state, maxDepth: d };
            }
            case 'crm/graph_view/display_depth_updated': {
                const p = event.payload;
                if (!p || typeof p.displayDepth !== 'number' || !Number.isInteger(p.displayDepth)) {
                    return state;
                }
                const dd = Math.min(5, Math.max(1, p.displayDepth));
                return { ...state, displayDepth: dd };
            }
            case 'crm/graph_view/selection_updated': {
                const p = event.payload;
                if (!p || !p.selection || typeof p.selection !== 'object') {
                    return state;
                }
                const nodeIdRaw = p.selection.nodeId;
                const edgeIdRaw = p.selection.edgeId;
                const nodeId =
                    nodeIdRaw === null || nodeIdRaw === undefined
                        ? null
                        : typeof nodeIdRaw === 'string'
                          ? nodeIdRaw.trim().length > 0
                              ? nodeIdRaw.trim()
                              : null
                          : null;
                const edgeId =
                    edgeIdRaw === null || edgeIdRaw === undefined
                        ? null
                        : typeof edgeIdRaw === 'string'
                          ? edgeIdRaw.trim().length > 0
                              ? edgeIdRaw.trim()
                              : null
                          : null;
                return {
                    ...state,
                    selection: Object.freeze({ nodeId, edgeId }),
                };
            }
            case 'crm/graph_view/search_input_updated': {
                const p = event.payload;
                if (!p || !p.searchInput || typeof p.searchInput !== 'object') {
                    return state;
                }
                const q = p.searchInput.query;
                const mode = p.searchInput.mode;
                const ms = p.searchInput.minScore;
                const query = typeof q === 'string' ? q : '';
                let searchMode = 'hybrid';
                if (mode === 'text' || mode === 'semantic' || mode === 'hybrid') {
                    searchMode = mode;
                }
                let minScore = 0;
                if (typeof ms === 'number' && Number.isFinite(ms)) {
                    minScore = ms;
                }
                return {
                    ...state,
                    searchInput: Object.freeze({
                        query,
                        mode: searchMode,
                        minScore,
                    }),
                };
            }
            default:
                return state;
        }
    },
});
