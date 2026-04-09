/**
 * RAG API Service
 */

import { BaseService } from '@platform/lib/services/BaseService.js';

export class RAGAPIService extends BaseService {
    constructor(baseURL = '/rag/api/v1') {
        super(baseURL);
    }
    
    async getProviders() {
        return this.get('/providers');
    }
    
    async switchProvider(providerName) {
        return this.post('/providers/switch', { provider_name: providerName });
    }
    
    async getNamespaces(provider = null) {
        const params = provider ? { provider } : {};
        return this.get('/namespaces', params);
    }

    async createNamespace(name, description, provider = null) {
        const query = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.post(`/namespaces${query}`, { name, description });
    }

    async deleteNamespace(namespaceId, provider = null) {
        const query = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.delete(`/namespaces/${namespaceId}${query}`);
    }

    async getDocuments(namespaceId, provider = null) {
        const params = provider ? { provider } : {};
        return this.get(`/namespaces/${namespaceId}/documents`, params);
    }

    async uploadDocument(namespaceId, file, provider = null) {
        const formData = new FormData();
        formData.append('file', file);
        const query = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.post(`/namespaces/${namespaceId}/documents${query}`, formData);
    }

    async getDocumentStatus(documentId) {
        return this.get(`/documents/${documentId}/status`);
    }

    async deleteDocument(namespaceId, documentId, provider = null) {
        const query = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.delete(`/namespaces/${namespaceId}/documents/${documentId}${query}`);
    }

    async search(namespaceId, query, limit = 5, provider = null) {
        const providerQuery = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.post(
            `/namespaces/${namespaceId}/search${providerQuery}`,
            { query, limit }
        );
    }

    async globalSearch(query, namespaceIds, limit = 5, provider = null) {
        const providerQuery = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.post(
            `/search${providerQuery}`,
            { query, namespace_ids: namespaceIds, limit }
        );
    }
}

