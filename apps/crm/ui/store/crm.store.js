/**
 * CRM Store - Состояние CRM приложения
 * Доменная структура: entities, ui, ai, grants, accessRequests
 */
import { BaseStore, deepMerge } from '@platform/lib/store/BaseStore.js';

const LAST_NAMESPACE_STORAGE_KEY = 'crm:last-namespace-by-company';
const ALL_NAMESPACES_SENTINEL = '__ALL__';

const DAILY_NOTES_RANGE_PERSIST_VERSION = 2;

function formatLocalYmd(date) {
    const year = String(date.getFullYear());
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function getTodayIsoDate() {
    return formatLocalYmd(new Date());
}

/** Понедельник–воскресенье, локальный календарь (ISO-неделя). */
function getCurrentWeekRangeIso() {
    const now = new Date();
    const jsDay = now.getDay();
    const offsetMonday = jsDay === 0 ? -6 : 1 - jsDay;
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offsetMonday);
    const sunday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
    return {
        from: formatLocalYmd(monday),
        to: formatLocalYmd(sunday),
    };
}

function getUtcTodayIsoDate() {
    return new Date().toISOString().slice(0, 10);
}

function assertIsoDate(value, fieldName) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        throw new Error(`${fieldName} must be ISO date string YYYY-MM-DD`);
    }
}

function assertDailyNotesRange(range, fieldName) {
    if (!range || typeof range !== 'object' || Array.isArray(range)) {
        throw new Error(`${fieldName} must be object with from and to`);
    }
    assertIsoDate(range.from, `${fieldName}.from`);
    assertIsoDate(range.to, `${fieldName}.to`);
}

function normalizeDailyNotesRange(from, to) {
    assertIsoDate(from, 'dailyNotesRange.from');
    assertIsoDate(to, 'dailyNotesRange.to');
    if (from > to) {
        return { from: to, to: from };
    }
    return { from, to };
}

function crmPersistMerge(persistedState, currentState) {
    const merged = deepMerge(currentState, persistedState);
    const persistedUi = persistedState?.ui;
    if (persistedUi && typeof persistedUi.dailyNotesDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(persistedUi.dailyNotesDate)) {
        merged.ui = {
            ...merged.ui,
            dailyNotesRange: getCurrentWeekRangeIso(),
            dailyNotesRangePersistVersion: DAILY_NOTES_RANGE_PERSIST_VERSION,
        };
    }
    const persistedRangeVersion = persistedState?.ui?.dailyNotesRangePersistVersion;
    if (persistedRangeVersion !== DAILY_NOTES_RANGE_PERSIST_VERSION) {
        merged.ui = {
            ...merged.ui,
            dailyNotesRange: getCurrentWeekRangeIso(),
            dailyNotesRangePersistVersion: DAILY_NOTES_RANGE_PERSIST_VERSION,
        };
    }
    return merged;
}

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

function readLastNamespaceByCompany() {
    const raw = window.localStorage.getItem(LAST_NAMESPACE_STORAGE_KEY);
    if (!raw) {
        return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Invalid stored namespace map');
    }
    return parsed;
}

function writeLastNamespaceByCompany(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new Error('Stored namespace map must be object');
    }
    window.localStorage.setItem(LAST_NAMESPACE_STORAGE_KEY, JSON.stringify(payload));
}

function getCompanyIdFromList(list) {
    if (!Array.isArray(list) || list.length === 0) {
        return null;
    }
    const companyId = list[0]?.company_id;
    if (typeof companyId !== 'string' || companyId.trim().length === 0) {
        throw new Error('Namespace company_id is required');
    }
    return companyId;
}

function persistNamespaceSelection(companyId, namespaceName) {
    if (!companyId || typeof companyId !== 'string') {
        return;
    }
    const map = readLastNamespaceByCompany();
    map[companyId] = typeof namespaceName === 'string' && namespaceName.trim().length > 0
        ? namespaceName
        : ALL_NAMESPACES_SENTINEL;
    writeLastNamespaceByCompany(map);
}

function resolveStoredNamespaceSelection(list, companyId) {
    if (!companyId) {
        return null;
    }
    const map = readLastNamespaceByCompany();
    const saved = map[companyId];
    if (saved === ALL_NAMESPACES_SENTINEL) {
        return null;
    }
    if (typeof saved !== 'string' || saved.trim().length === 0) {
        return null;
    }
    return list.find((item) => item.name === saved) || null;
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

export function isRelationshipSuggestion(suggestion) {
    return typeof suggestion?.draft_relationship_id === 'string'
        && suggestion.draft_relationship_id.trim().length > 0;
}

function normalizeString(value) {
    if (typeof value !== 'string') {
        return '';
    }
    return value.trim();
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
        settingsSelected: null,
        settingsEditability: null,
        settingsLoading: false,
        settingsSaving: false,
        grants: [],
        loading: false,
    },
    entities: {
        notes: [],
        currentNoteId: null,
        noteText: '',
        noteRelatedEntities: [],
        list: [],
        nextCursor: null,
        hasMore: false,
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
            status: null,
            priority: null,
            date_from: null,
            date_to: null,
            tags: [],
            search: '',
            search_mode: 'hybrid',
            user_id: null,
        },
        entitiesLoading: false,
        loadingMore: false,
        cardLoading: false,
        entityCardNotFound: false,
        aggregate: null,
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
        notesPageSearchQuery: '',
        tasksListSearchQuery: '',
        collapsedPanels: {},
        dailyNotesRange: getCurrentWeekRangeIso(),
        dailyNotesRangePersistVersion: DAILY_NOTES_RANGE_PERSIST_VERSION,
    },
    ai: {
        suggestions: [],
        mentionedEntities: [],
        analyzing: false,
        analyzingNoteId: null,
        noteSummaries: {},
        draftByNoteId: {},
        analyzeContextNote: null,
        resolvedDraftEntityIds: {},
        importReview: null,
    },
    loading: false,
    error: null,
}, {
    persist: true,
    devtools: true,
    persistMerge: crmPersistMerge,
    partialize: (state) => ({
        namespaces: {
            current: state.namespaces.current,
        },
        ui: {
            currentView: state.ui.currentView,
            sidebarOpen: state.ui.sidebarOpen,
            collapsedPanels: state.ui.collapsedPanels,
            dailyNotesRange: state.ui.dailyNotesRange,
            dailyNotesRangePersistVersion: state.ui.dailyNotesRangePersistVersion,
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
        const validViews = ['notes', 'entities', 'graph', 'tasks', 'settings', 'templates', 'spaces', 'namespace_imports', 'relationship_types'];
        
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

    getDailyNotesRange() {
        const range = baseStore.state.ui.dailyNotesRange;
        assertDailyNotesRange(range, 'ui.dailyNotesRange');
        let { from, to } = range;
        if (from > to) {
            const normalized = normalizeDailyNotesRange(from, to);
            this.setDailyNotesRange(normalized);
            from = normalized.from;
            to = normalized.to;
        }
        const utcToday = getUtcTodayIsoDate();
        const localToday = getTodayIsoDate();
        if (from === utcToday && utcToday !== localToday && to === utcToday) {
            this.setDailyNotesRange({ from: localToday, to: localToday });
            return { from: localToday, to: localToday };
        }
        return { from, to };
    },

    /** День по умолчанию для новой заметки: конец выбранного периода. */
    getDailyNotesFocusDate() {
        return this.getDailyNotesRange().to;
    },

    setDailyNotesRange({ from, to }) {
        const normalized = normalizeDailyNotesRange(from, to);
        baseStore.setState((s) => ({
            ui: {
                ...s.ui,
                dailyNotesRange: normalized,
                dailyNotesRangePersistVersion: DAILY_NOTES_RANGE_PERSIST_VERSION,
            },
        }));
    },

    defaultDailyNotesRange() {
        return getCurrentWeekRangeIso();
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
        
        const response = await crmApi.getEntities(params);
        const notes = Array.isArray(response.items) ? response.items : [];

        baseStore.setState((s) => ({
            entities: { ...s.entities, notes },
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
        
        const ns = this._getCurrentNamespaceName();
        const response = await crmApi.findEntitiesByText(text, ns);
        const entities = response.entities || [];
        
        baseStore.setState((s) => ({
            ai: { ...s.ai, mentionedEntities: entities, analyzing: false }
        }));
        
        return entities;
    },
    
    async analyzeNote(crmApi, noteId, options = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        if (options !== null && typeof options !== 'object') {
            throw new Error('Analyze options must be object');
        }

        baseStore.setState((s) => ({
            ai: { ...s.ai, analyzing: true, analyzingNoteId: noteId }
        }));

        try {
            const fallbackMentionedEntityIds = baseStore.state.ai.mentionedEntities
                .map((entity) => entity?.entity_id)
                .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
            const analyzeOptions = {
                ...options,
                ...(Array.isArray(options.mentionedEntityIds) ? {} : { mentionedEntityIds: fallbackMentionedEntityIds }),
            };
            const analyzeResponse = await crmApi.analyzeNote(noteId, analyzeOptions);
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

            const state = baseStore.state;
            const note = state.entities.notes.find((item) => item.entity_id === noteId);
            if (!note) {
                throw new Error(`Note not found for summary update: ${noteId}`);
            }

            let noteRow = await crmApi.getEntity(noteId);
            const serverDraft = noteRow.attributes?.ai_analysis_draft;
            if (!serverDraft || typeof serverDraft.draft_version !== 'number') {
                throw new Error('Server did not persist analyze draft: expected attributes.ai_analysis_draft with draft_version');
            }

            if (noteSummaryText.length > 0) {
                const attrs = { ...(noteRow.attributes && typeof noteRow.attributes === 'object' ? noteRow.attributes : {}) };
                attrs.ai_summary = noteSummaryText;
                attrs.ai_summary_entities = noteSummaryEntities;
                attrs.ai_summary_generated_at = noteSummaryGeneratedAt;
                noteRow = await crmApi.updateEntity(noteId, { attributes: attrs });
            }

            const draftSnapshot = noteRow.attributes?.ai_analysis_draft;
            if (!draftSnapshot || typeof draftSnapshot.draft_version !== 'number') {
                throw new Error('ai_analysis_draft missing after note update');
            }

            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    notes: s.entities.notes.map((item) => (
                        item.entity_id === noteId ? noteRow : item
                    )),
                },
                ai: {
                    ...s.ai,
                    suggestions,
                    analyzeContextNote: analysis.note || null,
                    resolvedDraftEntityIds: {},
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
                        [noteId]: draftSnapshot,
                    },
                },
            }));

            return analysis;
        } finally {
            baseStore.setState((s) => ({
                ai: { ...s.ai, analyzing: false, analyzingNoteId: null }
            }));
        }
    },

    setNoteInStore(note) {
        if (!note?.entity_id) {
            throw new Error('note.entity_id is required');
        }
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                notes: s.entities.notes.map((n) =>
                    n.entity_id === note.entity_id ? note : n
                ),
            },
        }));
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
        if (typeof draft.draft_version !== 'number') {
            throw new Error('Invalid draft: expected draft_version (server schema)');
        }
        const draftEntities = Array.isArray(draft.entities) ? draft.entities : [];
        const draftRelationships = Array.isArray(draft.relationships) ? draft.relationships : [];
        const suggestions = [...draftEntities, ...draftRelationships];
        baseStore.setState((s) => ({
            entities: { ...s.entities, currentNoteId: noteId },
            ai: {
                ...s.ai,
                suggestions,
                analyzeContextNote: draft.note || null,
                resolvedDraftEntityIds: {},
                draftByNoteId: {
                    ...s.ai.draftByNoteId,
                    [noteId]: draft,
                },
            },
        }));
        return draft;
    },
    
    clearKnowledgeImportReview() {
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                importReview: null,
                suggestions: [],
                analyzeContextNote: null,
                resolvedDraftEntityIds: {},
            },
        }));
    },

    async hydrateKnowledgeImportReview(crmApi, importId, summaryPreloaded = null) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const id = typeof importId === 'string' ? importId.trim() : '';
        if (!id) {
            throw new Error('importId is required');
        }
        const summary = summaryPreloaded ?? await crmApi.getKnowledgeImportCreatedEntities(id);
        const rows = Array.isArray(summary.entities) ? summary.entities : [];
        if (rows.length === 0) {
            throw new Error('Нет сущностей для просмотра');
        }
        const full = await Promise.all(rows.map((r) => crmApi.getEntity(r.entity_id)));
        const resolvedDraftEntityIds = {};
        const suggestions = [];
        for (const ent of full) {
            if (!ent || typeof ent.entity_id !== 'string') {
                continue;
            }
            const eid = ent.entity_id;
            const kid = `ki:${eid}`;
            resolvedDraftEntityIds[kid] = eid;
            const desc = typeof ent.description === 'string' ? ent.description : '';
            const attrs = ent.attributes && typeof ent.attributes === 'object' && !Array.isArray(ent.attributes)
                ? { ...ent.attributes }
                : {};
            suggestions.push({
                entity_type: ent.entity_type,
                entity_subtype: ent.entity_subtype || undefined,
                name: ent.name,
                description: desc,
                attributes: attrs,
                draft_entity_id: kid,
                dedup_action: 'merge',
                dedup_existing_id: eid,
                dedup_existing_name: ent.name,
                dedup_confidence: 1,
            });
        }
        const anchor = full.find((e) => e && e.entity_type === 'note') || full[0];
        if (!anchor || typeof anchor.entity_id !== 'string') {
            throw new Error('Не найдена якорная сущность для просмотра');
        }
        const anchorDesc = typeof anchor.description === 'string' ? anchor.description : '';
        const analyzeContextNote = {
            draft_entity_id: `ki:${anchor.entity_id}`,
            entity_type: anchor.entity_type,
            name: anchor.name,
            description: anchorDesc,
        };
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                importReview: { importId: id, anchorNote: anchor },
                suggestions,
                analyzeContextNote,
                resolvedDraftEntityIds,
            },
        }));
    },

    async persistKnowledgeImportReview(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const pack = baseStore.state.ai.importReview;
        if (!pack || typeof pack.importId !== 'string') {
            throw new Error('Режим просмотра импорта не активен');
        }
        const importId = pack.importId;
        const suggestions = baseStore.state.ai.suggestions;
        for (const s of suggestions) {
            if (isRelationshipSuggestion(s)) {
                continue;
            }
            const entityId = typeof s.dedup_existing_id === 'string' ? s.dedup_existing_id.trim() : '';
            if (!entityId) {
                throw new Error('У строки нет entity_id');
            }
            const name = normalizeString(s.name);
            if (!name) {
                throw new Error('Имя сущности не может быть пустым');
            }
            await crmApi.updateEntity(entityId, {
                name,
                description: s.description || null,
                attributes: s.attributes && typeof s.attributes === 'object' ? s.attributes : {},
            });
        }
        await crmApi.completeKnowledgeImportReview(importId);
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                importReview: null,
                suggestions: [],
                analyzeContextNote: null,
                resolvedDraftEntityIds: {},
            },
        }));
        await this.loadNotes(crmApi);
        await this.loadEntities(crmApi);
    },

    _replaceDraftAndSuggestions(noteId, draftStored) {
        if (!noteId || !draftStored || typeof draftStored !== 'object') {
            throw new Error('draftStored is required');
        }
        const nextSuggestions = [
            ...(Array.isArray(draftStored.entities) ? draftStored.entities : []),
            ...(Array.isArray(draftStored.relationships) ? draftStored.relationships : []),
        ];
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                draftByNoteId: { ...s.ai.draftByNoteId, [noteId]: draftStored },
                suggestions: nextSuggestions,
                analyzeContextNote: draftStored.note ?? s.ai.analyzeContextNote,
            },
        }));
    },

    _buildDraftEntityIdToRealIdMap() {
        const suggestions = baseStore.state.ai.suggestions;
        const currentNoteId = baseStore.state.entities.currentNoteId;
        const ctxNote = baseStore.state.ai.analyzeContextNote;
        const resolved = baseStore.state.ai.resolvedDraftEntityIds || {};
        const map = new Map();
        if (ctxNote?.draft_entity_id && currentNoteId) {
            map.set(ctxNote.draft_entity_id, currentNoteId);
        }
        for (const s of suggestions) {
            if (!s?.entity_type || isRelationshipSuggestion(s)) {
                continue;
            }
            if (typeof s.draft_entity_id !== 'string' || s.draft_entity_id.trim().length === 0) {
                throw new Error('Each draft entity must have draft_entity_id');
            }
            if (s.dedup_action === 'merge' && typeof s.dedup_existing_id === 'string' && s.dedup_existing_id.trim().length > 0) {
                map.set(s.draft_entity_id, s.dedup_existing_id.trim());
            }
        }
        for (const [k, v] of Object.entries(resolved)) {
            if (typeof v === 'string' && v.trim().length > 0) {
                map.set(k, v.trim());
            }
        }
        return map;
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

    async removeSuggestionWithServerDraftSync(crmApi, index) {
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
        const item = suggestions[index];
        const noteId = baseStore.state.entities.currentNoteId;
        const draftPack = noteId ? baseStore.state.ai.draftByNoteId[noteId] : null;
        const canPatch = noteId && draftPack && typeof draftPack.draft_version === 'number';

        if (canPatch && isRelationshipSuggestion(item)) {
            if (typeof item.draft_relationship_id !== 'string' || item.draft_relationship_id.trim().length === 0) {
                throw new Error('Relationship suggestion missing draft_relationship_id');
            }
            const patched = await crmApi.patchNoteAnalysisDraft(noteId, {
                expected_version: draftPack.draft_version,
                remove_entity_draft_ids: [],
                remove_relationship_draft_ids: [item.draft_relationship_id],
                patch_entities: [],
                patch_relationships: [],
            });
            this._replaceDraftAndSuggestions(noteId, patched);
            const refreshedNote = await crmApi.getEntity(noteId);
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    notes: s.entities.notes.map((n) => (
                        n.entity_id === noteId ? refreshedNote : n
                    )),
                },
            }));
            return;
        }

        if (canPatch && item?.entity_type && typeof item.draft_entity_id === 'string' && item.draft_entity_id.trim().length > 0) {
            const patched = await crmApi.patchNoteAnalysisDraft(noteId, {
                expected_version: draftPack.draft_version,
                remove_entity_draft_ids: [item.draft_entity_id],
                remove_relationship_draft_ids: [],
                patch_entities: [],
                patch_relationships: [],
            });
            this._replaceDraftAndSuggestions(noteId, patched);
            const refreshedNote = await crmApi.getEntity(noteId);
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    notes: s.entities.notes.map((n) => (
                        n.entity_id === noteId ? refreshedNote : n
                    )),
                },
            }));
            return;
        }

        this.removeSuggestion(index);
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
        const draftPack = currentNoteId ? baseStore.state.ai.draftByNoteId[currentNoteId] : null;
        const hasServerDraft = draftPack && typeof draftPack.draft_version === 'number'
            && typeof suggestion.draft_entity_id === 'string'
            && suggestion.draft_entity_id.trim().length > 0;

        if (hasServerDraft) {
            const patched = await crmApi.patchNoteAnalysisDraft(currentNoteId, {
                expected_version: draftPack.draft_version,
                remove_entity_draft_ids: [suggestion.draft_entity_id],
                remove_relationship_draft_ids: [],
                patch_entities: [],
                patch_relationships: [],
            });
            this._replaceDraftAndSuggestions(currentNoteId, patched);
            const refreshedNote = await crmApi.getEntity(currentNoteId);
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    notes: s.entities.notes.map((item) => (
                        item.entity_id === currentNoteId ? refreshedNote : item
                    )),
                    noteRelatedEntities: currentNoteId && entity && entity.entity_type !== 'note'
                        ? [...s.entities.noteRelatedEntities, entity].filter((value, idx, list) => (
                            list.findIndex((item) => item?.entity_id === value?.entity_id) === idx
                        ))
                        : s.entities.noteRelatedEntities,
                },
                ai: {
                    ...s.ai,
                    resolvedDraftEntityIds: {
                        ...s.ai.resolvedDraftEntityIds,
                        [suggestion.draft_entity_id]: entity.entity_id,
                    },
                },
            }));
        } else {
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
                    ai: {
                        ...s.ai,
                        suggestions: newSuggestions,
                        resolvedDraftEntityIds: suggestion.draft_entity_id
                            ? {
                                ...s.ai.resolvedDraftEntityIds,
                                [suggestion.draft_entity_id]: entity.entity_id,
                            }
                            : s.ai.resolvedDraftEntityIds,
                    },
                    entities: {
                        ...s.entities,
                        notes: updatedNotes,
                        noteRelatedEntities: updatedRelated,
                    },
                };
            });
        }

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

        const currentNoteId = baseStore.state.entities.currentNoteId;
        const draftPack = currentNoteId ? baseStore.state.ai.draftByNoteId[currentNoteId] : null;

        const map = this._buildDraftEntityIdToRealIdMap();
        const sid = suggestion.source_draft_entity_id;
        const tid = suggestion.target_draft_entity_id;
        if (typeof sid !== 'string' || sid.trim().length === 0
            || typeof tid !== 'string' || tid.trim().length === 0) {
            throw new Error('Draft relationship requires source_draft_entity_id and target_draft_entity_id');
        }
        const sourceId = map.get(sid);
        const targetId = map.get(tid);
        if (!sourceId || !targetId) {
            throw new Error(
                'Cannot create relationship: confirm entities first or set dedup_existing_id for merge.',
            );
        }

        const relationship = await this._createRelationshipIfMissing(crmApi, {
            source_entity_id: sourceId,
            target_entity_id: targetId,
            relationship_type: suggestion.relationship_type,
            weight: typeof suggestion.weight === 'number' ? suggestion.weight : 1.0,
            attributes: suggestion.attributes || {},
        });

        if (currentNoteId && draftPack && typeof draftPack.draft_version === 'number'
            && typeof suggestion.draft_relationship_id === 'string'
            && suggestion.draft_relationship_id.trim().length > 0) {
            const patched = await crmApi.patchNoteAnalysisDraft(currentNoteId, {
                expected_version: draftPack.draft_version,
                remove_entity_draft_ids: [],
                remove_relationship_draft_ids: [suggestion.draft_relationship_id],
                patch_entities: [],
                patch_relationships: [],
            });
            this._replaceDraftAndSuggestions(currentNoteId, patched);
            const refreshedNote = await crmApi.getEntity(currentNoteId);
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    notes: s.entities.notes.map((item) => (
                        item.entity_id === currentNoteId ? refreshedNote : item
                    )),
                },
            }));
        } else {
            baseStore.setState((s) => ({
                ai: {
                    ...s.ai,
                    suggestions: s.ai.suggestions.filter((_, i) => i !== index),
                },
            }));
        }

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
        if (!currentNoteId) {
            throw new Error('Applying draft requires active note (currentNoteId)');
        }

        const draft = baseStore.state.ai.draftByNoteId[currentNoteId];
        if (!draft || typeof draft.draft_version !== 'number') {
            throw new Error('No analyze draft on server for this note; run analyze with note_id');
        }

        const { task_id } = await crmApi.applyNoteAnalysisDraft(currentNoteId);

        // Сразу очищаем локальный черновик — результат придёт через WebSocket
        baseStore.setState((s) => ({
            ai: {
                ...s.ai,
                suggestions: [],
                analyzeContextNote: null,
                resolvedDraftEntityIds: {},
                draftByNoteId: Object.fromEntries(
                    Object.entries(s.ai.draftByNoteId).filter(([key]) => key !== currentNoteId),
                ),
            },
        }));

        return task_id;
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
    
    setSearchMode(mode) {
        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                filters: { ...s.entities.filters, search_mode: mode },
            }
        }));
    },

    setNotesPageSearchQuery(query) {
        if (typeof query !== 'string') {
            throw new Error('notesPageSearchQuery must be a string');
        }
        baseStore.setState((s) => ({
            ui: { ...s.ui, notesPageSearchQuery: query },
        }));
    },

    setTasksListSearchQuery(query) {
        if (typeof query !== 'string') {
            throw new Error('tasksListSearchQuery must be a string');
        }
        baseStore.setState((s) => ({
            ui: { ...s.ui, tasksListSearchQuery: query },
        }));
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
        const currentNamespaceName = getNamespaceName(baseStore.state.namespaces.current);
        const companyId = getCompanyIdFromList(list);
        let resolvedCurrent = null;
        if (currentNamespaceName) {
            resolvedCurrent = list.find((item) => item.name === currentNamespaceName) || null;
        }
        if (!resolvedCurrent) {
            resolvedCurrent = resolveStoredNamespaceSelection(list, companyId);
        }
        const resolvedNamespaceName = getNamespaceName(resolvedCurrent);
        persistNamespaceSelection(companyId, resolvedNamespaceName);

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                list,
                templates: s.namespaces.templates,
                templateDetails: s.namespaces.templateDetails,
                schemaOptions: s.namespaces.schemaOptions,
                current: resolvedCurrent,
                settingsSelected: s.namespaces.settingsSelected,
                settingsEditability: s.namespaces.settingsEditability,
                settingsLoading: s.namespaces.settingsLoading,
                settingsSaving: s.namespaces.settingsSaving,
                loading: false
            },
            entities: {
                ...s.entities,
                filters: {
                    ...s.entities.filters,
                    namespace: resolvedNamespaceName,
                },
            }
        }));

        return list;
    },

    setCurrentNamespace(namespace) {
        const namespaceName = getNamespaceName(namespace);
        const companyId = getCompanyIdFromList(baseStore.state.namespaces.list);
        persistNamespaceSelection(companyId, namespaceName);
        baseStore.setState((s) => ({
            namespaces: { ...s.namespaces, current: namespace },
            entities: {
                ...s.entities,
                filters: { ...s.entities.filters, namespace: namespaceName },
                list: [],
                currentEntityId: null,
                currentEntity: null,
                entityCardNotFound: false,
            }
        }));
    },

    setSettingsNamespaceSelection(namespaceName) {
        if (namespaceName !== null && typeof namespaceName !== 'string') {
            throw new Error('Namespace name must be string or null');
        }
        const normalizedName = typeof namespaceName === 'string' ? namespaceName.trim() : null;
        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                settingsSelected: normalizedName,
                settingsEditability: null,
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

    async loadNamespaceEditability(crmApi, namespaceName) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!namespaceName || typeof namespaceName !== 'string') {
            throw new Error('Namespace name is required');
        }
        const normalizedName = namespaceName.trim();
        if (!normalizedName) {
            throw new Error('Namespace name is required');
        }

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                settingsLoading: true,
            }
        }));

        try {
            const payload = await crmApi.getNamespaceEditability(normalizedName);
            if (!payload || typeof payload !== 'object') {
                throw new Error('Namespace editability payload must be object');
            }

            baseStore.setState((s) => ({
                namespaces: {
                    ...s.namespaces,
                    settingsSelected: normalizedName,
                    settingsEditability: payload,
                    settingsLoading: false,
                }
            }));

            return payload;
        } catch (error) {
            baseStore.setState((s) => ({
                namespaces: {
                    ...s.namespaces,
                    settingsLoading: false,
                }
            }));
            throw error;
        }
    },

    async updateExistingNamespace(crmApi, namespaceName, payload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!namespaceName || typeof namespaceName !== 'string') {
            throw new Error('Namespace name is required');
        }
        const normalizedName = namespaceName.trim();
        if (!normalizedName) {
            throw new Error('Namespace name is required');
        }
        if (!payload || typeof payload !== 'object') {
            throw new Error('Namespace payload is required');
        }

        baseStore.setState((s) => ({
            namespaces: {
                ...s.namespaces,
                settingsSaving: true,
            }
        }));

        try {
            const updatedNamespace = await crmApi.updateNamespace(normalizedName, payload);
            await Promise.all([
                this.loadNamespaces(crmApi),
                this.loadEntityTypes(crmApi),
                this.loadNamespaceEditability(crmApi, normalizedName),
            ]);
            return updatedNamespace;
        } finally {
            baseStore.setState((s) => ({
                namespaces: {
                    ...s.namespaces,
                    settingsSaving: false,
                }
            }));
        }
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
                    status: null,
                    priority: null,
                    date_from: null,
                    date_to: null,
                    tags: [],
                    search: '',
                    search_mode: 'hybrid',
                    user_id: null,
                }
            }
        }));
    },

    _buildEntityQueryParams(params = {}) {
        const filters = baseStore.state.entities.filters;
        const currentNamespace = baseStore.state.namespaces.current;
        const namespaceName = getNamespaceName(currentNamespace);

        const queryParams = {
            entity_type: params.entity_type || filters.entity_type,
            entity_subtype: params.entity_subtype || filters.entity_subtype,
            namespace: namespaceName,
            status: filters.status,
            priority: filters.priority,
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

        return { queryParams, namespaceName };
    },

    async loadEntities(crmApi, params = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }

        baseStore.setState((s) => ({
            entities: { ...s.entities, entitiesLoading: true }
        }));

        const filters = baseStore.state.entities.filters;
        const searchTrimmed = typeof filters.search === 'string' ? filters.search.trim() : '';
        const { queryParams, namespaceName } = this._buildEntityQueryParams(params);

        let response;
        if (searchTrimmed) {
            const searchMode = filters.search_mode || 'hybrid';
            const searchParams = { ...queryParams, namespace: namespaceName, search_mode: searchMode };
            response = await crmApi.searchEntities(searchTrimmed, searchParams);
        } else {
            response = await crmApi.getEntities(queryParams);
        }

        const list = Array.isArray(response.items) ? response.items : [];

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list,
                nextCursor: response.next_cursor || null,
                hasMore: response.has_more === true,
                entitiesLoading: false,
            }
        }));

        return list;
    },

    async loadAggregate(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const ns = this._getCurrentNamespaceName();
        const params = {};
        if (ns) {
            params.namespace = ns;
        }
        const aggregate = await crmApi.getAggregate(params);
        baseStore.setState((s) => ({
            entities: { ...s.entities, aggregate }
        }));
        return aggregate;
    },

    async loadMoreEntities(crmApi) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        const { nextCursor, hasMore, loadingMore } = baseStore.state.entities;
        if (!hasMore || !nextCursor || loadingMore) {
            return;
        }

        baseStore.setState((s) => ({
            entities: { ...s.entities, loadingMore: true }
        }));

        const filters = baseStore.state.entities.filters;
        const searchTrimmed = typeof filters.search === 'string' ? filters.search.trim() : '';
        const { queryParams } = this._buildEntityQueryParams();

        let response;
        if (searchTrimmed) {
            const searchMode = filters.search_mode || 'hybrid';
            const searchParams = { ...queryParams, search_mode: searchMode };
            response = await crmApi.searchEntities(searchTrimmed, searchParams);
        } else {
            response = await crmApi.getEntities({ ...queryParams, cursor: nextCursor });
        }

        const page = Array.isArray(response.items) ? response.items : [];

        baseStore.setState((s) => ({
            entities: {
                ...s.entities,
                list: [...s.entities.list, ...page],
                nextCursor: response.next_cursor || null,
                hasMore: response.has_more === true,
                loadingMore: false,
            }
        }));
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
                entityCardNotFound: false,
            },
            grants: { ...s.grants, currentEntityGrants: [] }
        }));
        
        if (!options.skipUrl) {
            const url = entityId ? `/crm/entities/${entityId}` : '/crm/entities';
            history.pushState({}, '', url);
        }
    },

    async loadEntityCard(crmApi, entityId, options = {}) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!entityId) {
            throw new Error('Entity ID is required');
        }

        const updateStore = options.updateStore !== false;

        if (updateStore) {
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    cardLoading: true,
                    entityCardNotFound: false,
                }
            }));
        }

        const card = await crmApi.getEntityCardIfPresent(entityId);

        if (!card) {
            if (updateStore) {
                baseStore.setState((s) => ({
                    entities: {
                        ...s.entities,
                        currentEntity: null,
                        currentEntityRelated: [],
                        cardLoading: false,
                        entityCardNotFound: true,
                    }
                }));
            }
            return null;
        }

        if (updateStore) {
            baseStore.setState((s) => ({
                entities: {
                    ...s.entities,
                    currentEntity: card.entity,
                    currentEntityRelated: card.related_entities || [],
                    cardLoading: false,
                    entityCardNotFound: false,
                }
            }));
        }

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
                entityCardNotFound: false,
            }
        }));

        return entity;
    },

    async mergeEntities(crmApi, payload) {
        if (!crmApi) {
            throw new Error('crmApi service is required');
        }
        if (!payload || typeof payload !== 'object') {
            throw new Error('Merge payload is required');
        }

        const result = await crmApi.mergeEntities(payload);
        const survivor = result.entity;
        const mergedFromId = result.merged_from_entity_id;
        const survivorId = survivor.entity_id;

        baseStore.setState((s) => {
            const listWithout = s.entities.list.filter((e) => e.entity_id !== mergedFromId);
            const hasSurvivor = listWithout.some((e) => e.entity_id === survivorId);
            const nextList = hasSurvivor
                ? listWithout.map((e) => (e.entity_id === survivorId ? survivor : e))
                : [...listWithout, survivor];

            let nextCurrentId = s.entities.currentEntityId;
            if (nextCurrentId === mergedFromId) {
                nextCurrentId = survivorId;
            }

            let nextCurrentEntity = s.entities.currentEntity;
            if (nextCurrentEntity && nextCurrentEntity.entity_id === mergedFromId) {
                nextCurrentEntity = survivor;
            } else if (nextCurrentEntity && nextCurrentEntity.entity_id === survivorId) {
                nextCurrentEntity = survivor;
            }

            return {
                entities: {
                    ...s.entities,
                    list: nextList,
                    currentEntityId: nextCurrentId,
                    currentEntity: nextCurrentEntity,
                    entityCardNotFound: false,
                },
            };
        });

        return result;
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
                entityCardNotFound: false,
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
