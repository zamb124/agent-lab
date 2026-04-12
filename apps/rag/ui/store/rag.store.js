/**
 * RagStore - Состояние RAG Service приложения
 * Доменная структура: providers, namespaces, search, ui
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

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
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        providers: {
            current: state.providers.current,
        },
        ui: {
            currentView: state.ui.currentView,
        }
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
    
    async loadNamespaces(ragApi) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        
        baseStore.setState({ loading: true });
        
        const currentProvider = baseStore.state.providers.current;
        const response = await ragApi.getNamespaces(currentProvider);
        const namespaces = response.items || [];
        
        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, list: namespaces },
            loading: false
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
        const providers = response.items || [];
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
    
    async loadDocuments(ragApi, namespaceId) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!namespaceId) {
            throw new Error('Namespace ID is required');
        }
        
        baseStore.setState({ loading: true });
        
        const currentProvider = baseStore.state.providers.current;
        const response = await ragApi.getDocuments(namespaceId, currentProvider);
        const documents = response.items || [];
        
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                documents: {
                    ...s.namespaces.documents,
                    [namespaceId]: documents
                }
            },
            loading: false
        }));
        
        return documents;
    },
    
    async uploadDocument(ragApi, namespaceId, file) {
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
        const response = await ragApi.uploadDocument(namespaceId, file, currentProvider);
        
        const pollStatus = async () => {
            const status = await ragApi.getDocumentStatus(response.document_id);
            
            if (status.status === 'completed') {
                await this.loadDocuments(ragApi, namespaceId);
                baseStore.setState({ uploading: false });
                return;
            }
            
            if (status.status === 'failed') {
                baseStore.setState({ uploading: false });
                throw new Error(status.error_message || 'Document processing failed');
            }
            
            setTimeout(pollStatus, 2000);
        };
        
        setTimeout(pollStatus, 1000);
        
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
    
    async searchInNamespace(ragApi, namespaceId, query, limit = 5) {
        if (!ragApi) {
            throw new Error('ragApi service is required');
        }
        if (!namespaceId) {
            throw new Error('Namespace ID is required');
        }
        if (!query) {
            throw new Error('Query is required');
        }
        
        baseStore.setState((s) => ({
            search: { ...s.search, query },
            loading: true
        }));
        
        const currentProvider = baseStore.state.providers.current;
        const response = await ragApi.search(namespaceId, query, limit, currentProvider);
        const results = response.results || [];
        
        baseStore.setState((s) => ({
            search: { ...s.search, results },
            loading: false
        }));
        
        return results;
    },
};
