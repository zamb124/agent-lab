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
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

function hasOwnKey<T extends object>(catalog: T, key: string): key is Extract<keyof T, string> {
    return Object.prototype.hasOwnProperty.call(catalog, key);
}

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

function graphPanelsValue(getState: () => unknown) {
    const state = getState();
    const slice = isPlainRecord(state) ? state.crmGraphUi : null;
    if (!isPlainRecord(slice) || !isPlainRecord(slice.panels)) {
        return { key: KEYS.graphPanels, value: null };
    }
    return { key: KEYS.graphPanels, value: { ...slice.panels } };
}

function graphViewValue(getState: () => unknown) {
    const state = getState();
    const slice = isPlainRecord(state) ? state.crmGraphView : null;
    if (!isPlainRecord(slice)) {
        return { key: KEYS.graphViewState, value: null };
    }
    const searchInput = isPlainRecord(slice.searchInput) ? { ...slice.searchInput } : {};
    return {
        key: KEYS.graphViewState,
        value: {
            viewMode: slice.viewMode,
            maxDepth: slice.maxDepth,
            displayDepth: slice.displayDepth,
            searchInput,
        },
    };
}

const PERSIST_TRIGGERS = Object.freeze({
    'crm/graph_ui/panels_updated': (_event: PlatformEvent, getState: () => unknown) => graphPanelsValue(getState),
    'crm/graph_view/view_mode_updated': (_event: PlatformEvent, getState: () => unknown) => graphViewValue(getState),
    'crm/graph_view/max_depth_updated': (_event: PlatformEvent, getState: () => unknown) => graphViewValue(getState),
    'crm/graph_view/display_depth_updated': (_event: PlatformEvent, getState: () => unknown) => graphViewValue(getState),
    'crm/graph_view/search_input_updated': (_event: PlatformEvent, getState: () => unknown) => graphViewValue(getState),
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
            if (!isPlainRecord(event.payload)) return;
            const key = event.payload.key;
            const value = event.payload.value;
            if (value === null || value === undefined) return;
            if (typeof key !== 'string' || !hasOwnKey(HYDRATION_ACTIONS, key)) return;
            const factory = HYDRATION_ACTIONS[key];
            if (factory === undefined) return;
            const action = factory(value);
            if (action && typeof action.type === 'string') {
                ctx.dispatch(action.type, action.payload, { source: 'storage' });
            }
            return;
        }

        if (!hasOwnKey(PERSIST_TRIGGERS, event.type)) return;
        const { key, value } = PERSIST_TRIGGERS[event.type](event, ctx.getState);
        ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, { key, value }, { source: 'system' });
    };
}
