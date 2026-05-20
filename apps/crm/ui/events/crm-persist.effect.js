/**
 * CRM persist effect — связка локальных UI-slice с core storage-effect.
 *
 * На bootstrap (AUTH_USER_LOADED / AUTH_LOGIN_SUCCEEDED) диспатчит
 * `STORAGE_LOAD_REQUESTED` для всех ключей CRM. На `STORAGE_LOADED` от storage
 * effect'а — гидратирует соответствующий slice через action.
 *
 * На действия фабрик (`crm/graph_ui/panels_updated`, `crm/graph_view/*_updated`) —
 * диспатчит `STORAGE_PERSIST_REQUESTED`
 * с актуальным значением из slice.
 *
 * Ключи в localStorage:
 *   crm.graph_ui.panels        — { search, timeline, legend, meta }
 *   crm.graph_view.state      — { viewMode, maxDepth, displayDepth, searchInput }
 * Никакого резерва: если ключа нет — гидратация не происходит, slice остаётся
 * в `extraInitial`.
 */

import { CoreEvents } from '@platform/lib/events/index.js';

const KEYS = Object.freeze({
    graphPanels: 'crm.graph_ui.panels',
    graphViewState: 'crm.graph_view.state',
});

const HYDRATION_ACTIONS = Object.freeze({
    [KEYS.graphPanels]: (value) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'crm/graph_ui/panels_hydrated', payload: { panels: value } };
    },
    [KEYS.graphViewState]: (value) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'crm/graph_view/hydrated', payload: value };
    },
});

const PERSIST_TRIGGERS = Object.freeze({
    'crm/graph_ui/panels_updated': (event, getState) => {
        const slice = getState().crmGraphUi;
        if (!slice || !slice.panels || typeof slice.panels !== 'object') {
            return { key: KEYS.graphPanels, value: null };
        }
        return { key: KEYS.graphPanels, value: { ...slice.panels } };
    },
    'crm/graph_view/view_mode_updated': (event, getState) => {
        const slice = getState().crmGraphView;
        if (!slice || typeof slice !== 'object') {
            return { key: KEYS.graphViewState, value: null };
        }
        return {
            key: KEYS.graphViewState,
            value: {
                viewMode: slice.viewMode,
                maxDepth: slice.maxDepth,
                displayDepth: slice.displayDepth,
                searchInput: { ...slice.searchInput },
            },
        };
    },
    'crm/graph_view/max_depth_updated': (event, getState) => {
        const slice = getState().crmGraphView;
        if (!slice || typeof slice !== 'object') {
            return { key: KEYS.graphViewState, value: null };
        }
        return {
            key: KEYS.graphViewState,
            value: {
                viewMode: slice.viewMode,
                maxDepth: slice.maxDepth,
                displayDepth: slice.displayDepth,
                searchInput: { ...slice.searchInput },
            },
        };
    },
    'crm/graph_view/display_depth_updated': (event, getState) => {
        const slice = getState().crmGraphView;
        if (!slice || typeof slice !== 'object') {
            return { key: KEYS.graphViewState, value: null };
        }
        return {
            key: KEYS.graphViewState,
            value: {
                viewMode: slice.viewMode,
                maxDepth: slice.maxDepth,
                displayDepth: slice.displayDepth,
                searchInput: { ...slice.searchInput },
            },
        };
    },
    'crm/graph_view/search_input_updated': (event, getState) => {
        const slice = getState().crmGraphView;
        if (!slice || typeof slice !== 'object') {
            return { key: KEYS.graphViewState, value: null };
        }
        return {
            key: KEYS.graphViewState,
            value: {
                viewMode: slice.viewMode,
                maxDepth: slice.maxDepth,
                displayDepth: slice.displayDepth,
                searchInput: { ...slice.searchInput },
            },
        };
    },
});

export function createCrmPersistEffect() {
    let bootstrapDispatched = false;

    function dispatchBootstrap(ctx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        for (const key of Object.values(KEYS)) {
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key }, { source: 'system' });
        }
    }

    return async function crmPersistEffect(event, ctx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            if (!event.payload || typeof event.payload !== 'object') return;
            const { key, value } = event.payload;
            if (value === null || value === undefined) return;
            const factory = HYDRATION_ACTIONS[key];
            if (typeof factory !== 'function') return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        const persistFn = PERSIST_TRIGGERS[event.type];
        if (persistFn) {
            const { key, value } = persistFn(event, ctx.getState);
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
        }
    };
}
