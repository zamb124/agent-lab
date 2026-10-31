/**
 * office/documents: activeCatalogId === null остаётся корнем namespace.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { testEvent } from '../../helpers/bus-fixtures.js';

const storage = installFakeStorage();
Object.defineProperty(globalThis, 'window', { value: { localStorage: storage.localStorage }, configurable: true, writable: true });

const { documentsOp } = await import(
    '../../../../apps/office/ui/events/resources/documents.resource.js'
);

beforeEach(() => {
    storage.localStorage.clear();
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

describe('office/documents explorer root', () => {
    it('setActiveCatalog(null) leaves activeCatalogId null', () => {
        const opened = documentsOp.reducer(documentsOp.slice.initial, testEvent(documentsOp.events.SET_ACTIVE_CATALOG, { catalogId: 'cat-lara' }));
        expect(opened.activeCatalogId).toBe('cat-lara');

        const rooted = documentsOp.reducer(opened, testEvent(documentsOp.events.SET_ACTIVE_CATALOG, { catalogId: null }));
        expect(rooted.activeCatalogId).toBeNull();
        expect(rooted.selectedCatalogId).toBeNull();
    });

    it('setActiveCatalog empty string is root', () => {
        const opened = documentsOp.reducer(documentsOp.slice.initial, testEvent(documentsOp.events.SET_ACTIVE_CATALOG, { catalogId: 'cat-lara' }));
        const rooted = documentsOp.reducer(opened, testEvent(documentsOp.events.SET_ACTIVE_CATALOG, { catalogId: '' }));
        expect(rooted.activeCatalogId).toBeNull();
    });

    it('clearFilter resets to root and is not replaced by reducer', () => {
        const opened = documentsOp.reducer(documentsOp.slice.initial, testEvent(documentsOp.events.SET_ACTIVE_CATALOG, { catalogId: 'cat-lara' }));
        const rooted = documentsOp.reducer(opened, testEvent(documentsOp.events.CLEAR_FILTER, null));
        expect(rooted.activeCatalogId).toBeNull();
        expect(rooted.filterCatalogIds).toEqual([]);
        expect(rooted.selectedCatalogId).toBeNull();
    });
});
