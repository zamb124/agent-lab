import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';
import '../modals/entity-modal.js';
import '../modals/note-view-modal.js';
import '../modals/ai-analysis-modal.js';

export class DailyNotesPage extends PlatformElement {
    static properties = {
        _notes: { state: true },
        _query: { state: true },
        _selectedDate: { state: true },
        _currentNamespace: { state: true },
        _noteEntitiesByNoteId: { state: true },
        _currentUser: { state: true },
        _summaryText: { state: true },
        _summaryEntities: { state: true },
        _summaryGeneratedAt: { state: true },
        _loadingSummary: { state: true },
        _summaryRevalidating: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .layout {
                display: grid;
                grid-template-columns: 1fr 350px;
                gap: var(--space-4);
                width: 100%;
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }

            .main-column {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            .page-header {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .section-label {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-1);
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
            }

            .title-settings {
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .top-row {
                display: grid;
                grid-template-columns: auto minmax(260px, 1fr) auto;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .toolbar-actions {
                display: flex;
                align-items: center;
                margin-left: auto;
                gap: var(--space-2);
            }

            .search-box {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-height: 44px;
                width: 100%;
            }

            .search-input {
                width: 100%;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-base);
                outline: none;
            }

            .date-input {
                min-width: 180px;
                --platform-date-picker-labeled-bg: var(--crm-surface-muted);
                --platform-date-picker-labeled-border: transparent;
                --platform-date-picker-labeled-height: 44px;
                --platform-date-picker-labeled-padding: 0 var(--space-3);
                --platform-date-picker-label-size: 11px;
                --platform-date-picker-value-size: 16px;
            }

            .cta-btn {
                min-height: 44px;
                border: none;
                border-radius: var(--radius-full);
                background: var(--crm-daily-notes-cta-bg);
                color: var(--text-inverse);
                font-size: var(--text-lg);
                font-weight: 500;
                padding: 0 var(--space-6);
                cursor: pointer;
                transition: background var(--duration-fast);
                white-space: nowrap;
            }

            .cta-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }

            .cards-scroll {
                flex: 1;
                overflow-y: auto;
                overflow-x: hidden;
                min-height: 0;
                padding-right: var(--space-2);
            }

            .cards-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 24px;
                align-content: start;
            }

            .note-card {
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                border-radius: 16px;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                min-height: 222px;
                cursor: pointer;
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }

            .note-card:hover {
                border-color: var(--crm-stroke-strong);
                background: var(--crm-surface-elevated);
            }

            .note-tags-row {
                position: relative;
                min-height: 24px;
            }

            .note-tags {
                display: flex;
                flex-wrap: nowrap;
                gap: 12px;
                min-height: 24px;
                overflow-x: auto;
                overflow-y: hidden;
                padding-right: 52px;
                scrollbar-width: none;
                -ms-overflow-style: none;
            }

            .note-tags::-webkit-scrollbar {
                display: none;
            }

            .note-tags-hint {
                position: absolute;
                top: 0;
                right: 0;
                height: 24px;
                display: inline-flex;
                align-items: center;
                padding-left: 12px;
                background: linear-gradient(90deg, rgba(0, 0, 0, 0) 0%, var(--crm-surface) 42%);
                color: var(--text-tertiary);
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.04em;
                pointer-events: none;
            }

            .note-tag {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 0 12px;
                min-height: 24px;
                font-size: 12px;
                line-height: 15px;
                border-radius: 14px;
                color: rgba(34, 34, 34, 0.95);
                font-weight: 400;
                border: none;
                cursor: pointer;
                transition: filter var(--duration-fast);
                white-space: nowrap;
                flex: 0 0 auto;
            }

            .note-tag:hover {
                filter: brightness(0.96);
            }

            .note-tag.primary {
                background: #99A6F9;
            }

            .note-tag.secondary {
                background: #FAD17A;
            }

            .note-tag.accent {
                background: #FF885C;
            }

            .note-title {
                font-size: 20px;
                line-height: 26px;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
            }

            .note-text {
                margin: 0;
                color: var(--text-primary);
                font-size: 16px;
                line-height: 20px;
            }

            .note-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                min-height: 32px;
                margin-top: auto;
            }

            .author {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                color: var(--text-primary);
                font-size: 12px;
                line-height: 15px;
            }

            .author-avatar {
                width: 32px;
                height: 32px;
                border-radius: 999px;
                overflow: hidden;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                background: var(--accent-gradient);
            }

            .author-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .author-avatar-fallback {
                color: var(--text-inverse);
                font-size: 12px;
                font-weight: 600;
                line-height: 1;
            }

            .note-footer-right {
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }

            .published-at {
                color: var(--text-tertiary);
                font-size: 12px;
                line-height: 15px;
            }

            .analyze-btn {
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                border-radius: 16px;
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }

            .analyze-btn.has-draft {
                border-color: var(--crm-button-secondary-bg);
                background: rgba(255, 136, 92, 0.18);
                color: var(--crm-button-secondary-bg);
            }

            .summary-panel {
                background: var(--crm-summary-bg);
                border-radius: var(--radius-xl);
                border: 1px solid var(--crm-summary-stroke);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                min-height: 0;
                max-height: 100%;
                overflow: hidden;
            }

            .summary-header {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }

            .summary-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: 32px;
                font-weight: 700;
                line-height: 1.05;
                background: var(--crm-summary-title-gradient);
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                margin: 0;
                min-width: 0;
                flex-wrap: nowrap;
                white-space: nowrap;
            }

            .summary-title-text {
                display: inline-block;
                min-width: 0;
                white-space: nowrap;
            }

            .summary-title-icon {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-full);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                background: var(--crm-summary-title-gradient);
                box-shadow: var(--glass-shadow-subtle);
            }

            .summary-title-icon platform-icon {
                color: var(--text-inverse);
            }

            .summary-refresh-btn {
                width: 28px;
                height: 28px;
                border-radius: var(--radius-full);
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                flex-shrink: 0;
            }

            .summary-refresh-btn:hover {
                color: var(--accent-tertiary);
            }

            .summary-refresh-icon.spinning {
                animation: summary-refresh-spin 0.9s linear infinite;
                transform-origin: center;
            }

            @keyframes summary-refresh-spin {
                from {
                    transform: rotate(0deg);
                }
                to {
                    transform: rotate(360deg);
                }
            }

            .summary-meta {
                color: var(--crm-summary-meta);
                font-size: var(--text-base);
                margin-bottom: var(--space-4);
            }

            .summary-text {
                color: var(--text-primary);
                font-size: var(--text-xl);
                line-height: 1.32;
                margin: 0;
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
            }

            .summary-tags {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }

            .summary-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                border-radius: var(--radius-full);
                padding: 7px 14px;
                background: var(--crm-summary-chip-blue-bg);
                color: var(--text-primary);
                border: none;
                font-weight: var(--font-medium);
            }

            .summary-chip.cyan {
                background: var(--crm-summary-chip-cyan-bg);
            }

            .summary-chip.orange {
                background: var(--crm-summary-chip-orange-bg);
            }

            .summary-chip.rose {
                background: var(--crm-summary-chip-rose-bg);
            }

            .empty {
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-xl);
                min-height: 200px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }

            @media (max-width: 1279px) {
                .layout {
                    grid-template-columns: 1fr;
                }
                .summary-panel {
                    min-height: 240px;
                    margin-top: 0;
                }
                .top-row {
                    grid-template-columns: 1fr;
                    align-items: stretch;
                }
                .summary-title {
                    font-size: 30px;
                }
                .summary-text {
                    font-size: var(--text-lg);
                }
                .toolbar-actions {
                    margin-left: 0;
                    justify-content: flex-start;
                }
                .date-input {
                    min-width: 0;
                    width: 100%;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._notes = [];
        this._query = '';
        this._selectedDate = new Date().toISOString().slice(0, 10);
        this._currentNamespace = null;
        this._noteEntitiesByNoteId = {};
        this._currentUser = null;
        this._summaryText = '';
        this._summaryEntities = [];
        this._summaryGeneratedAt = '';
        this._loadingSummary = false;
        this._summaryRevalidating = false;
        this._unsubscribe = null;
        this._onPlatformNotification = this._onPlatformNotification.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._notes = Array.isArray(CRMStore.state.entities.notes) ? CRMStore.state.entities.notes : [];
        this._currentNamespace = CRMStore.state.namespaces.current;
        this._unsubscribe = CRMStore.subscribe((state) => {
            this._notes = Array.isArray(state.entities.notes) ? state.entities.notes : [];
            const previousNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
            this._currentNamespace = state.namespaces.current;
            const nextNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
            if (previousNamespace !== nextNamespace) {
                this._reloadNotesForSelectedDate();
                this._loadDailySummary();
            }
            this._loadVisibleNoteEntities();
        });
        window.addEventListener('platform-notification-received', this._onPlatformNotification);
        this._reloadNotesForSelectedDate();
        this._loadDailySummary();
        this._loadCurrentUser();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        window.removeEventListener('platform-notification-received', this._onPlatformNotification);
    }

    _getCurrentNamespaceName() {
        if (!this._currentNamespace) {
            return null;
        }
        if (typeof this._currentNamespace === 'string') {
            return this._currentNamespace;
        }
        if (typeof this._currentNamespace === 'object' && typeof this._currentNamespace.name === 'string') {
            return this._currentNamespace.name;
        }
        throw new Error('Invalid namespace in daily notes state');
    }

    async _loadDailySummary(options = {}) {
        const { forceRebuild = false, waitForWsUpdate = false } = options;
        this._loadingSummary = true;
        try {
            const crmApi = this.services.get('crmApi');
            const response = await crmApi.getDailySummary(this._selectedDate, {
                forceRebuild,
                namespace: this._getCurrentNamespaceName(),
            });
            this._applySummaryPayload(response);
            if (!waitForWsUpdate) {
                this._loadingSummary = false;
            }
        } catch (error) {
            this._loadingSummary = false;
            throw error;
        }
    }

    _applySummaryPayload(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error('Daily summary response must be object');
        }
        if (typeof payload.summary !== 'string') {
            throw new Error('Daily summary response.summary must be string');
        }
        const payloadEntities = payload.entities;
        if (payloadEntities !== undefined && !Array.isArray(payloadEntities)) {
            throw new Error('Daily summary response.entities must be array when present');
        }
        this._summaryText = payload.summary;
        this._summaryEntities = Array.isArray(payloadEntities)
            ? payloadEntities.filter((entityName) => typeof entityName === 'string' && entityName.trim().length > 0)
            : [];
        this._summaryRevalidating = payload.revalidating === true;

        if (typeof payload.generated_at === 'string' && payload.generated_at.trim().length > 0) {
            this._summaryGeneratedAt = this._formatSummaryGeneratedAt(new Date(payload.generated_at));
            return;
        }
        if (payload.summary.trim().length > 0) {
            this._summaryGeneratedAt = this._formatSummaryGeneratedAt(new Date());
            return;
        }
        this._summaryGeneratedAt = '';
    }

    _normalizeNamespaceName(namespace) {
        if (!namespace) {
            return 'all';
        }
        if (typeof namespace === 'string') {
            return namespace.trim() === '' ? 'all' : namespace;
        }
        throw new Error('Invalid summary notification namespace');
    }

    _onPlatformNotification(event) {
        const notification = event.detail;
        if (!notification || notification.service !== 'crm') {
            return;
        }
        if (notification.type !== 'crm_daily_summary_updated') {
            return;
        }
        const payload = notification.data;
        if (!payload || payload.event !== 'crm.daily_summary.updated') {
            return;
        }

        const selectedNamespace = this._normalizeNamespaceName(this._getCurrentNamespaceName());
        const payloadNamespace = this._normalizeNamespaceName(payload.namespace);
        if (payloadNamespace !== selectedNamespace) {
            return;
        }
        if (payload.date !== this._selectedDate) {
            return;
        }

        this._loadingSummary = false;
        this._applySummaryPayload(payload.summary_state);
    }

    _formatSummaryGeneratedAt(date) {
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _formatTime(dateString) {
        const date = new Date(dateString);
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _getLimitedText(text, maxLength = 220) {
        if (typeof text !== 'string') {
            return '';
        }
        const normalized = text.trim();
        if (normalized.length <= maxLength) {
            return normalized;
        }
        return `${normalized.slice(0, maxLength).trimEnd()}...`;
    }

    _getNotePreviewText(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (attrs && typeof attrs === 'object' && typeof attrs.ai_summary === 'string' && attrs.ai_summary.trim().length > 0) {
            return this._getLimitedText(attrs.ai_summary, 260);
        }
        return this._getLimitedText(this._getTextValue(note.description, 'Без описания'), 220);
    }

    _getTextValue(value, defaultValue) {
        if (typeof value === 'string' && value.trim().length > 0) {
            return value;
        }
        return defaultValue;
    }

    _onSearchInput(event) {
        this._query = event.target.value;
        this._loadVisibleNoteEntities();
    }

    async _onDateChange(event) {
        this._selectedDate = event.target.value;
        await this._reloadNotesForSelectedDate();
        await this._loadDailySummary();
        await this._loadVisibleNoteEntities();
    }

    async _reloadNotesForSelectedDate() {
        const crmApi = this.services.get('crmApi');
        this._noteEntitiesByNoteId = {};
        await CRMStore.loadNotes(crmApi, {
            dateFrom: this._selectedDate,
            dateTo: this._selectedDate,
            limit: 300,
        });
    }

    async _onCreateNote() {
        const draftNote = {
            entity_id: `draft-${Date.now()}`,
            entity_type: 'note',
            entity_subtype: 'meeting',
            name: '',
            description: '',
            note_date: this._selectedDate,
            attributes: {},
        };
        this._openNoteModal(draftNote, { editable: true, draftMode: true });
    }

    async _onRefreshSummary() {
        await this._loadDailySummary({ forceRebuild: true, waitForWsUpdate: true });
    }

    async _onAnalyzeNote(note) {
        if (!note || typeof note.description !== 'string') {
            throw new Error('Note description is required for AI analysis');
        }
        if (this._hasNoteAnalysisDraft(note)) {
            this._openNoteAnalysisDraftModal(note);
            return;
        }
        const noteText = note.description.trim();
        if (!noteText) {
            throw new Error('Empty note cannot be analyzed');
        }
        CRMStore.setCurrentNote(note.entity_id);
        const analysisModal = document.createElement('ai-analysis-modal');
        analysisModal.loading = true;
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
        const crmApi = this.services.get('crmApi');
        try {
            const relatedEntities = this._getNoteEntities(note);
            const mentionedEntityIds = relatedEntities
                .map((entity) => entity?.entity_id)
                .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
            await CRMStore.analyzeText(crmApi, noteText, note.entity_id, {
                mentionedEntityIds,
                extractEntityTypes: ['note', 'task', 'person', 'organization'],
                extractRelationshipTypes: ['mentions'],
                checkDuplicates: true,
            });
        } finally {
            analysisModal.loading = false;
        }
    }

    _hasNoteAnalysisDraft(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return false;
        }
        return typeof attrs.ai_analysis_draft === 'object' && attrs.ai_analysis_draft !== null;
    }

    _openNoteAnalysisDraftModal(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        if (typeof note.entity_id !== 'string' || note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        CRMStore.openNoteAnalysisDraft(note.entity_id);
        const analysisModal = document.createElement('ai-analysis-modal');
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
    }

    _getFilteredNotes() {
        const normalizedQuery = this._query.trim().toLowerCase();
        return this._notes.filter((note) => {
            if (!normalizedQuery) {
                return true;
            }
            const inTitle = typeof note.name === 'string' && note.name.toLowerCase().includes(normalizedQuery);
            const inDescription = typeof note.description === 'string' && note.description.toLowerCase().includes(normalizedQuery);
            return inTitle || inDescription;
        });
    }

    _getSummaryChipTone(index) {
        const tones = ['blue', 'cyan', 'orange', 'rose'];
        return tones[index % tones.length];
    }

    async _loadCurrentUser() {
        const user = await this.auth.get('/api/auth/me');
        if (!user || typeof user !== 'object') {
            throw new Error('Current user payload must be object');
        }
        this._currentUser = user;
    }

    async _loadVisibleNoteEntities() {
        const filteredNotes = this._getFilteredNotes();
        const noteIds = filteredNotes
            .map((note) => note.entity_id)
            .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
        const unresolvedNoteIds = noteIds.filter(
            (entityId) => !Object.prototype.hasOwnProperty.call(this._noteEntitiesByNoteId, entityId),
        );
        if (unresolvedNoteIds.length === 0) {
            return;
        }

        const crmApi = this.services.get('crmApi');
        const relatedEntitiesById = await Promise.all(
            unresolvedNoteIds.map(async (entityId) => {
                const card = await crmApi.getEntityCard(entityId);
                if (!card || !Array.isArray(card.related_entities)) {
                    throw new Error('Entity card must contain related_entities array');
                }
                return [entityId, card.related_entities];
            }),
        );

        const next = { ...this._noteEntitiesByNoteId };
        for (const [entityId, relatedEntities] of relatedEntitiesById) {
            next[entityId] = relatedEntities;
        }
        this._noteEntitiesByNoteId = next;
    }

    _getNoteEntities(note) {
        if (!note || typeof note.entity_id !== 'string') {
            throw new Error('Note entity_id is required');
        }
        const relatedEntities = this._noteEntitiesByNoteId[note.entity_id];
        if (!Array.isArray(relatedEntities)) {
            return [];
        }
        return relatedEntities;
    }

    _getEntityTagTone(index) {
        const tones = ['primary', 'secondary', 'accent'];
        return tones[index % tones.length];
    }

    _getEntityTagIcon(entity) {
        const entityType = typeof entity?.entity_type === 'string' ? entity.entity_type : '';
        if (entityType === 'contact') {
            return 'user';
        }
        if (entityType === 'organization') {
            return 'database';
        }
        return 'folder';
    }

    _getNoteSubtypeLabel(note) {
        const subtype = typeof note?.entity_subtype === 'string' ? note.entity_subtype.trim() : '';
        if (subtype.length === 0) {
            return '';
        }
        return subtype
            .split('_')
            .filter((part) => part.length > 0)
            .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
            .join(' ');
    }

    _getAuthorName(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (attrs && typeof attrs === 'object' && typeof attrs.author_name === 'string' && attrs.author_name.trim().length > 0) {
            return attrs.author_name;
        }
        if (
            this._currentUser
            && typeof this._currentUser === 'object'
            && note.user_id === this._currentUser.user_id
            && typeof this._currentUser.name === 'string'
            && this._currentUser.name.trim().length > 0
        ) {
            return this._currentUser.name;
        }
        return 'Пользователь';
    }

    _getAuthorAvatarUrl(note) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        const attrs = note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.author_avatar_url === 'string' && attrs.author_avatar_url.trim().length > 0) {
            return attrs.author_avatar_url;
        }
        if (typeof attrs.avatar_url === 'string' && attrs.avatar_url.trim().length > 0) {
            return attrs.avatar_url;
        }
        if (
            this._currentUser
            && typeof this._currentUser === 'object'
            && note.user_id === this._currentUser.user_id
            && typeof this._currentUser.avatar_url === 'string'
            && this._currentUser.avatar_url.trim().length > 0
        ) {
            return this._currentUser.avatar_url;
        }
        return '';
    }

    _getInitials(name) {
        if (typeof name !== 'string' || name.trim().length === 0) {
            return '?';
        }
        const parts = name.trim().split(/\s+/);
        if (parts.length === 1) {
            return parts[0].slice(0, 1).toUpperCase();
        }
        return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
    }

    _openEntityModal(entity, event = null) {
        event?.stopPropagation();
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity object is required');
        }
        if (typeof entity.entity_id !== 'string' || entity.entity_id.trim().length === 0) {
            throw new Error('Entity ID is required');
        }

        CRMStore.setCurrentEntity(entity.entity_id);
        const modal = document.createElement('entity-modal');
        modal.entityId = entity.entity_id;
        modal.entity = entity;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openNoteModal(note, options = {}) {
        if (!note || typeof note !== 'object') {
            throw new Error('Note object is required');
        }
        if (typeof note.entity_id !== 'string' || note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        const modal = document.createElement('note-view-modal');
        modal.note = note;
        modal.startInEditMode = options.editable === true;
        modal.draftMode = options.draftMode === true;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('note-created', async () => {
            await this._loadVisibleNoteEntities();
            await this._loadDailySummary();
        });
    }

    render() {
        const filteredNotes = this._getFilteredNotes();
        const summaryTags = this._summaryEntities;

        return html`
            <div class="section-label">Ежедневник</div>
            <div class="top-row">
                <div class="title">
                    Ежедневник
                    <button class="title-settings" type="button" title="Настройки">
                        <platform-icon name="settings" size="18"></platform-icon>
                    </button>
                </div>
                <label class="search-box">
                    <platform-icon name="ai" size="14" colored></platform-icon>
                    <input
                        class="search-input"
                        type="text"
                        placeholder="Введите запрос"
                        .value=${this._query}
                        @input=${this._onSearchInput}
                    />
                </label>
                <div class="toolbar-actions">
                    <platform-date-picker
                        class="date-input"
                        mode="date"
                        value-format="iso"
                        label="Дата заметки"
                        .value=${this._selectedDate}
                        @change=${this._onDateChange}
                    ></platform-date-picker>
                    <button class="cta-btn" type="button" @click=${this._onCreateNote}>Добавить заметку</button>
                </div>
            </div>

            <div class="layout">
                <section class="main-column">
                    <div class="cards-scroll">
                        ${filteredNotes.length === 0 ? html`
                            <div class="empty">На выбранную дату заметок нет</div>
                        ` : html`
                            <div class="cards-grid">
                                ${filteredNotes.map((note) => html`
                                    <article class="note-card" @click=${() => this._openNoteModal(note)}>
                                        ${(() => {
                                            const relatedEntities = this._getNoteEntities(note);
                                            return html`
                                                <div class="note-tags-row">
                                                    <div class="note-tags">
                                                        ${relatedEntities.map((entity, index) => html`
                                                            <button
                                                                class="note-tag ${this._getEntityTagTone(index)}"
                                                                type="button"
                                                                title="Открыть сущность"
                                                                @click=${(event) => this._openEntityModal(entity, event)}
                                                            >
                                                                <platform-icon name=${this._getEntityTagIcon(entity)} size="12"></platform-icon>
                                                                ${this._getTextValue(entity.name, 'Entity')}
                                                            </button>
                                                        `)}
                                                    </div>
                                                    ${relatedEntities.length > 1 ? html`
                                                        <span class="note-tags-hint" aria-hidden="true">... &gt;&gt;</span>
                                                    ` : ''}
                                                </div>
                                            `;
                                        })()}
                                        <h3 class="note-title">${note.name}</h3>
                                        ${this._getNoteSubtypeLabel(note).length > 0 ? html`
                                            <p class="published-at">${this._getNoteSubtypeLabel(note)}</p>
                                        ` : ''}
                                        <p class="note-text">${this._getNotePreviewText(note)}</p>
                                        <div class="note-footer">
                                            ${(() => {
                                                const authorName = this._getAuthorName(note);
                                                const authorAvatarUrl = this._getAuthorAvatarUrl(note);
                                                return html`
                                                    <span class="author">
                                                        <span class="author-avatar">
                                                            ${authorAvatarUrl
                                                                ? html`<img src=${authorAvatarUrl} alt=${authorName} />`
                                                                : html`<span class="author-avatar-fallback">${this._getInitials(authorName)}</span>`}
                                                        </span>
                                                        ${authorName}
                                                    </span>
                                                `;
                                            })()}
                                            <div class="note-footer-right">
                                                <span class="published-at">Опубликовано в ${this._formatTime(this._getTextValue(note.updated_at, this._getTextValue(note.created_at, new Date().toISOString())))}</span>
                                                <button
                                                    class="analyze-btn ${this._hasNoteAnalysisDraft(note) ? 'has-draft' : ''}"
                                                    type="button"
                                                    @click=${(event) => { event.stopPropagation(); this._onAnalyzeNote(note); }}
                                                    title=${this._hasNoteAnalysisDraft(note) ? 'Открыть черновик AI анализа' : 'AI анализ'}
                                                >
                                                    <platform-icon name="ai" size="14" colored></platform-icon>
                                                </button>
                                            </div>
                                        </div>
                                    </article>
                                `)}
                            </div>
                        `}
                    </div>
                </section>

                <aside class="summary-panel">
                    <div class="summary-header">
                        <h3 class="summary-title">
                            <span class="summary-title-icon">
                                <platform-icon name="ai" size="24" colored></platform-icon>
                            </span>
                            <span class="summary-title-text">Daily summary</span>
                        </h3>
                        <button class="summary-refresh-btn" type="button" title="Обновить" @click=${this._onRefreshSummary} ?disabled=${this._loadingSummary}>
                            <platform-icon
                                class=${this._loadingSummary ? 'summary-refresh-icon spinning' : 'summary-refresh-icon'}
                                name="refresh"
                                size="18"
                            ></platform-icon>
                        </button>
                    </div>
                    <div class="summary-meta">
                        ${this._loadingSummary
                            ? 'Генерация...'
                            : this._summaryRevalidating
                                ? this._summaryGeneratedAt
                                    ? `Обновляется... последнее в ${this._summaryGeneratedAt}`
                                    : 'Обновляется...'
                                : this._summaryGeneratedAt
                                    ? `Сгенерировано в ${this._summaryGeneratedAt}`
                                    : 'Нет summary'}
                    </div>
                    <p class="summary-text">${this._summaryText}</p>
                    <div class="summary-tags">
                        ${summaryTags.map((tag, index) => html`
                            <span class="summary-chip ${this._getSummaryChipTone(index)}">
                                <platform-icon name="file" size="14"></platform-icon>
                                ${tag}
                            </span>
                        `)}
                    </div>
                </aside>
            </div>
        `;
    }
}

customElements.define('daily-notes-page', DailyNotesPage);
