/**
 * Состояние приложения «Документы».
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

const baseStore = new BaseStore(
    'office',
    {
        documents: {
            items: [],
            loading: false,
            error: null,
        },
        integration: {
            configured: true,
            detail: '',
            loaded: false,
        },
        catalog: {
            activeCatalogId: '',
            filterCatalogIds: [],
        },
    },
    { persist: false, devtools: true },
);

export const OfficeStore = {
    get state() {
        return baseStore.state;
    },

    subscribe(listener) {
        return baseStore.subscribe(listener);
    },

    setDocumentsLoading(loading) {
        baseStore.setState((s) => ({
            documents: { ...s.documents, loading, error: loading ? null : s.documents.error },
        }));
    },

    setDocumentsError(error) {
        baseStore.setState((s) => ({
            documents: { ...s.documents, loading: false, error },
        }));
    },

    setDocumentsItems(items) {
        baseStore.setState((s) => ({
            documents: { ...s.documents, items: Array.isArray(items) ? items : [], loading: false, error: null },
        }));
    },

    setIntegrationStatus(configured, detail) {
        baseStore.setState((s) => ({
            integration: { configured, detail: detail || '', loaded: true },
        }));
    },

    setActiveCatalogId(catalogId) {
        const id = typeof catalogId === 'string' ? catalogId : '';
        baseStore.setState((s) => ({
            catalog: { ...s.catalog, activeCatalogId: id },
        }));
    },

    /**
     * @param {unknown} ids
     */
    setFilterCatalogIds(ids) {
        const arr = Array.isArray(ids)
            ? [...new Set(ids.map((x) => String(x).trim()).filter((x) => x.length > 0))]
            : [];
        baseStore.setState((s) => ({
            catalog: { ...s.catalog, filterCatalogIds: arr },
        }));
    },
};
