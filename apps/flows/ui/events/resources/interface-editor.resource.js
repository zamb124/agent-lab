import { createSlice } from '@platform/lib/events/index.js';

function requirePayloadObject(event) {
    const payload = event.payload;
    if (payload === undefined || payload === null) {
        return {};
    }
    if (typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error(`flows/interface_editor: payload must be object for ${event.type}`);
    }
    return payload;
}

function requireString(payload, key, eventType) {
    const value = payload[key];
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`flows/interface_editor: ${key} required for ${eventType}`);
    }
    return value;
}

function requireNumber(payload, key, eventType, fallback) {
    if (!(key in payload)) {
        if (fallback === undefined) {
            throw new Error(`flows/interface_editor: ${key} required for ${eventType}`);
        }
        return fallback;
    }
    const value = Number(payload[key]);
    if (!Number.isFinite(value)) {
        throw new Error(`flows/interface_editor: ${key} must be finite number for ${eventType}`);
    }
    return value;
}

const HISTORY_LIMIT = 80;
const HISTORY_COALESCE_MS = 1200;

export const interfaceEditorSlice = createSlice({
    name: 'flows/interface_editor',
    extraInitial: {
        selectedComponentId: 'root',
        selectedComponentIds: Object.freeze(['root']),
        hoveredComponentId: '',
        lockedComponentIds: Object.freeze([]),
        selectedPageId: 'main',
        targetSurface: 'page',
        viewportProfile: 'desktop-wide',
        customWidth: 1440,
        customHeight: 900,
        zoom: 1,
        editBand: 'wide',
        gridVisible: false,
        baselineVisible: false,
        rulersVisible: false,
        guidesVisible: true,
        guides: Object.freeze([]),
        snapEnabled: true,
        dataFlowVisible: false,
        previewMode: false,
        runMode: false,
        openPanel: 'properties',
        lastMeasuredRevision: 0,
        history: Object.freeze({ past: Object.freeze([]), future: Object.freeze([]) }),
    },
    actions: {
        selectComponent: 'component_selected',
        selectComponents: 'components_selected',
        hoverComponent: 'component_hovered',
        toggleLock: 'lock_toggled',
        selectPage: 'page_selected',
        setTarget: 'target_set',
        setViewport: 'viewport_set',
        setZoom: 'zoom_set',
        setEditBand: 'edit_band_set',
        toggleGrid: 'grid_toggled',
        toggleBaseline: 'baseline_toggled',
        toggleRulers: 'rulers_toggled',
        toggleGuides: 'guides_toggled',
        setGuides: 'guides_set',
        toggleSnap: 'snap_toggled',
        toggleDataFlow: 'data_flow_toggled',
        setPreview: 'preview_set',
        setRunMode: 'run_mode_set',
        setPanel: 'panel_set',
        setMeasuredRevision: 'measured_revision_set',
        historyPush: 'history_pushed',
        historyUndo: 'history_undone',
        historyRedo: 'history_redone',
        historyClear: 'history_cleared',
        reset: 'reset',
    },
    extraReducer: (state, event) => {
        const payload = requirePayloadObject(event);
        if (event.type === 'flows/interface_editor/component_selected') {
            const componentId = requireString(payload, 'componentId', event.type);
            const additive = payload.additive === true;
            const current = Array.isArray(state.selectedComponentIds)
                ? state.selectedComponentIds
                : [state.selectedComponentId];
            let selectedComponentIds;
            if (!additive) {
                selectedComponentIds = [componentId];
            } else if (current.includes(componentId)) {
                selectedComponentIds = current.filter((id) => id !== componentId);
                if (!selectedComponentIds.length) selectedComponentIds = [componentId];
            } else {
                selectedComponentIds = [...current, componentId];
            }
            return {
                ...state,
                selectedComponentId: selectedComponentIds[selectedComponentIds.length - 1],
                selectedComponentIds: Object.freeze(selectedComponentIds),
            };
        }
        if (event.type === 'flows/interface_editor/components_selected') {
            const ids = payload.componentIds;
            if (!Array.isArray(ids) || !ids.length) {
                throw new Error(`flows/interface_editor: componentIds required for ${event.type}`);
            }
            return {
                ...state,
                selectedComponentId: String(ids[ids.length - 1]),
                selectedComponentIds: Object.freeze(ids.map(String)),
            };
        }
        if (event.type === 'flows/interface_editor/component_hovered') {
            const hovered = typeof payload.componentId === 'string' ? payload.componentId : '';
            return { ...state, hoveredComponentId: hovered };
        }
        if (event.type === 'flows/interface_editor/lock_toggled') {
            const componentId = requireString(payload, 'componentId', event.type);
            const locked = Array.isArray(state.lockedComponentIds) ? state.lockedComponentIds : [];
            return {
                ...state,
                lockedComponentIds: Object.freeze(locked.includes(componentId)
                    ? locked.filter((id) => id !== componentId)
                    : [...locked, componentId]),
            };
        }
        if (event.type === 'flows/interface_editor/page_selected') {
            return {
                ...state,
                selectedPageId: requireString(payload, 'pageId', event.type),
                selectedComponentId: 'root',
                selectedComponentIds: Object.freeze(['root']),
            };
        }
        if (event.type === 'flows/interface_editor/guides_set') {
            const guides = payload.guides;
            if (!Array.isArray(guides)) {
                throw new Error(`flows/interface_editor: guides array required for ${event.type}`);
            }
            for (const guide of guides) {
                if (!guide || (guide.axis !== 'x' && guide.axis !== 'y') || !Number.isFinite(guide.offset)) {
                    throw new Error(`flows/interface_editor: invalid guide for ${event.type}`);
                }
            }
            return {
                ...state,
                guides: Object.freeze(guides.map((guide) => Object.freeze({
                    axis: guide.axis,
                    offset: Math.round(guide.offset),
                }))),
            };
        }
        if (event.type === 'flows/interface_editor/edit_band_set') {
            const band = requireString(payload, 'band', event.type);
            if (!['compact', 'medium', 'wide'].includes(band)) {
                throw new Error(`flows/interface_editor: unknown band ${band}`);
            }
            return { ...state, editBand: band };
        }
        if (event.type === 'flows/interface_editor/history_pushed') {
            if (!('config' in payload)) {
                throw new Error(`flows/interface_editor: config required for ${event.type}`);
            }
            const label = requireString(payload, 'label', event.type);
            const coalesceKey = typeof payload.coalesceKey === 'string' ? payload.coalesceKey : '';
            const now = Date.now();
            const past = state.history.past;
            const top = past.length ? past[past.length - 1] : null;
            if (coalesceKey !== ''
                && top
                && top.coalesceKey === coalesceKey
                && now - top.at < HISTORY_COALESCE_MS) {
                // Same gesture continues: keep the original "before" snapshot,
                // refresh the coalesce window, drop redo branch.
                return {
                    ...state,
                    history: Object.freeze({
                        past: Object.freeze([...past.slice(0, -1), { ...top, at: now }]),
                        future: Object.freeze([]),
                    }),
                };
            }
            const entry = Object.freeze({
                label,
                coalesceKey,
                at: now,
                config: payload.config,
            });
            return {
                ...state,
                history: Object.freeze({
                    past: Object.freeze([...past, entry].slice(-HISTORY_LIMIT)),
                    future: Object.freeze([]),
                }),
            };
        }
        if (event.type === 'flows/interface_editor/history_undone') {
            if (!('config' in payload)) {
                throw new Error(`flows/interface_editor: config required for ${event.type}`);
            }
            const past = state.history.past;
            if (!past.length) return state;
            const entry = Object.freeze({
                label: past[past.length - 1].label,
                coalesceKey: '',
                at: Date.now(),
                config: payload.config,
            });
            return {
                ...state,
                history: Object.freeze({
                    past: Object.freeze(past.slice(0, -1)),
                    future: Object.freeze([entry, ...state.history.future].slice(0, HISTORY_LIMIT)),
                }),
            };
        }
        if (event.type === 'flows/interface_editor/history_redone') {
            if (!('config' in payload)) {
                throw new Error(`flows/interface_editor: config required for ${event.type}`);
            }
            const future = state.history.future;
            if (!future.length) return state;
            const entry = Object.freeze({
                label: future[0].label,
                coalesceKey: '',
                at: Date.now(),
                config: payload.config,
            });
            return {
                ...state,
                history: Object.freeze({
                    past: Object.freeze([...state.history.past, entry].slice(-HISTORY_LIMIT)),
                    future: Object.freeze(future.slice(1)),
                }),
            };
        }
        if (event.type === 'flows/interface_editor/history_cleared') {
            return {
                ...state,
                history: Object.freeze({ past: Object.freeze([]), future: Object.freeze([]) }),
            };
        }
        if (event.type === 'flows/interface_editor/target_set') {
            return {
                ...state,
                targetSurface: requireString(payload, 'target', event.type),
            };
        }
        if (event.type === 'flows/interface_editor/viewport_set') {
            return {
                ...state,
                viewportProfile: requireString(payload, 'profile', event.type),
                customWidth: requireNumber(payload, 'width', event.type, state.customWidth),
                customHeight: requireNumber(payload, 'height', event.type, state.customHeight),
            };
        }
        if (event.type === 'flows/interface_editor/zoom_set') {
            if (payload.zoom === 'fit') {
                return { ...state, zoom: 'fit' };
            }
            const zoom = requireNumber(payload, 'zoom', event.type);
            return {
                ...state,
                zoom: Math.min(2, Math.max(0.5, zoom)),
            };
        }
        if (event.type === 'flows/interface_editor/grid_toggled') {
            return { ...state, gridVisible: !state.gridVisible };
        }
        if (event.type === 'flows/interface_editor/baseline_toggled') {
            return { ...state, baselineVisible: !state.baselineVisible };
        }
        if (event.type === 'flows/interface_editor/rulers_toggled') {
            return { ...state, rulersVisible: !state.rulersVisible };
        }
        if (event.type === 'flows/interface_editor/guides_toggled') {
            return { ...state, guidesVisible: !state.guidesVisible };
        }
        if (event.type === 'flows/interface_editor/snap_toggled') {
            return { ...state, snapEnabled: !state.snapEnabled };
        }
        if (event.type === 'flows/interface_editor/data_flow_toggled') {
            return { ...state, dataFlowVisible: !state.dataFlowVisible };
        }
        if (event.type === 'flows/interface_editor/preview_set') {
            if (!('value' in payload)) {
                throw new Error(`flows/interface_editor: value required for ${event.type}`);
            }
            return { ...state, previewMode: Boolean(payload.value), runMode: false };
        }
        if (event.type === 'flows/interface_editor/run_mode_set') {
            if (!('value' in payload)) {
                throw new Error(`flows/interface_editor: value required for ${event.type}`);
            }
            return { ...state, runMode: Boolean(payload.value), previewMode: false };
        }
        if (event.type === 'flows/interface_editor/panel_set') {
            return {
                ...state,
                openPanel: requireString(payload, 'panel', event.type),
            };
        }
        if (event.type === 'flows/interface_editor/measured_revision_set') {
            return {
                ...state,
                lastMeasuredRevision: requireNumber(payload, 'revision', event.type),
            };
        }
        if (event.type === 'flows/interface_editor/reset') {
            return {
                ...state,
                selectedComponentId: 'root',
                selectedComponentIds: Object.freeze(['root']),
                hoveredComponentId: '',
                selectedPageId: 'main',
                previewMode: false,
                runMode: false,
                history: Object.freeze({ past: Object.freeze([]), future: Object.freeze([]) }),
            };
        }
        return state;
    },
});
