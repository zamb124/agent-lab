/**
 * RagStore - Состояние RAG Service приложения
 * Доменная структура: providers, namespaces, search, ui
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

/** Соответствует ``IndexProfileSplitConfig`` / ``IndexProfileParsingConfig`` (``core/rag_indexing_schema``). */
export const UPLOAD_INDEX_PROFILE_DEFAULTS_INITIAL = {
    split: {
        strategy: 'fixed_tokens',
        chunk_size: 512,
        chunk_overlap: 50,
        chonkie_code_language: 'auto',
        chonkie_fast_delimiters: '',
    },
    parsing: {
        engine: 'unstructured',
        languages: 'rus, eng',
    },
};

const baseStore = new BaseStore('rag', {
    providers: {
        list: [],
        current: 'pgvector',
        loading: false,
    },
    namespaces: {
        list: [],
        currentId: null,
        documents: {},
        documentSummaries: {},
    },
    search: {
        results: [],
        query: '',
    },
    ui: {
        currentView: 'namespaces',
    },
    usage: {
        pages: 0,
        maxPages: 1000,
        retrievals: 0,
        maxRetrievals: 10000,
    },
    loading: false,
    uploading: false,
    uploadIndexProfileDefaults: UPLOAD_INDEX_PROFILE_DEFAULTS_INITIAL,
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        providers: {
            current: state.providers.current,
        },
        ui: {
            currentView: state.ui.currentView,
        },
        uploadIndexProfileDefaults: state.uploadIndexProfileDefaults,
    })
});

export const RagStore = {
    get state() {
        return baseStore.state;
    },
    
    subscribe(callback) {
        return baseStore.subscribe(callback);
    },
    
    setState(updater) {
        return baseStore.setState(updater);
    },

    /**
     * Частичное обновление сохраняемых дефолтов загрузки (metadata.index_profile_config).
     * @param {{ split?: Record<string, unknown>, parsing?: Record<string, unknown> }} patch
     */
    patchUploadIndexProfileDefaults(patch) {
        if (!patch || typeof patch !== 'object') {
            throw new Error('patchUploadIndexProfileDefaults: ожидается объект');
        }
        baseStore.setState((s) => ({
            uploadIndexProfileDefaults: {
                split: { ...s.uploadIndexProfileDefaults.split, ...(patch.split || {}) },
                parsing: { ...s.uploadIndexProfileDefaults.parsing, ...(patch.parsing || {}) },
            },
        }));
    },

    resetUploadIndexProfileDefaults() {
        baseStore.setState({
            uploadIndexProfileDefaults: JSON.parse(JSON.stringify(UPLOAD_INDEX_PROFILE_DEFAULTS_INITIAL)),
        });
    },
    
    setProviders(providers, currentProvider) {
        baseStore.setState((s) => ({
            providers: {
                ...s.providers,
                list: providers,
                current: currentProvider,
                loading: false
            }
        }));
    },
    
    setCurrentView(view) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, currentView: view }
        }));
    },
    
    selectNamespace(namespaceId) {
        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, currentId: namespaceId },
            ui: { ...s.ui, currentView: 'documents' }
        }));
    },
    
    setLoading(loading) {
        baseStore.setState({ loading });
    },
    
    /**
     * @param {{ getNamespaces: (provider?: string | null) => Promise<unknown> }} ragApi
     * @param {{ silent?: boolean }} [options] silent — не менять глобальный `loading` (фоновая подгрузка списка)
     */
    async loadNamespaces(ragApi, options = {}) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }

        const silent = options.silent === true;
        if (!silent) {
            baseStore.setState({ loading: true });
        }

        const currentProvider = baseStore.state.providers.current;
        const response = await ragApi.getNamespaces(currentProvider);
        const countsByNs = response.document_status_counts_by_namespace || {};
        const namespaces = (response.namespaces || []).map((ns) => {
            const key = ns.namespace_id ?? ns.name;
            const c = countsByNs[key] || countsByNs[ns.name];
            return c ? { ...ns, document_status_counts: c } : { ...ns };
        });

        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, list: namespaces },
            ...(silent ? {} : { loading: false }),
        }));

        return namespaces;
    },
    
    async loadProviders(ragApi) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        
        baseStore.setState((s) => ({
            providers: { ...s.providers, loading: true }
        }));
        
        const response = await ragApi.getProviders();
        const providers = response.providers || [];
        const currentProvider = response.current_provider || 'pgvector';
        
        baseStore.setState((s) => ({
            providers: {
                ...s.providers,
                list: providers,
                current: currentProvider,
                loading: false
            }
        }));
        
        return { providers, currentProvider };
    },
    
    async switchProvider(ragApi, providerName) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!providerName) {
            throw new Error('Provider name is required');
        }
        
        baseStore.setState({ loading: true });
        
        await ragApi.switchProvider(providerName);
        
        baseStore.setState((s) => ({
            providers: { ...s.providers, current: providerName },
            namespaces: { ...s.namespaces, list: [] },
            loading: false
        }));
        
        await this.loadNamespaces(ragApi);
    },
    
    /**
     * @param {{ silent?: boolean }} [options] silent — не выставлять глобальный `loading` (фоновое обновление списка)
     */
    async loadDocuments(ragApi, namespaceId, options = {}) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!namespaceId) {
            throw new Error('Namespace ID is required');
        }

        const silent = options.silent === true;
        if (!silent) {
            baseStore.setState({ loading: true });
        }

        const currentProvider = baseStore.state.providers.current;
        const response = await ragApi.getDocuments(namespaceId, currentProvider);
        const documents = response.documents || [];
        const summary = response.summary ?? null;

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                documents: {
                    ...s.namespaces.documents,
                    [namespaceId]: documents,
                },
                documentSummaries: {
                    ...s.namespaces.documentSummaries,
                    ...(summary && typeof summary === 'object'
                        ? { [namespaceId]: summary }
                        : {}),
                },
            },
            ...(silent ? {} : { loading: false }),
        }));

        await this.loadNamespaces(ragApi, { silent: true });

        return documents;
    },

    async uploadDocument(ragApi, namespaceId, file, metadata = null) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!namespaceId) {
            throw new Error('Namespace ID is required');
        }
        if (!file) {
            throw new Error('File is required');
        }

        baseStore.setState({ uploading: true });
        const currentProvider = baseStore.state.providers.current;

        let response;
        try {
            response = await ragApi.uploadDocument(
                namespaceId,
                file,
                currentProvider,
                metadata,
            );
            if (!response.document_id) {
                throw new Error('Ответ сервера без document_id');
            }
        } finally {
            baseStore.setState({ uploading: false });
        }

        const pollStatus = async (attempts = 0) => {
            const maxAttempts = 90;
            if (attempts >= maxAttempts) {
                return;
            }
            try {
                const status = await ragApi.getDocumentStatus(response.document_id);

                if (status.status === 'completed') {
                    await this.loadDocuments(ragApi, namespaceId);
                    return;
                }

                if (status.status === 'failed') {
                    throw new Error(status.error_message || 'Ошибка индексации документа');
                }

                setTimeout(() => pollStatus(attempts + 1), 2000);
            } catch (e) {
                console.error('[RagStore] pollStatus', e);
            }
        };

        setTimeout(() => pollStatus(0), 1000);

        return response;
    },
    
    async deleteDocument(ragApi, namespaceId, documentId) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!namespaceId) {
            throw new Error('Namespace ID is required');
        }
        if (!documentId) {
            throw new Error('Document ID is required');
        }
        
        const prevDocuments = baseStore.state.namespaces.documents[namespaceId] || [];
        
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                documents: {
                    ...s.namespaces.documents,
                    [namespaceId]: prevDocuments.filter(d => d.document_id !== documentId)
                }
            }
        }));
        
        try {
            const currentProvider = baseStore.state.providers.current;
            await ragApi.deleteDocument(namespaceId, documentId, currentProvider);
            await this.loadDocuments(ragApi, namespaceId, { silent: true });
        } catch (error) {
            baseStore.setState((s) => ({
                namespaces: {
                    ...s.namespaces,
                    documents: {
                        ...s.namespaces.documents,
                        [namespaceId]: prevDocuments
                    }
                }
            }));
            throw error;
        }
    },
    
    /**
     * @param {Record<string, unknown>} [searchOptions] Поля тела POST …/search: channels, rerank, rrf_k, per_channel_top_k, filters
     */
    async searchInNamespace(
        ragApi,
        namespaceId,
        query,
        limit = 5,
        searchOptions = null,
    ) {
        return this.searchInNamespaces(ragApi, [namespaceId], query, limit, searchOptions);
    },

    /**
     * Поиск по одному или нескольким namespace. Несколько — `POST /search` (globalSearch), один — `POST …/namespaces/{id}/search`.
     *
     * @param {string[]} namespaceIds
     * @param {Record<string, unknown>} [searchOptions]
     */
    async searchInNamespaces(
        ragApi,
        namespaceIds,
        query,
        limit = 5,
        searchOptions = null,
    ) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!Array.isArray(namespaceIds) || namespaceIds.length === 0) {
            throw new Error('Нужен хотя бы один namespace');
        }
        const ids = [...new Set(namespaceIds.map((x) => String(x).trim()).filter(Boolean))];
        if (ids.length === 0) {
            throw new Error('Нужен хотя бы один namespace');
        }
        if (!query) {
            throw new Error('Query is required');
        }

        baseStore.setState((s) => ({
            search: { ...s.search, query },
            loading: true,
        }));

        const currentProvider = baseStore.state.providers.current;
        const bodyPayload =
            searchOptions && typeof searchOptions === 'object' && Object.keys(searchOptions).length > 0
                ? searchOptions
                : null;

        let results;
        if (ids.length === 1) {
            const response = await ragApi.search(ids[0], query, limit, currentProvider, bodyPayload);
            results = response.results || [];
        } else {
            const response = await ragApi.globalSearch(query, ids, limit, currentProvider, bodyPayload);
            const byNs = response.results || {};
            const flat = [];
            for (const id of ids) {
                const bucket = byNs[id];
                if (Array.isArray(bucket)) {
                    flat.push(...bucket);
                }
            }
            flat.sort((a, b) => Number(b.score) - Number(a.score));
            results = flat.slice(0, limit);
        }

        baseStore.setState((s) => ({
            search: { ...s.search, results },
            loading: false,
        }));

        return results;
    },
};
