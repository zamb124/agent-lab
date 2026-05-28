/**
 * Слайс UI — sidebar (mobile/collapse), namespace selection, documents reload счётчик.
 *
 * state.ui:
 *   sidebar:   { mobileOpen: boolean, collapsed: boolean }
 *   namespace: { selectionByCompany: { [companyId]: 'all' | string } }
 *   documents: { reloadTick: number }
 */

import { CoreEvents } from '../contract.js';

export const initialUiState = Object.freeze({
    sidebar: { mobileOpen: false, collapsed: false },
    namespace: { selectionByCompany: {} },
    documents: { reloadTick: 0 },
});

export function uiReducer(state = initialUiState, event) {
    switch (event.type) {
        case CoreEvents.UI_SIDEBAR_OPEN_REQUESTED:
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: true } };
        case CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED:
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: false } };
        case CoreEvents.UI_SIDEBAR_MOBILE_CHANGED: {
            const open = !!(event.payload && event.payload.open);
            if (state.sidebar.mobileOpen === open) return state;
            return { ...state, sidebar: { ...state.sidebar, mobileOpen: open } };
        }
        case CoreEvents.UI_SIDEBAR_COLLAPSE_CHANGED: {
            const collapsed = !!(event.payload && event.payload.collapsed);
            if (state.sidebar.collapsed === collapsed) return state;
            return { ...state, sidebar: { ...state.sidebar, collapsed } };
        }
        case CoreEvents.UI_NAMESPACE_CHANGED: {
            const cid = event.payload && event.payload.company_id;
            const selection = event.payload && event.payload.selection;
            if (!cid || (selection !== 'all' && typeof selection !== 'string')) return state;
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
