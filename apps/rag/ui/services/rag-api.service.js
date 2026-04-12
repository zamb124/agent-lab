/**
 * RAG API Service
 */

import { BaseService } from '@platform/lib/services/BaseService.js';

export class RAGAPIService extends BaseService {
    constructor(baseURL = '/rag/api/v1') {
        super(baseURL);
    }

    _pathWithProvider(path, provider) {
        const q = provider ? { provider } : {};
        return this._buildUrlWithParams(path, q);
    }
    
    async getProviders() {
        return this.get('/providers');
    }
    
    async switchProvider(providerName) {
        return this.post('/providers/switch', { provider_name: providerName });
    }
    
    async getNamespaces(provider = null) {
        return this.get('/namespaces', provider ? { provider } : {});
    }
    
    async createNamespace(name, description, provider = null) {
        const path = this._pathWithProvider('/namespaces', provider);
        return this.post(path, { name, description }, {});
    }
    
    async deleteNamespace(namespaceId, provider = null) {
        const path = this._pathWithProvider(`/namespaces/${namespaceId}`, provider);
        return this.delete(path, {});
    }
    
    async getDocuments(namespaceId, provider = null) {
        const path = this._pathWithProvider(`/namespaces/${namespaceId}/documents`, provider);
        return this.get(path, {});
    }
    
    async uploadDocument(namespaceId, file, provider = null, metadata = null) {
        const formData = new FormData();
        formData.append('file', file);
        if (metadata && typeof metadata === 'object' && Object.keys(metadata).length > 0) {
            formData.append('metadata', JSON.stringify(metadata));
        }
        const query = {};
        if (provider) {
            query.provider = provider;
        }
        const path = this._buildUrlWithParams(`/namespaces/${namespaceId}/documents`, query);
        return this.post(path, formData, {});
    }
    
    async getDocumentStatus(documentId) {
        return this.get(`/documents/${documentId}/status`);
    }
    
    async deleteDocument(namespaceId, documentId, provider = null) {
        const path = this._pathWithProvider(
            `/namespaces/${namespaceId}/documents/${documentId}`,
            provider,
        );
        return this.delete(path, {});
    }
    
    async search(namespaceId, query, limit = 5, provider = null, bodyExtra = null) {
        const path = this._pathWithProvider(`/namespaces/${namespaceId}/search`, provider);
        const body = { query, limit, ...(bodyExtra && typeof bodyExtra === 'object' ? bodyExtra : {}) };
        return this.post(path, body, {});
    }
    
    async globalSearch(query, namespaceIds, limit = 5, provider = null, bodyExtra = null) {
        const path = this._pathWithProvider('/search', provider);
        const body = {
            query,
            namespace_ids: namespaceIds,
            limit,
            ...(bodyExtra && typeof bodyExtra === 'object' ? bodyExtra : {}),
        };
        return this.post(path, body, {});
    }
}

