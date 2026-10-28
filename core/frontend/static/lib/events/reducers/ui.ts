/**
 * Слайс UI — sidebar (mobile/collapse), namespace selection, documents reload счётчик.
 *
 * state.ui:
 *   sidebar:   { mobileOpen: boolean, collapsed: boolean }
 *   namespace: { selectionByCompany: { [companyId]: 'all' | string } }
 *   documents: { reloadTick: number }
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';
import { payloadFields } from '../payload.js';

export interface UiState {
    sidebar: { mobileOpen: boolean; collapsed: boolean };
    namespace: { selectionByCompany: Record<string, string> };
    documents: { reloadTick: number };
}

export const initialUiState: UiState = Object.freeze({
    sidebar: { mobileOpen: false, collapsed: false },
    namespace: { selectionByCompany: {} },
    documents: { reloadTick: 0 },
});

export function uiReducer(state: UiState = initialUiState, event: PlatformEvent): UiState {
    switch (event.type) {
        case CoreEvents.UI_SIDEBAR_OPEN_REQUESTED:
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: true } };
        case CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED:
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: false } };
        case CoreEvents.UI_SIDEBAR_MOBILE_CHANGED: {
            const open = !!(payloadFields(event)).open;
            if (state.sidebar.mobileOpen === open) return state;
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: open } };
        }
        case CoreEvents.UI_SIDEBAR_COLLAPSE_CHANGED: {
            const collapsed = !!(payloadFields(event)).collapsed;
            if (state.sidebar.collapsed === collapsed) return state;
            return { ...state, sidebar: { ...state.sidebar, collapsed } };
        }
        case CoreEvents.UI_NAMESPACE_CHANGED: {
            const p = payloadFields(event);
            const cid = p.company_id;
            const selection = p.selection;
            if (typeof cid !== 'string' || !cid || (selection !== 'all' && typeof selection !== 'string')) return state;
            return {
                ...state,
                namespace: {
                    ...state.namespace,
                    selectionByCompany: { ...state.namespace.selectionByCompany, [cid]: selection },
                },
            };
        }
        case CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED:
            return { ...state, documents: { reloadTick: state.documents.reloadTick + 1 } };
        default:
            return state;
    }
}

export const uiSlice = { reducer: uiReducer, initial: initialUiState };
