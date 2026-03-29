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

function normalizeEntityTypeList(payload) {
    if (Array.isArray(payload)) {
        return payload;
    }
    throw new Error('Entity types payload must be array');
}

function normalizeRelationshipTypeList(payload) {
    if (!payload || typeof payload !== 'object') {
        throw new Error('Relationship types payload must be object');
    }
    if (!Array.isArray(payload.relationship_types)) {
        throw new Error('relationship_types must be array');
    }
    return payload.relationship_types.map((item) => {
        if (!item || typeof item !== 'object') {
            throw new Error('Relationship type must be object');
        }
        if (typeof item.type_id !== 'string' || item.type_id.trim().length === 0) {
            throw new Error('Relationship type_id is required');
        }
        if (typeof item.name !== 'string' || item.name.trim().length === 0) {
            throw new Error('Relationship name is required');
        }
        return {
            type_id: item.type_id,
            name: item.name,
            is_directed: item.is_directed === false ? false : true,
            inverse_type_id: typeof item.inverse_type_id === 'string' ? item.inverse_type_id : null,
            icon: typeof item.icon === 'string' ? item.icon : '',
            color: typeof item.color === 'string' ? item.color : '',
            weight_default: typeof item.weight_default === 'number' ? item.weight_default : null,
        };
    });
}

function isRelationshipSuggestion(suggestion) {
    return typeof suggestion?.relationship_type === 'string' && suggestion.relationship_type.trim().length > 0;
}

function normalizeString(value) {
    if (typeof value !== 'string') {
        return '';
    }
    return value.trim();
}

function getSuggestionDedupeKey(suggestion) {
    const entityType = normalizeString(suggestion?.entity_type).toLowerCase();
    const entitySubtype = normalizeString(suggestion?.entity_subtype).toLowerCase();
    const name = normalizeString(suggestion?.name).toLowerCase();
    const dueDate = normalizeString(suggestion?.due_date).toLowerCase();
    const noteDate = normalizeString(suggestion?.note_date).toLowerCase();
    if (entityType.length === 0 || name.length === 0) {
        throw new Error('Suggestion must contain entity_type and name');
    }
    return `${entityType}|${entitySubtype}|${name}|${dueDate}|${noteDate}`;
}

function normalizeAnalyzeResponse(analysis) {
    if (!analysis || typeof analysis !== 'object') {
        throw new Error('Analyze response must be object');
    }
    const entities = Array.isArray(analysis.entities) ? analysis.entities : [];
    const relationships = Array.isArray(analysis.relationships) ? analysis.relationships : [];
    return {
        ...analysis,
        entities,
        relationships,
    };
}

const baseStore = new BaseStore('crm', {
    namespaces: {
        list: [],
        templates: [],
        templateDetails: null,
        schemaOptions: null,
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
        noteSummaries: {},
        draftByNoteId: {},
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
        const validViews = ['notes', 'entities', 'graph', 'tasks', 'calendar', 'settings'];
        
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
    
    async loadNotes(crmApi, options = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        baseStore.setState({ loading: true });
        
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        if (options !== null && typeof options !== 'object') {
            throw new Error('loadNotes options must be object');
        }
        const params = {
            entity_type: 'note',
            limit: typeof options.limit === 'number' ? options.limit : 300,
        };
        if (namespaceName) {
            params.namespace = namespaceName;
        }
        if (typeof options.entitySubtype === 'string' && options.entitySubtype.trim().length > 0) {
            params.entity_subtype = options.entitySubtype.trim();
        }
        if (typeof options.dateFrom === 'string' && options.dateFrom.trim().length > 0) {
            params.date_from = options.dateFrom.trim();
        }
        if (typeof options.dateTo === 'string' && options.dateTo.trim().length > 0) {
            params.date_to = options.dateTo.trim();
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
        const prevCurrentNoteId = baseStore.state.entities.currentNoteId;
        
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
                entities: {
                    ...s.entities,
                    notes: prevNotes,
                    currentNoteId: prevCurrentNoteId,
                },
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
    
    async analyzeText(crmApi, text, noteId = null, options = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!text) {
            throw new Error('Text is required');
        }
        if (options !== null && typeof options !== 'object') {
            throw new Error('Analyze options must be object');
        }

        baseStore.setState((s) => ({
            ai: { ...s.ai, analyzing: true }
        }));

        try {
            const fallbackMentionedEntityIds = baseStore.state.ai.mentionedEntities
                .map((entity) => entity?.entity_id)
                .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
            const analyzeOptions = {
                ...options,
                ...(Array.isArray(options.mentionedEntityIds) ? {} : { mentionedEntityIds: fallbackMentionedEntityIds }),
                ...(typeof options.namespace === 'string'
                    ? {}
                    : { namespace: this._getCurrentNamespaceName() }),
            };
            const analyzeResponse = await crmApi.analyzeText(text, noteId, analyzeOptions);
            const analysis = normalizeAnalyzeResponse(analyzeResponse);

            const suggestions = [
                ...analysis.entities,
                ...analysis.relationships,
            ];

            const noteSummaryText = typeof analysis?.note?.description === 'string' ? analysis.note.description.trim() : '';
            const noteSummaryEntities = Array.isArray(analysis?.entities)
                ? analysis.entities
                    .map((entity) => (typeof entity?.name === 'string' ? entity.name.trim() : ''))
                    .filter((name) => name.length > 0)
                    .slice(0, 8)
                : [];
            const noteSummaryGeneratedAt = new Date().toISOString();

            if (noteId) {
                const state = baseStore.state;
                const note = state.entities.notes.find((item) => item.entity_id === noteId);
                if (!note) {
                    throw new Error(`Note not found for summary update: ${noteId}`);
                }

                const currentAttributes = note.attributes && typeof note.attributes === 'object'
                    ? note.attributes
                    : {};
                const nextAttributes = {
                    ...currentAttributes,
                    ai_analysis_draft: {
                        note: analysis?.note || null,
                        entities: analysis.entities,
                        relationships: analysis.relationships,
                        saved_at: noteSummaryGeneratedAt,
                    },
                };
                if (noteSummaryText.length > 0) {
                    nextAttributes.ai_summary = noteSummaryText;
                    nextAttributes.ai_summary_entities = noteSummaryEntities;
                    nextAttributes.ai_summary_generated_at = noteSummaryGeneratedAt;
                }

                const updatedNote = await crmApi.updateEntity(noteId, {
                    attributes: nextAttributes,
                });

                baseStore.setState((s) => ({
                    entities: {
                        ...s.entities,
                        notes: s.entities.notes.map((item) => (
                            item.entity_id === noteId ? updatedNote : item
                        )),
                    },
                    ai: {
                        ...s.ai,
                        suggestions,
                        noteSummaries: {
                            ...s.ai.noteSummaries,
                            ...(noteSummaryText.length > 0
                                ? {
                                    [noteId]: {
                                        summary: noteSummaryText,
                                        entities: noteSummaryEntities,
                                        generated_at: noteSummaryGeneratedAt,
                                    },
                                }
                                : {}),
                        },
                        draftByNoteId: {
                            ...s.ai.draftByNoteId,
                            [noteId]: {
                                note: analysis?.note || null,
                                entities: analysis.entities,
                                relationships: analysis.relationships,
                                saved_at: noteSummaryGeneratedAt,
                            },
                        },
                    },
                }));
                return analysis;
            }

            baseStore.setState((s) => ({
                ai: {
                    ...s.ai,
                    suggestions,
                }
            }));

            return analysis;
        } finally {
            baseStore.setState((s) => ({
                ai: { ...s.ai, analyzing: false }
            }));
        }
    },

    openNoteAnalysisDraft(noteId) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        const note = baseStore.state.entities.notes.find((item) => item.entity_id === noteId);
        if (!note) {
            throw new Error(`Note not found: ${noteId}`);
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            throw new Error('Note attributes are required');
        }
        const draft = attrs.ai_analysis_draft;
        if (!draft || typeof draft !== 'object') {
            throw new Error('AI draft is not available for this note');
        }
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const draftRelationships = Array.isArray(draft.relationships) ? draft.relationships : [];
        const suggestions = [...draftEntities, ...draftRelationships];
        baseStore.setState((s) => ({
            entities: { ...s.entities, currentNoteId: noteId },
            ai: {
                ...s.ai,
                suggestions,
                draftByNoteId: {
                    ...s.ai.draftByNoteId,
                    [noteId]: draft,
                },
            },
        }));
        return draft;
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

    _getCurrentNamespaceName() {
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);
        return namespaceName || 'default';
    },

    _buildEntityPayloadFromSuggestion(suggestion) {
        if (!suggestion || typeof suggestion !== 'object') {
            throw new Error('Suggestion must be object');
        }
        const name = normalizeString(suggestion.name);
        if (name.length === 0) {
            throw new Error('Suggestion name is required');
        }
        const entityType = normalizeString(suggestion.entity_type);
        if (entityType.length === 0) {
            throw new Error('Suggestion entity_type is required');
        }
        return {
            entity_type: entityType,
            entity_subtype: suggestion.entity_subtype || null,
            name,
            description: suggestion.description || null,
            attributes: suggestion.attributes || {},
            note_date: suggestion.note_date || null,
            due_date: suggestion.due_date || null,
            priority: suggestion.priority || null,
            assignees: suggestion.assignees || [],
            namespace: this._getCurrentNamespaceName(),
        };
    },

    async _createRelationshipIfMissing(crmApi, relationshipPayload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!relationshipPayload || typeof relationshipPayload !== 'object') {
            throw new Error('relationship payload is required');
        }
        const sourceId = normalizeString(relationshipPayload.source_entity_id);
        const targetId = normalizeString(relationshipPayload.target_entity_id);
        const relationshipType = normalizeString(relationshipPayload.relationship_type);
        if (sourceId.length === 0 || targetId.length === 0 || relationshipType.length === 0) {
            throw new Error('Relationship source, target and type are required');
        }

        const existingRelationshipsResponse = await crmApi.getEntityRelationships(sourceId);
        if (!existingRelationshipsResponse || typeof existingRelationshipsResponse !== 'object') {
            throw new Error('Entity relationships response must be object');
        }
        const existingRelationships = Array.isArray(existingRelationshipsResponse.relationships)
            ? existingRelationshipsResponse.relationships
            : [];
        const alreadyExists = existingRelationships.some((item) => (
            item
            && item.source_entity_id === sourceId
            && item.target_entity_id === targetId
            && item.relationship_type === relationshipType
        ));
        if (alreadyExists) {
            return null;
        }
        return crmApi.createRelationship({
            source_entity_id: sourceId,
            target_entity_id: targetId,
            relationship_type: relationshipType,
            weight: relationshipPayload.weight || 1.0,
            attributes: relationshipPayload.attributes || {},
        });
    },

    async _linkEntityToCurrentNoteIfNeeded(crmApi, entity) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity is required');
        }
        const currentNoteId = baseStore.state.entities.currentNoteId;
        if (!currentNoteId || entity.entity_type === 'note') {
            return;
        }
        await this._createRelationshipIfMissing(crmApi, {
            source_entity_id: currentNoteId,
            target_entity_id: entity.entity_id,
            relationship_type: 'mentions',
            weight: 1.0,
        });
    },

    async _clearNoteAnalysisDraft(crmApi, noteId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!noteId) {
            return;
        }
        const note = baseStore.state.entities.notes.find((item) => item.entity_id === noteId);
        if (!note) {
            throw new Error(`Note not found for draft cleanup: ${noteId}`);
        }
        const attributes = note.attributes && typeof note.attributes === 'object'
            ? { ...note.attributes }
            : {};
        if (!Object.prototype.hasOwnProperty.call(attributes, 'ai_analysis_draft')) {
            return;
        }
        delete attributes.ai_analysis_draft;
        const updatedNote = await crmApi.updateEntity(noteId, { attributes });
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                notes: s.entities.notes.map((item) => (
                    item.entity_id === noteId ? updatedNote : item
                )),
            },
            ai: {
                ...s.ai,
                draftByNoteId: Object.fromEntries(
                    Object.entries(s.ai.draftByNoteId).filter(([key]) => key !== noteId)
                ),
            },
        }));
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
        if (isRelationshipSuggestion(suggestion)) {
            throw new Error('Use confirmRelationship for relationships');
        }

        const isMergeSuggestion = suggestion?.dedup_action === 'merge'
            && typeof suggestion?.dedup_existing_id === 'string'
            && suggestion.dedup_existing_id.trim().length > 0;

        let entity = null;
        if (isMergeSuggestion) {
            const updateData = {
                name: normalizeString(suggestion.name),
                description: suggestion.description || null,
                attributes: suggestion.attributes || {},
            };
            entity = await crmApi.updateEntity(suggestion.dedup_existing_id, updateData);
        } else {
            const payload = this._buildEntityPayloadFromSuggestion(suggestion);
            entity = await crmApi.createEntity(payload);
            await this._linkEntityToCurrentNoteIfNeeded(crmApi, entity);
        }

        const currentNoteId = baseStore.state.entities.currentNoteId;

        baseStore.setState((s) => {
            const newSuggestions = s.ai.suggestions.filter((_, i) => i !== index);
            const updatedNotes = suggestion.entity_type === 'note' && entity
                ? [entity, ...s.entities.notes]
                : s.entities.notes;
            const updatedRelated = currentNoteId && entity && entity.entity_type !== 'note'
                ? [...s.entities.noteRelatedEntities, entity].filter((value, idx, list) => (
                    list.findIndex((item) => item?.entity_id === value?.entity_id) === idx
                ))
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
        if (!isRelationshipSuggestion(suggestion)) {
            throw new Error('Not a relationship suggestion');
        }

        const relationship = await this._createRelationshipIfMissing(crmApi, {
            source_entity_id: suggestion.source_entity_id,
            target_entity_id: suggestion.target_entity_id,
            relationship_type: suggestion.relationship_type,
            weight: suggestion.weight || 1.0,
            attributes: suggestion.attributes || {},
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
            name: normalizeString(suggestion.name),
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
        let processedCount = 0;
        const createdOrUpdatedEntities = [];

        const entitySuggestions = suggestions.filter((item) => item?.entity_type && !isRelationshipSuggestion(item));
        const uniqueEntitySuggestions = [];
        const seenKeys = new Set();
        for (const suggestion of entitySuggestions) {
            const isMergeSuggestion = suggestion?.dedup_action === 'merge'
                && typeof suggestion?.dedup_existing_id === 'string'
                && suggestion.dedup_existing_id.trim().length > 0;
            if (isMergeSuggestion) {
                uniqueEntitySuggestions.push(suggestion);
                continue;
            }
            const dedupeKey = getSuggestionDedupeKey(suggestion);
            if (seenKeys.has(dedupeKey)) {
                continue;
            }
            seenKeys.add(dedupeKey);
            uniqueEntitySuggestions.push(suggestion);
        }

        for (const suggestion of uniqueEntitySuggestions) {
            const isMergeSuggestion = suggestion?.dedup_action === 'merge'
                && typeof suggestion?.dedup_existing_id === 'string'
                && suggestion.dedup_existing_id.trim().length > 0;
            let entity = null;
            if (isMergeSuggestion) {
                entity = await crmApi.updateEntity(suggestion.dedup_existing_id, {
                    name: normalizeString(suggestion.name),
                    description: suggestion.description || null,
                    attributes: suggestion.attributes || {},
                });
            } else {
                const payload = this._buildEntityPayloadFromSuggestion(suggestion);
                entity = await crmApi.createEntity(payload);
                await this._linkEntityToCurrentNoteIfNeeded(crmApi, entity);
            }
            createdOrUpdatedEntities.push(entity);
            processedCount++;
        }

        const relationships = suggestions.filter((item) => isRelationshipSuggestion(item));
        const relationshipKeys = new Set();
        for (const suggestion of relationships) {
            const sourceId = normalizeString(suggestion.source_entity_id);
            const targetId = normalizeString(suggestion.target_entity_id);
            const typeId = normalizeString(suggestion.relationship_type);
            if (sourceId.length === 0 || targetId.length === 0 || typeId.length === 0) {
                continue;
            }
            const relationKey = `${sourceId}|${targetId}|${typeId}`;
            if (relationshipKeys.has(relationKey)) {
                continue;
            }
            relationshipKeys.add(relationKey);
            await this._createRelationshipIfMissing(crmApi, {
                source_entity_id: sourceId,
                target_entity_id: targetId,
                relationship_type: typeId,
                weight: suggestion.weight || 1.0,
                attributes: suggestion.attributes || {},
            });
            processedCount++;
        }

        baseStore.setState((s) => ({
            ai: { ...s.ai, suggestions: [] },
            entities: {
                ...s.entities,
                noteRelatedEntities: currentNoteId
                    ? [...s.entities.noteRelatedEntities, ...createdOrUpdatedEntities]
                        .filter((value, idx, list) => list.findIndex((item) => item?.entity_id === value?.entity_id) === idx)
                    : s.entities.noteRelatedEntities,
            },
        }));

        await this.loadNotes(crmApi);
        await this.loadEntities(crmApi);
        await this._clearNoteAnalysisDraft(crmApi, currentNoteId);

        return processedCount;
    },

    async loadEntityTypes(crmApi, namespace = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        const response = namespace
            ? await crmApi.getEntityTypesByNamespace(namespace)
            : await crmApi.getEntityTypes();
        const types = normalizeEntityTypeList(response);
        baseStore.setState((s) => ({
            entities: { ...s.entities, entityTypes: types }
        }));
        return types;
    },
    
    async loadRelationshipTypes(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        
        const response = await crmApi.getRelationshipTypes();
        const types = normalizeRelationshipTypeList(response);
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
                templates: s.namespaces.templates,
                templateDetails: s.namespaces.templateDetails,
                schemaOptions: s.namespaces.schemaOptions,
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

    async createNamespace(crmApi, name, description = null, templateId = null) {
        return await this.createNamespaceFromTemplate(crmApi, name, templateId, description);
    },

    async loadNamespaceTemplates(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const templates = await crmApi.getNamespaceTemplates();
        if (!Array.isArray(templates)) {
            throw new Error('Namespace templates payload must be array');
        }
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                templates,
                templateDetails: s.namespaces.templateDetails,
            }
        }));
        return templates;
    },

    async loadNamespaceTemplateDetails(crmApi, templateId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!templateId) {
            throw new Error('Template ID is required');
        }
        const details = await crmApi.getNamespaceTemplate(templateId);
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                templateDetails: details,
            }
        }));
        return details;
    },

    async loadTemplateSchemaOptions(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const schemaOptions = await crmApi.getTemplateSchemaOptions();
        if (!schemaOptions || typeof schemaOptions !== 'object') {
            throw new Error('Template schema options must be object');
        }
        if (!Array.isArray(schemaOptions.field_types)) {
            throw new Error('field_types must be array');
        }
        if (!Array.isArray(schemaOptions.enum_sets)) {
            throw new Error('enum_sets must be array');
        }
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                schemaOptions,
            }
        }));
        return schemaOptions;
    },

    async createNamespaceTemplate(crmApi, payload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const created = await crmApi.createNamespaceTemplate(payload);
        await this.loadNamespaceTemplates(crmApi);
        return created;
    },

    async updateNamespaceTemplate(crmApi, templateId, payload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const updated = await crmApi.updateNamespaceTemplate(templateId, payload);
        await this.loadNamespaceTemplates(crmApi);
        const current = baseStore.state.namespaces.templateDetails;
        if (current && current.template_id === templateId) {
            await this.loadNamespaceTemplateDetails(crmApi, templateId);
        }
        return updated;
    },

    async upsertNamespaceTemplateType(crmApi, templateId, payload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const item = await crmApi.upsertNamespaceTemplateType(templateId, payload);
        await this.loadNamespaceTemplateDetails(crmApi, templateId);
        return item;
    },

    async deleteNamespaceTemplateType(crmApi, templateId, typeId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        await crmApi.deleteNamespaceTemplateType(templateId, typeId);
        await this.loadNamespaceTemplateDetails(crmApi, templateId);
    },

    async createNamespaceFromTemplate(crmApi, name, templateId, description = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!name) {
            throw new Error('Namespace name is required');
        }
        if (!templateId) {
            throw new Error('Template ID is required');
        }

        const namespace = await crmApi.createNamespace(name, description, templateId);

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

    getAllowedEntityTypesForCurrentNamespace() {
        const namespace = this._getCurrentNamespaceName();
        return (baseStore.state.entities.entityTypes || []).filter((type) => {
            const namespaceIds = Array.isArray(type?.namespace_ids) ? type.namespace_ids : [];
            return namespaceIds.includes(namespace);
        });
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

    async getEntityById(crmApi, entityId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        const entity = await crmApi.getEntity(entityId);
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity must be object');
        }
        if (typeof entity.entity_id !== 'string' || entity.entity_id.trim().length === 0) {
            throw new Error('entity_id is required');
        }

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                currentEntityId: entity.entity_id,
                currentEntity: entity,
            }
        }));

        return entity;
    },

    async uploadEntityAttachment(crmApi, entityId, file) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!(file instanceof File)) {
            throw new Error('File is required');
        }

        await crmApi.uploadAttachment(entityId, file);
        return await this.loadEntityCard(crmApi, entityId);
    },

    async deleteEntityAttachment(crmApi, entityId, attachmentId) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }
        if (!attachmentId) {
            throw new Error('Attachment ID is required');
        }

        await crmApi.deleteAttachment(entityId, attachmentId);
        return await this.loadEntityCard(crmApi, entityId);
    },

    async deleteRelationshipById(crmApi, relationshipId, linkedEntityId = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!relationshipId) {
            throw new Error('Relationship ID is required');
        }

        await crmApi.deleteRelationship(relationshipId);
        if (!linkedEntityId) {
            return null;
        }

        return await this.loadEntityCard(crmApi, linkedEntityId);
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
