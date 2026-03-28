/**
 * CRM Store - Состояние CRM приложения
 * Доменная структура: entities, ui, ai, grants, accessRequests
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

function getNamespaceName(namespace) {
    if (!namespace) {
        return null;
    }
    if (typeof namespace === 'string') {
        return namespace;
    }
    if (typeof namespace === 'object' && typeof namespace.name === 'string') {
        return namespace.name;
    }
    throw new Error('Invalid namespace value');
}

const baseStore = new BaseStore('crm', {
    namespaces: {
        list: [],
        current: null,
        grants: [],
        loading: false,
    },
    entities: {
        notes: [],
        currentNoteId: null,
        noteText: '',
        noteRelatedEntities: [],
        list: [],
        entityTypes: [],
        relationshipTypes: [],
        currentEntityId: null,
        currentEntity: null,
        currentEntityRelated: [],
        relationships: [],
        filters: {
            namespace: null,
            entity_type: null,
            entity_subtype: null,
            date_from: null,
            date_to: null,
            tags: [],
            search: '',
            user_id: null,
        },
        entitiesLoading: false,
    },
    grants: {
        currentEntityGrants: [],
        loading: false,
    },
    accessRequests: {
        pending: [],
        sent: [],
        loading: false,
    },
    ui: {
        currentView: 'notes',
        sidebarOpen: false,
        isMobile: false,
        filterTags: [],
        searchQuery: '',
        collapsedPanels: {},
    },
    ai: {
        suggestions: [],
        mentionedEntities: [],
        analyzing: false,
    },
    loading: false,
    error: null,
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        namespaces: {
            current: state.namespaces.current,
        },
        ui: {
            currentView: state.ui.currentView,
            sidebarOpen: state.ui.sidebarOpen,
            collapsedPanels: state.ui.collapsedPanels,
        }
    })
});

export const CRMStore = {
    get state() {
        return baseStore.state;
    },
    
    subscribe(callback) {
        return baseStore.subscribe(callback);
    },
    
    setState(updater) {
        return baseStore.setState(updater);
    },
    
    // URL синхронизация
    initFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/^\/crm\/(\w+)(?:\/(.+))?/);
        
        if (!match) {
            // /crm/ без раздела - редирект на notes
            history.replaceState({}, '', '/crm/notes');
            return;
        }
        
        const [, view, id] = match;
        const validViews = ['notes', 'entities', 'graph', 'tasks', 'calendar'];
        
        if (!validViews.includes(view)) {
            history.replaceState({}, '', '/crm/notes');
            return;
        }
        
        this.setCurrentView(view, { skipUrl: true });
        
        if (id) {
            if (view === 'notes') {
                this.setCurrentNote(id, { skipUrl: true });
            } else if (view === 'entities') {
                this.setCurrentEntity(id, { skipUrl: true });
            }
        }
    },
    
    setupPopstateListener() {
        window.addEventListener('popstate', () => {
            this.initFromUrl();
        });
    },
    
    setMobile(isMobile) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, isMobile }
        }));
    },
    
    setCurrentView(view, options = {}) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, currentView: view }
        }));
        
        if (!options.skipUrl) {
            const currentId = view === 'notes' 
                ? baseStore.state.entities.currentNoteId 
                : view === 'entities' 
                    ? baseStore.state.entities.currentEntityId 
                    : null;
            
            const url = currentId ? `/crm/${view}/${currentId}` : `/crm/${view}`;
            history.pushState({}, '', url);
        }
    },
    
    toggleSidebar() {
        baseStore.setState((s) => ({
            ui: { ...s.ui, sidebarOpen: !s.ui.sidebarOpen }
        }));
    },
    
    togglePanel(panelId) {
        baseStore.setState((s) => ({
            ui: { 
                ...s.ui, 
                collapsedPanels: {
                    ...s.ui.collapsedPanels,
                    [panelId]: !s.ui.collapsedPanels[panelId]
                }
            }
        }));
    },
    
    isPanelCollapsed(panelId) {
        return baseStore.state.ui.collapsedPanels[panelId] || false;
    },
    
    async loadNotes(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        baseStore.setState({ loading: true });
        
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        const params = { entity_type: 'note' };
        if (namespaceName) {
            params.namespace = namespaceName;
        }
        
        const notes = await crmApi.getEntities(params);
        
        baseStore.setState((s) => ({
            entities: { ...s.entities, notes: Array.isArray(notes) ? notes : [] },
            loading: false
        }));
        return notes;
    },
    
    setCurrentNote(noteId, options = {}) {
        baseStore.setState((s) => ({
            entities: { 
                ...s.entities, 
                currentNoteId: noteId,
                noteRelatedEntities: [],
            }
        }));
        
        if (!options.skipUrl) {
            const url = noteId ? `/crm/notes/${noteId}` : '/crm/notes';
            history.pushState({}, '', url);
        }
    },
    
    async loadNoteRelationships(crmApi, noteId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!noteId) {
            baseStore.setState((s) => ({
                entities: { ...s.entities, noteRelatedEntities: [] }
            }));
            return [];
        }
        
        const data = await crmApi.getEntityWithRelatedEntities(noteId);
        const relatedEntities = data.relatedEntities || [];
        
        baseStore.setState((s) => ({
            entities: { ...s.entities, noteRelatedEntities: relatedEntities }
        }));
        
        return relatedEntities;
    },
    
    updateNoteText(text) {
        baseStore.setState((s) => ({
            entities: { ...s.entities, noteText: text }
        }));
    },
    
    async createNote(crmApi, data) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        baseStore.setState({ loading: true });
        
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        const note = await crmApi.createEntity({
            entity_type: 'note',
            namespace: namespaceName || 'default',
            ...data
        });
        
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                notes: [note, ...s.entities.notes],
                currentNoteId: note.entity_id,
            },
            loading: false
        }));
        
        return note;
    },
    
    async updateNote(crmApi, noteId, data) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        
        const updatedNote = await crmApi.updateEntity(noteId, data);
        
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                notes: s.entities.notes.map(n => 
                    n.entity_id === noteId ? updatedNote : n
                )
            }
        }));
        
        return updatedNote;
    },
    
    async deleteNote(crmApi, noteId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        
        const prevNotes = baseStore.state.entities.notes;
        
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                notes: s.entities.notes.filter(n => n.entity_id !== noteId),
                currentNoteId: s.entities.currentNoteId === noteId ? null : s.entities.currentNoteId
            }
        }));
        
        try {
            await crmApi.deleteEntity(noteId);
        } catch (error) {
            baseStore.setState((s) => ({
                entities: { ...s.entities, notes: prevNotes },
                error: error.message
            }));
            throw error;
        }
    },
    
    async highlightMentions(crmApi, text) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        if (!text || text.trim().length === 0) {
            baseStore.setState((s) => ({
                ai: { ...s.ai, mentionedEntities: [] }
            }));
            return;
        }
        
        baseStore.setState((s) => ({
            ai: { ...s.ai, analyzing: true }
        }));
        
        const response = await crmApi.findEntitiesByText(text);
        const entities = response.entities || [];
        
        baseStore.setState((s) => ({
            ai: { ...s.ai, mentionedEntities: entities, analyzing: false }
        }));
        
        return entities;
    },
    
    async analyzeText(crmApi, text, noteId = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!text) {
            throw new Error('Text is required');
        }
        
        baseStore.setState((s) => ({
            ai: { ...s.ai, analyzing: true }
        }));
        
        const analysis = await crmApi.analyzeText(text, noteId);
        
        const suggestions = [
            ...(analysis.entities || []),
            ...(analysis.relationships || [])
        ];
        
        console.log('[CRMStore] analyzeText result:', { analysis, suggestions });
        
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                suggestions,
                analyzing: false
            }
        }));
        
        return analysis;
    },
    
    clearAISuggestions() {
        baseStore.setState((s) => ({
            ai: { ...s.ai, suggestions: [] }
        }));
    },

    updateSuggestion(index, updates) {
        if (index < 0) {
            throw new Error('Invalid suggestion index');
        }

        baseStore.setState((s) => {
            const suggestions = [...s.ai.suggestions];
            if (index >= suggestions.length) {
                throw new Error('Suggestion index out of bounds');
            }
            suggestions[index] = { ...suggestions[index], ...updates };
            return {
                ai: { ...s.ai, suggestions }
            };
        });
    },

    removeSuggestion(index) {
        if (index < 0) {
            throw new Error('Invalid suggestion index');
        }

        baseStore.setState((s) => {
            const suggestions = s.ai.suggestions.filter((_, i) => i !== index);
            return {
                ai: { ...s.ai, suggestions }
            };
        });
    },

    async confirmSuggestion(crmApi, index) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (index < 0) {
            throw new Error('Invalid suggestion index');
        }

        const suggestions = baseStore.state.ai.suggestions;
        if (index >= suggestions.length) {
            throw new Error('Suggestion index out of bounds');
        }

        const suggestion = suggestions[index];
        if (suggestion.relationship_type) {
            throw new Error('Use confirmRelationship for relationships');
        }

        const currentNoteId = baseStore.state.entities.currentNoteId;

        const entity = await crmApi.createEntity({
            entity_type: suggestion.entity_type,
            entity_subtype: suggestion.entity_subtype || null,
            name: suggestion.name,
            description: suggestion.description || null,
            attributes: suggestion.attributes || {},
            note_date: suggestion.note_date || null,
            due_date: suggestion.due_date || null,
            priority: suggestion.priority || null,
            assignees: suggestion.assignees || [],
        });

        if (currentNoteId && entity.entity_type !== 'note') {
            await crmApi.createRelationship({
                source_entity_id: currentNoteId,
                target_entity_id: entity.entity_id,
                relationship_type: 'mentions',
                weight: 1.0,
            });
        }

        baseStore.setState((s) => {
            const newSuggestions = s.ai.suggestions.filter((_, i) => i !== index);
            const updatedNotes = suggestion.entity_type === 'note'
                ? [entity, ...s.entities.notes]
                : s.entities.notes;
            const updatedRelated = currentNoteId && entity.entity_type !== 'note'
                ? [...s.entities.noteRelatedEntities, entity]
                : s.entities.noteRelatedEntities;
            return {
                ai: { ...s.ai, suggestions: newSuggestions },
                entities: { 
                    ...s.entities, 
                    notes: updatedNotes,
                    noteRelatedEntities: updatedRelated,
                }
            };
        });

        return entity;
    },

    async confirmRelationship(crmApi, index) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (index < 0) {
            throw new Error('Invalid suggestion index');
        }

        const suggestions = baseStore.state.ai.suggestions;
        if (index >= suggestions.length) {
            throw new Error('Suggestion index out of bounds');
        }

        const suggestion = suggestions[index];
        if (!suggestion.relationship_type) {
            throw new Error('Not a relationship suggestion');
        }

        const relationship = await crmApi.createRelationship({
            source_entity_id: suggestion.source_entity_id,
            target_entity_id: suggestion.target_entity_id,
            relationship_type: suggestion.relationship_type,
            weight: suggestion.weight || 1.0,
        });

        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                suggestions: s.ai.suggestions.filter((_, i) => i !== index)
            }
        }));

        return relationship;
    },

    async updateExistingEntity(crmApi, index, existingId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (index < 0) {
            throw new Error('Invalid suggestion index');
        }

        const suggestions = baseStore.state.ai.suggestions;
        if (index >= suggestions.length) {
            throw new Error('Suggestion index out of bounds');
        }

        const suggestion = suggestions[index];
        
        const updateData = {
            name: suggestion.name,
            description: suggestion.description || null,
            attributes: suggestion.attributes || {},
        };

        const updated = await crmApi.updateEntity(existingId, updateData);

        baseStore.setState((s) => {
            const newSuggestions = s.ai.suggestions.filter((_, i) => i !== index);
            return {
                ai: { ...s.ai, suggestions: newSuggestions },
                entities: {
                    ...s.entities,
                    list: s.entities.list.map(e =>
                        e.entity_id === existingId ? updated : e
                    ),
                }
            };
        });

        return updated;
    },

    async confirmAllSuggestions(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const currentNoteId = baseStore.state.entities.currentNoteId;
        const suggestions = [...baseStore.state.ai.suggestions];
        let createdCount = 0;
        const createdEntities = [];

        const entitySuggestions = suggestions.filter(s => s.entity_type && !s.relationship_type);
        for (const suggestion of entitySuggestions) {
            const entity = await crmApi.createEntity({
                entity_type: suggestion.entity_type,
                entity_subtype: suggestion.entity_subtype || null,
                name: suggestion.name,
                description: suggestion.description || null,
                attributes: suggestion.attributes || {},
                note_date: suggestion.note_date || null,
                due_date: suggestion.due_date || null,
                priority: suggestion.priority || null,
                assignees: suggestion.assignees || [],
            });
            createdCount++;

            if (currentNoteId && entity.entity_type !== 'note') {
                await crmApi.createRelationship({
                    source_entity_id: currentNoteId,
                    target_entity_id: entity.entity_id,
                    relationship_type: 'mentions',
                    weight: 1.0,
                });
                createdEntities.push(entity);
            }
        }

        const relationships = suggestions.filter(s => s.relationship_type);
        for (const suggestion of relationships) {
            if (suggestion.source_entity_id && suggestion.target_entity_id) {
                await crmApi.createRelationship({
                    source_entity_id: suggestion.source_entity_id,
                    target_entity_id: suggestion.target_entity_id,
                    relationship_type: suggestion.relationship_type,
                    weight: suggestion.weight || 1.0,
                });
                createdCount++;
            }
        }

        baseStore.setState((s) => ({
            ai: { ...s.ai, suggestions: [] },
            entities: {
                ...s.entities,
                noteRelatedEntities: [...s.entities.noteRelatedEntities, ...createdEntities],
            }
        }));

        await this.loadNotes(crmApi);

        return createdCount;
    },

    async loadEntityTypes(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        const types = await crmApi.getEntityTypes();
        baseStore.setState((s) => ({
            entities: { ...s.entities, entityTypes: types }
        }));
        return types;
    },
    
    async loadRelationshipTypes(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        const types = await crmApi.getRelationshipTypes();
        baseStore.setState((s) => ({
            entities: { ...s.entities, relationshipTypes: types }
        }));
        return types;
    },
    
    setSearchQuery(query) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, searchQuery: query }
        }));
    },
    
    setFilterTags(tags) {
        baseStore.setState((s) => ({
            ui: { ...s.ui, filterTags: tags }
        }));
    },
    
    clearError() {
        baseStore.setState({ error: null });
    },

    // === NAMESPACES ===

    async loadNamespaces(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, loading: true }
        }));

        const response = await crmApi.getNamespaces();
        const list = response.namespaces || [];

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                list,
                loading: false
            }
        }));

        return list;
    },

    setCurrentNamespace(namespace) {
        const namespaceName = getNamespaceName(namespace);
        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, current: namespace },
            entities: {
                ...s.entities,
                filters: { ...s.entities.filters, namespace: namespaceName },
                list: [],
                currentEntityId: null,
                currentEntity: null,
            }
        }));
    },

    async createNamespace(crmApi, name, description = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!name) {
            throw new Error('Namespace name is required');
        }

        const namespace = await crmApi.createNamespace(name, description);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                list: [...s.namespaces.list, namespace],
                current: namespace,
            },
            entities: {
                ...s.entities,
                filters: { ...s.entities.filters, namespace: namespace.name }
            }
        }));

        return namespace;
    },

    async loadNamespaceGrants(crmApi, namespace) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!namespace) {
            throw new Error('Namespace is required');
        }

        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, loading: true }
        }));

        const grants = await crmApi.getNamespaceGrants(namespace);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                grants: Array.isArray(grants) ? grants : [],
                loading: false
            }
        }));

        return grants;
    },

    async grantNamespaceToUser(crmApi, namespace, userId, role = 'viewer') {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.grantNamespaceToUser(namespace, userId, role);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                grants: [...s.namespaces.grants, grant]
            }
        }));

        return grant;
    },

    async grantNamespaceToCompany(crmApi, namespace, companyId, role = 'viewer') {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.grantNamespaceToCompany(namespace, companyId, role);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                grants: [...s.namespaces.grants, grant]
            }
        }));

        return grant;
    },

    async makeNamespacePublic(crmApi, namespace) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.makeNamespacePublic(namespace);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                grants: [...s.namespaces.grants, grant]
            }
        }));

        return grant;
    },

    // === ENTITIES (общий список) ===

    setEntityFilters(filters) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                filters: { ...s.entities.filters, ...filters }
            }
        }));
    },

    clearEntityFilters() {
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                filters: {
                    namespace: namespaceName,
                    entity_type: null,
                    entity_subtype: null,
                    date_from: null,
                    date_to: null,
                    tags: [],
                    search: '',
                    user_id: null,
                }
            }
        }));
    },

    async loadEntities(crmApi, params = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        baseStore.setState((s) => ({
            entities: { ...s.entities, entitiesLoading: true }
        }));

        const filters = baseStore.state.entities.filters;
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        const queryParams = {
            entity_type: params.entity_type || filters.entity_type,
            entity_subtype: params.entity_subtype || filters.entity_subtype,
            namespace: namespaceName,
            date_from: filters.date_from,
            date_to: filters.date_to,
            tags: filters.tags.length > 0 ? filters.tags.join(',') : undefined,
            user_id: filters.user_id,
            limit: params.limit || 100,
        };

        Object.keys(queryParams).forEach(key => {
            if (queryParams[key] === null || queryParams[key] === undefined) {
                delete queryParams[key];
            }
        });

        const entities = await crmApi.getEntities(queryParams);

        let filteredList = Array.isArray(entities) ? entities : [];
        if (filters.search) {
            const searchLower = filters.search.toLowerCase();
            filteredList = filteredList.filter(e =>
                e.name?.toLowerCase().includes(searchLower) ||
                e.description?.toLowerCase().includes(searchLower)
            );
        }

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list: filteredList,
                entitiesLoading: false
            }
        }));

        return filteredList;
    },

    setCurrentEntity(entityId, options = {}) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                currentEntityId: entityId,
                currentEntity: entityId
                    ? s.entities.list.find(e => e.entity_id === entityId) || null
                    : null,
                currentEntityRelated: [],
            },
            grants: { ...s.grants, currentEntityGrants: [] }
        }));
        
        if (!options.skipUrl) {
            const url = entityId ? `/crm/entities/${entityId}` : '/crm/entities';
            history.pushState({}, '', url);
        }
    },

    async loadEntityCard(crmApi, entityId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        baseStore.setState((s) => ({
            entities: { ...s.entities, entitiesLoading: true }
        }));

        const card = await crmApi.getEntityCard(entityId);

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                currentEntity: card.entity,
                currentEntityRelated: card.related_entities || [],
                entitiesLoading: false,
            }
        }));

        return card;
    },

    async createEntity(crmApi, data) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        const entityData = {
            ...data,
            namespace: data.namespace || namespaceName || 'default',
        };

        const entity = await crmApi.createEntity(entityData);

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list: [entity, ...s.entities.list],
                currentEntityId: entity.entity_id,
                currentEntity: entity,
            }
        }));

        return entity;
    },

    async updateEntity(crmApi, entityId, data) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        const updated = await crmApi.updateEntity(entityId, data);

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list: s.entities.list.map(e =>
                    e.entity_id === entityId ? updated : e
                ),
                currentEntity: s.entities.currentEntityId === entityId
                    ? updated
                    : s.entities.currentEntity,
            }
        }));

        return updated;
    },

    async deleteEntity(crmApi, entityId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        await crmApi.deleteEntity(entityId);

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list: s.entities.list.filter(e => e.entity_id !== entityId),
                currentEntityId: s.entities.currentEntityId === entityId
                    ? null
                    : s.entities.currentEntityId,
                currentEntity: s.entities.currentEntityId === entityId
                    ? null
                    : s.entities.currentEntity,
            }
        }));
    },

    // === GRANTS ===

    async loadEntityGrants(crmApi, entityId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        baseStore.setState((s) => ({
            grants: { ...s.grants, loading: true }
        }));

        const grants = await crmApi.getEntityGrants(entityId);

        baseStore.setState((s) => ({
            grants: {
                ...s.grants,
                currentEntityGrants: Array.isArray(grants) ? grants : [],
                loading: false
            }
        }));

        return grants;
    },

    async grantToUser(crmApi, entityId, userId, role) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.grantToUser(entityId, userId, role);

        baseStore.setState((s) => ({
            grants: {
                ...s.grants,
                currentEntityGrants: [...s.grants.currentEntityGrants, grant]
            }
        }));

        return grant;
    },

    async grantToCompany(crmApi, entityId, companyId, role) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.grantToCompany(entityId, companyId, role);

        baseStore.setState((s) => ({
            grants: {
                ...s.grants,
                currentEntityGrants: [...s.grants.currentEntityGrants, grant]
            }
        }));

        return grant;
    },

    async makeEntityPublic(crmApi, entityId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const grant = await crmApi.makeEntityPublic(entityId);

        baseStore.setState((s) => ({
            grants: {
                ...s.grants,
                currentEntityGrants: [...s.grants.currentEntityGrants, grant]
            }
        }));

        return grant;
    },

    async revokeGrant(crmApi, grantId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        await crmApi.revokeGrant(grantId);

        baseStore.setState((s) => ({
            grants: {
                ...s.grants,
                currentEntityGrants: s.grants.currentEntityGrants.filter(
                    g => g.grant_id !== grantId
                )
            }
        }));
    },

    // === ACCESS REQUESTS ===

    async loadAccessRequests(crmApi, status = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        baseStore.setState((s) => ({
            accessRequests: { ...s.accessRequests, loading: true }
        }));

        const requests = await crmApi.listAccessRequests(status);

        baseStore.setState((s) => ({
            accessRequests: {
                ...s.accessRequests,
                pending: Array.isArray(requests)
                    ? requests.filter(r => r.status === 'pending')
                    : [],
                loading: false
            }
        }));

        return requests;
    },

    async createAccessRequest(crmApi, entityId, message, includeDeps = false, maxDepth = 1) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const request = await crmApi.createAccessRequest(
            entityId,
            message,
            includeDeps,
            maxDepth
        );

        baseStore.setState((s) => ({
            accessRequests: {
                ...s.accessRequests,
                sent: [...s.accessRequests.sent, request]
            }
        }));

        return request;
    },

    async approveAccessRequest(crmApi, requestId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const result = await crmApi.approveAccessRequest(requestId);

        baseStore.setState((s) => ({
            accessRequests: {
                ...s.accessRequests,
                pending: s.accessRequests.pending.filter(r => r.request_id !== requestId)
            }
        }));

        return result;
    },

    async rejectAccessRequest(crmApi, requestId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const result = await crmApi.rejectAccessRequest(requestId);

        baseStore.setState((s) => ({
            accessRequests: {
                ...s.accessRequests,
                pending: s.accessRequests.pending.filter(r => r.request_id !== requestId)
            }
        }));

        return result;
    },
};
