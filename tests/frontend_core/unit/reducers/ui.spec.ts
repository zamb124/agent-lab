import { describe, it, expect } from 'vitest';
import { uiReducer, initialUiState, uiSlice } from '@platform/lib/events/reducers/ui.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('uiReducer', () => {
    it('initial: sidebar mobileOpen=false collapsed=false', () => {
        expect(initialUiState.sidebar).toEqual({ mobileOpen: false, collapsed: false });
        expect(initialUiState.documents.reloadTick).toBe(0);
        expect(uiSlice.initial).toBe(initialUiState);
    });

    it('UI_SIDEBAR_OPEN_REQUESTED → mobileOpen=true', () => {
        const next = uiReducer(initialUiState, ev(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED));
        expect(next.sidebar.mobileOpen).toBe(true);
    });

    it('UI_SIDEBAR_CLOSE_REQUESTED → mobileOpen=false', () => {
        const seeded = uiReducer(initialUiState, ev(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED));
        const next = uiReducer(seeded, ev(CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED));
        expect(next.sidebar.mobileOpen).toBe(false);
    });

    it('UI_SIDEBAR_COLLAPSE_CHANGED', () => {
        const next = uiReducer(initialUiState, ev(CoreEvents.UI_SIDEBAR_COLLAPSE_CHANGED, { collapsed: true }));
        expect(next.sidebar.collapsed).toBe(true);
    });

    it('UI_NAMESPACE_CHANGED обновляет selection по company_id', () => {
        const next = uiReducer(initialUiState, ev(CoreEvents.UI_NAMESPACE_CHANGED, { company_id: 'c1', selection: 'public' }));
        expect(next.namespace.selectionByCompany.c1).toBe('public');
    });

    it('UI_NAMESPACE_CHANGED без company_id — no-op', () => {
        const next = uiReducer(initialUiState, ev(CoreEvents.UI_NAMESPACE_CHANGED, { selection: 'all' }));
        expect(next).toBe(initialUiState);
    });

    it('UI_DOCUMENTS_RELOAD_REQUESTED инкрементирует reloadTick', () => {
        const a = uiReducer(initialUiState, ev(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED));
        expect(a.documents.reloadTick).toBe(1);
        const b = uiReducer(a, ev(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED));
        expect(b.documents.reloadTick).toBe(2);
    });
});
