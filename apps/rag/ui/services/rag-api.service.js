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
        return this.get('/namespaces', { params });
    }
    
    async createNamespace(name, description, provider = null) {
        const params = provider ? { provider } : {};
        return this.post('/namespaces', { name, description }, { params });
    }
    
    async deleteNamespace(namespaceId, provider = null) {
        const params = provider ? { provider } : {};
        return this.delete(`/namespaces/${namespaceId}`, { params });
    }
    
    async getDocuments(namespaceId, provider = null) {
        const params = provider ? { provider } : {};
        return this.get(`/namespaces/${namespaceId}/documents`, { params });
    }
    
    async uploadDocument(namespaceId, file, provider = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        const params = provider ? { provider } : {};
        const url = `/namespaces/${namespaceId}/documents`;
        
        return this.post(url, formData, { params });
    }
    
    async getDocumentStatus(documentId) {
        return this.get(`/documents/${documentId}/status`);
    }
    
    async deleteDocument(namespaceId, documentId, provider = null) {
        const params = provider ? { provider } : {};
        return this.delete(`/namespaces/${namespaceId}/documents/${documentId}`, { params });
    }
    
    async search(namespaceId, query, limit = 5, provider = null) {
        const params = provider ? { provider } : {};
        return this.post(
            `/namespaces/${namespaceId}/search`,
            { query, limit },
            { params }
        );
    }
    
    async globalSearch(query, namespaceIds, limit = 5, provider = null) {
        const params = provider ? { provider } : {};
        return this.post(
            '/search',
            { query, namespace_ids: namespaceIds, limit },
            { params }
        );
    }
}

