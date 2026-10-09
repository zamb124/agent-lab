/**
 * Эффект persist CRM — связка локальных UI-slice с core storage-effect.
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
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

const KEYS = Object.freeze({
    graphPanels: platformStorageKey('crm', 'graph_ui.panels'),
    graphViewState: platformStorageKey('crm', 'graph_view.state'),
});

const HYDRATION_ACTIONS = Object.freeze({
    [KEYS.graphPanels]: (value: unknown) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'crm/graph_ui/panels_hydrated', payload: { panels: value } };
    },
    [KEYS.graphViewState]: (value: unknown) => {
        if (!value || typeof value !== 'object') return null;
        return { type: 'crm/graph_view/hydrated', payload: value };
    },
});

const PERSIST_TRIGGERS = Object.freeze({
    'crm/graph_ui/panels_updated': (event: PlatformEvent, getState: () => Record<string, any>) => {
        const slice = getState().crmGraphUi;
        if (!slice || !slice.panels || typeof slice.panels !== 'object') {
            return { key: KEYS.graphPanels, value: null };
        }
        return { key: KEYS.graphPanels, value: { ...slice.panels } };
    },
    'crm/graph_view/view_mode_updated': (event: PlatformEvent, getState: () => Record<string, any>) => {
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
    'crm/graph_view/max_depth_updated': (event: PlatformEvent, getState: () => Record<string, any>) => {
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
    'crm/graph_view/display_depth_updated': (event: PlatformEvent, getState: () => Record<string, any>) => {
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
    'crm/graph_view/search_input_updated': (event: PlatformEvent, getState: () => Record<string, any>) => {
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

    function dispatchBootstrap(ctx: EffectCtx) {
        if (bootstrapDispatched) return;
        bootstrapDispatched = true;
        for (const key of Object.values(KEYS)) {
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key }, { source: 'system' });
        }
    }

    return async function crmPersistEffect(event: PlatformEvent, ctx: EffectCtx) {
        if (event.type === CoreEvents.AUTH_USER_LOADED || event.type === CoreEvents.AUTH_LOGIN_SUCCEEDED) {
            dispatchBootstrap(ctx);
            return;
        }

        if (event.type === CoreEvents.STORAGE_LOADED) {
            if (!event.payload || typeof event.payload !== 'object') return;
            const { key, value } = event.payload as { key?: string; value?: unknown };
            if (value === null || value === undefined) return;
            const factory = HYDRATION_ACTIONS[key as keyof typeof HYDRATION_ACTIONS];
            if (typeof factory !== 'function') return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        const persistFn = (PERSIST_TRIGGERS as Record<string, ((event: PlatformEvent, getState: () => Record<string, any>) => { key: string; value: unknown }) | undefined>)[event.type];
        if (persistFn) {
            const { key, value } = persistFn(event, ctx.getState as () => Record<string, any>);
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
        }
    };
}
