/**
 * CRM API Service - Работа с CRM API
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class CRMAPIService extends BaseService {
    constructor(baseUrl = '/crm/api/v1') {
        super(baseUrl);
    }
    
    async getEntities(params = {}) {
        return this.get('/entities', params);
    }
    
    async getEntity(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}`);
    }
    
    async createEntity(data) {
        if (!data) {
            throw new Error('Entity data is required');
        }
        return this.post('/entities', data);
    }
    
    async updateEntity(entityId, data) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!data) {
            throw new Error('Entity data is required');
        }
        return this.put(`/entities/${entityId}`, data);
    }
    
    async deleteEntity(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.delete(`/entities/${entityId}`);
    }
    
    async searchEntities(query, params = {}) {
        if (!query) {
            throw new Error('Search query is required');
        }
        return this.post('/entities/search', { query, ...params });
    }
    
    async findEntitiesByText(text) {
        if (!text) {
            throw new Error('Text is required');
        }
        return this.post('/entities/search/mentions', { text });
    }
    
    async analyzeText(text, noteId = null, mentioned_entity_ids = null) {
        if (!text) {
            throw new Error('Text is required');
        }
        const params = noteId ? `?note_id=${noteId}` : '';
        return this.post(`/entities/analyze${params}`, { text, mentioned_entity_ids });
    }
    
    async getEntityTypes() {
        return this.get('/entity-types');
    }
    
    async createEntityType(data) {
        if (!data) {
            throw new Error('Entity type data is required');
        }
        return this.post('/entity-types', data);
    }
    
    async getRelationships(params = {}) {
        return this.get('/relationships', params);
    }
    
    async createRelationship(data) {
        if (!data) {
            throw new Error('Relationship data is required');
        }
        return this.post('/relationships', data);
    }
    
    async deleteRelationship(relationshipId) {
        if (!relationshipId) {
            throw new Error('Relationship ID is required');
        }
        return this.delete(`/relationships/${relationshipId}`);
    }
    
    async getRelationshipTypes() {
        return this.get('/relationship-types');
    }
    
    async createRelationshipType(data) {
        if (!data) {
            throw new Error('Relationship type data is required');
        }
        return this.post('/relationship-types', data);
    }
    
    async getInfluenceGraph(entityId, params = {}) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/influence-graph`, params);
    }
    
    async getShortestPath(sourceId, targetId, params = {}) {
        if (!sourceId || !targetId) {
            throw new Error('Source and target IDs are required');
        }
        return this.get('/relationships/path/', {
            from: sourceId,
            to: targetId,
            ...params,
        });
    }
    
    async getEntityRelationships(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/relationships`);
    }
    
    async getEntityWithRelatedEntities(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        
        const [entity, relResponse] = await Promise.all([
            this.getEntity(entityId),
            this.getEntityRelationships(entityId),
        ]);
        
        const relationships = relResponse.relationships || [];
        const relatedEntityIds = new Set();
        
        for (const rel of relationships) {
            if (rel.source_entity_id === entityId) {
                relatedEntityIds.add(rel.target_entity_id);
            } else {
                relatedEntityIds.add(rel.source_entity_id);
            }
        }
        
        const relatedEntities = [];
        for (const relEntityId of relatedEntityIds) {
            const relEntity = await this.getEntity(relEntityId);
            relatedEntities.push(relEntity);
        }
        
        return {
            entity,
            relationships,
            relatedEntities,
        };
    }

    async getEntityCard(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/card`);
    }

    async getDailySummary(date, options = {}) {
        if (!date) {
            throw new Error('Date is required');
        }
        const namespace = options.namespace;
        return this.post('/entities/daily-summary', {
            date,
            namespace: namespace ?? null,
            force_rebuild: options.forceRebuild === true,
        });
    }

    // === GRANTS ===

    async getEntityGrants(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/grants`);
    }

    async grantToUser(entityId, userId, role = 'viewer') {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!userId) {
            throw new Error('User ID is required');
        }
        return this.post(`/entities/${entityId}/grants/user`, {
            user_id: userId,
            role,
        });
    }

    async grantToCompany(entityId, companyId, role = 'viewer') {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!companyId) {
            throw new Error('Company ID is required');
        }
        return this.post(`/entities/${entityId}/grants/company`, {
            company_id: companyId,
            role,
        });
    }

    async makeEntityPublic(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.post(`/entities/${entityId}/grants/public`);
    }

    async revokeGrant(grantId) {
        if (!grantId) {
            throw new Error('Grant ID is required');
        }
        return this.delete(`/grants/${grantId}`);
    }

    // === ACCESS REQUESTS ===

    async listAccessRequests(status = null) {
        const params = status ? { status } : {};
        return this.get('/access-requests', params);
    }

    async getAccessRequest(requestId) {
        if (!requestId) {
            throw new Error('Request ID is required');
        }
        return this.get(`/access-requests/${requestId}`);
    }

    async createAccessRequest(entityId, message = null, includeDeps = false, maxDepth = 1) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.post('/access-requests', {
            resource_type: 'entity',
            resource_id: entityId,
            message,
            include_dependencies: includeDeps,
            max_depth: maxDepth,
        });
    }

    async approveAccessRequest(requestId) {
        if (!requestId) {
            throw new Error('Request ID is required');
        }
        return this.put(`/access-requests/${requestId}`, {
            status: 'approved',
        });
    }

    async rejectAccessRequest(requestId) {
        if (!requestId) {
            throw new Error('Request ID is required');
        }
        return this.put(`/access-requests/${requestId}`, {
            status: 'rejected',
        });
    }

    // === NAMESPACES ===

    async getNamespaces() {
        return this.get('/namespaces');
    }

    async createNamespace(name, description = null) {
        if (!name) {
            throw new Error('Namespace name is required');
        }
        return this.post('/namespaces', { name, description });
    }

    // === NAMESPACE GRANTS ===

    async getNamespaceGrants(namespace) {
        if (!namespace) {
            throw new Error('Namespace is required');
        }
        return this.get(`/namespaces/${namespace}/grants`);
    }

    async grantNamespaceToUser(namespace, userId, role = 'viewer') {
        if (!namespace) {
            throw new Error('Namespace is required');
        }
        if (!userId) {
            throw new Error('User ID is required');
        }
        return this.post(`/namespaces/${namespace}/grants/user`, {
            user_id: userId,
            role,
        });
    }

    async grantNamespaceToCompany(namespace, companyId, role = 'viewer') {
        if (!namespace) {
            throw new Error('Namespace is required');
        }
        if (!companyId) {
            throw new Error('Company ID is required');
        }
        return this.post(`/namespaces/${namespace}/grants/company`, {
            company_id: companyId,
            role,
        });
    }

    async makeNamespacePublic(namespace) {
        if (!namespace) {
            throw new Error('Namespace is required');
        }
        return this.post(`/namespaces/${namespace}/grants/public`);
    }

    // === ATTACHMENTS ===

    async getEntityAttachments(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/attachments`);
    }

    async uploadAttachment(entityId, file) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!file) {
            throw new Error('File is required');
        }
        const formData = new FormData();
        formData.append('file', file);
        return this.postFormData(`/entities/${entityId}/attachments`, formData);
    }

    async deleteAttachment(entityId, attachmentId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!attachmentId) {
            throw new Error('Attachment ID is required');
        }
        return this.delete(`/entities/${entityId}/attachments/${attachmentId}`);
    }
}

