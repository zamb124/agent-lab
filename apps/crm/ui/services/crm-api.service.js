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

    async getEntityTimelineBounds(params = {}) {
        return this.get('/entities/timeline/bounds', params);
    }
    
    async getEntity(entityId) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}`);
    }

    async getPersonEntitySelf() {
        return this.get('/entities/person-entity/self');
    }
    
    async createEntity(data) {
        if (!data) {
            throw new Error('Entity data is required');
        }
        return this.post('/entities', data);
    }

    async mergeEntities(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error('Merge payload is required');
        }
        return this.post('/entities/merge', payload);
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
    
    async bulkUpdateEntities(items) {
        return this.put('/entities/bulk', { items });
    }

    async bulkDeleteEntities(entityIds) {
        return this.post('/entities/bulk-delete', { entity_ids: entityIds });
    }

    async exportEntities(params = {}) {
        const format = params.format || 'json';
        const exportParams = Object.fromEntries(
            Object.entries({ ...params, format }).filter(([, v]) => v != null)
        );
        return this.getBlob('/entities/export', exportParams);
    }

    async getAggregate(params = {}) {
        return this.get('/entities/aggregate', params);
    }

    async voiceInput(audioFile, language = null) {
        const formData = new FormData();
        formData.append('file', audioFile);
        if (language) {
            formData.append('language', language);
        }
        return this.post('/entities/voice-input', formData);
    }

    async searchEntities(query, params = {}) {
        if (!query) {
            throw new Error('Search query is required');
        }
        return this.get('/entities/search', { query, ...params });
    }

    async getLaraWorkspaceSummary(namespace) {
        if (!namespace || typeof namespace !== 'string' || namespace.trim().length === 0) {
            throw new Error('namespace is required');
        }
        return this.get('/workspace/lara-summary', { namespace: namespace.trim() });
    }
    
    async findEntitiesByText(text) {
        if (!text) {
            throw new Error('Text is required');
        }
        return this.post('/entities/search/mentions', { text });
    }
    
    async analyzeNote(noteId, options = {}) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        if (options !== null && typeof options !== 'object') {
            throw new Error('Analyze options must be object');
        }

        const mentionedEntityIds = Array.isArray(options.mentionedEntityIds)
            ? options.mentionedEntityIds
            : (Array.isArray(options.mentioned_entity_ids) ? options.mentioned_entity_ids : null);
        const extractEntityTypes = Array.isArray(options.extractEntityTypes)
            ? options.extractEntityTypes
            : null;
        const extractRelationshipTypes = Array.isArray(options.extractRelationshipTypes)
            ? options.extractRelationshipTypes
            : null;

        const body = {};
        if (mentionedEntityIds && mentionedEntityIds.length > 0) {
            body.mentioned_entity_ids = mentionedEntityIds;
        }
        if (extractEntityTypes && extractEntityTypes.length > 0) {
            body.extract_entity_types = extractEntityTypes;
        }
        if (extractRelationshipTypes && extractRelationshipTypes.length > 0) {
            body.extract_relationship_types = extractRelationshipTypes;
        }
        if (typeof options.checkDuplicates === 'boolean') {
            body.check_duplicates = options.checkDuplicates;
        }

        return this.post(`/entities/notes/${encodeURIComponent(noteId)}/analyze`, body);
    }

    async patchNoteAnalysisDraft(noteId, body) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        if (!body || typeof body !== 'object') {
            throw new Error('Patch body is required');
        }
        return this.patch(`/entities/notes/${encodeURIComponent(noteId)}/analysis-draft`, body);
    }

    async applyNoteAnalysisDraft(noteId) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        return this.post(`/entities/notes/${encodeURIComponent(noteId)}/apply`, {});
    }
    
    async getEntityTypes() {
        return this.get('/entity-types');
    }

    async getEntityTypesByNamespace(namespace) {
        if (!namespace) {
            throw new Error('Namespace is required');
        }
        return this.get(`/entity-types/by-namespace/${encodeURIComponent(namespace)}`);
    }
    
    async createEntityType(data) {
        if (!data) {
            throw new Error('Entity type data is required');
        }
        return this.post('/entity-types', data);
    }

    async updateEntityType(typeId, data) {
        if (!typeId) {
            throw new Error('Type ID is required');
        }
        if (!data) {
            throw new Error('Entity type update data is required');
        }
        return this.put(`/entity-types/${encodeURIComponent(typeId)}`, data);
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

    async getRelationship(relationshipId) {
        if (!relationshipId) {
            throw new Error('Relationship ID is required');
        }
        return this.get(`/relationships/${relationshipId}`);
    }
    
    async getRelationshipTypes() {
        const response = await this.get('/relationships/types/');
        if (Array.isArray(response)) {
            return { relationship_types: response };
        }
        if (!response || typeof response !== 'object') {
            throw new Error('Relationship types response must be object');
        }
        if (Array.isArray(response.relationship_types)) {
            return { relationship_types: response.relationship_types };
        }
        if (Array.isArray(response.items)) {
            return { relationship_types: response.items };
        }
        throw new Error('relationship_types must be array');
    }
    
    async createRelationshipType(data) {
        if (!data) {
            throw new Error('Relationship type data is required');
        }
        return this.post('/relationships/types/', data);
    }

    async getInfluenceGraph(entityId, params = {}) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/influence-graph`, params);
    }

    async getOverviewGraph(entityIds, params = {}) {
        if (!Array.isArray(entityIds) || entityIds.length === 0) {
            throw new Error('entity_ids array is required');
        }
        return this.post('/entities/overview-graph', {
            entity_ids: entityIds,
            max_depth: params.max_depth || 3,
            relationship_types: params.relationship_types || null,
            created_at_from: params.created_at_from || null,
            created_at_to: params.created_at_to || null,
        });
    }

    async getRelatedEntities(entityId, params = {}) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/related`, params);
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
    
    async getEntityRelationships(entityId, params = {}) {
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        return this.get(`/entities/${entityId}/relationships`, params);
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

    async getPeriodSummary(dateFrom, dateTo, options = {}) {
        if (!dateFrom || !dateTo) {
            throw new Error('dateFrom and dateTo are required');
        }
        const namespace = options.namespace;
        return this.post('/entities/period-summary', {
            date_from: dateFrom,
            date_to: dateTo,
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

    async getNamespaceEditability(namespaceName) {
        if (!namespaceName || typeof namespaceName !== 'string') {
            throw new Error('Namespace name is required');
        }
        const normalizedNamespaceName = namespaceName.trim();
        if (!normalizedNamespaceName) {
            throw new Error('Namespace name is required');
        }
        return this.get(`/namespaces/${encodeURIComponent(normalizedNamespaceName)}/editability`);
    }

    async updateNamespace(namespaceName, payload) {
        if (!namespaceName || typeof namespaceName !== 'string') {
            throw new Error('Namespace name is required');
        }
        const normalizedNamespaceName = namespaceName.trim();
        if (!normalizedNamespaceName) {
            throw new Error('Namespace name is required');
        }
        if (!payload || typeof payload !== 'object') {
            throw new Error('Namespace update payload is required');
        }
        return this.put(`/namespaces/${encodeURIComponent(normalizedNamespaceName)}`, payload);
    }

    async getNamespaceTemplates() {
        return this.get('/namespaces/templates');
    }

    async getTemplateSchemaOptions() {
        return this.get('/namespaces/templates/schema/options');
    }

    async getNamespaceTemplate(templateId) {
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        return this.get(`/namespaces/templates/${encodeURIComponent(templateId)}`);
    }

    async createNamespaceTemplate(data) {
        if (!data || typeof data !== 'object') {
            throw new Error('Template payload is required');
        }
        return this.post('/namespaces/templates', data);
    }

    async updateNamespaceTemplate(templateId, data) {
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        if (!data || typeof data !== 'object') {
            throw new Error('Template payload is required');
        }
        return this.put(`/namespaces/templates/${encodeURIComponent(templateId)}`, data);
    }

    async deleteNamespaceTemplate(templateId) {
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        return this.delete(`/namespaces/templates/${encodeURIComponent(templateId)}`);
    }

    async upsertNamespaceTemplateType(templateId, data) {
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        if (!data || typeof data !== 'object') {
            throw new Error('Template type payload is required');
        }
        return this.post(`/namespaces/templates/${encodeURIComponent(templateId)}/types`, data);
    }

    async deleteNamespaceTemplateType(templateId, typeId) {
        if (!templateId || !typeId) {
            throw new Error('Template ID and type ID are required');
        }
        return this.delete(`/namespaces/templates/${encodeURIComponent(templateId)}/types/${encodeURIComponent(typeId)}`);
    }

    async createNamespace(name, description = null, templateId = null) {
        if (!name) {
            throw new Error('Namespace name is required');
        }
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        return this.post('/namespaces', { name, description, template_id: templateId });
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

    // === KNOWLEDGE IMPORT ===

    async uploadFile(file) {
        if (!file) {
            throw new Error('File is required');
        }
        const formData = new FormData();
        formData.append('file', file);
        return this.post('/files/', formData);
    }

    async listKnowledgeImports(namespace, limit = 50) {
        if (!namespace || typeof namespace !== 'string') {
            throw new Error('Namespace is required');
        }
        return this.get('/knowledge-imports', { namespace, limit });
    }

    async startKnowledgeImport(body) {
        if (!body || typeof body !== 'object') {
            throw new Error('Body is required');
        }
        return this.post('/knowledge-imports', body);
    }

    async cancelKnowledgeImport(importId) {
        if (!importId) {
            throw new Error('Import ID is required');
        }
        return this.post(`/knowledge-imports/${importId}/cancel`, {});
    }

    async rollbackKnowledgeImport(importId) {
        if (!importId) {
            throw new Error('Import ID is required');
        }
        return this.post(`/knowledge-imports/${importId}/rollback`, {});
    }

    async getKnowledgeImportCreatedEntities(importId) {
        if (!importId) {
            throw new Error('Import ID is required');
        }
        return this.get(`/knowledge-imports/${importId}/created-entities`, {});
    }

    async completeKnowledgeImportReview(importId) {
        if (!importId) {
            throw new Error('Import ID is required');
        }
        return this.post(`/knowledge-imports/${importId}/review-complete`, {});
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
        return this.post(`/entities/${entityId}/attachments`, formData);
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

