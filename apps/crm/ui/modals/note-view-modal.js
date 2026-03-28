import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { CRMStore } from '../store/crm.store.js';
import './entity-modal.js';
import './share-modal.js';
import './ai-analysis-modal.js';
import '../components/note-content.js';

export class NoteViewModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        note: { type: Object },
        startInEditMode: { type: Boolean },
        draftMode: { type: Boolean },
        _relatedEntities: { state: true },
        _relationships: { state: true },
        _entityTypes: { state: true },
        _relationshipTypes: { state: true },
        _processingEntities: { state: true },
        _deleting: { state: true },
        _editing: { state: true },
        _savingNote: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .note-view-shell {
                display: flex;
                height: 100%;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: 8px;
            }

            .note-view-shell > note-content {
                flex: 1;
                min-height: 0;
            }

            @media (max-width: 767px) {
                .note-view-shell {
                    padding: 4px 0 8px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.note = null;
        this.startInEditMode = false;
        this.draftMode = false;
        this._relatedEntities = [];
        this._relationships = [];
        this._entityTypes = [];
        this._relationshipTypes = [];
        this._processingEntities = false;
        this._deleting = false;
        this._editing = false;
        this._savingNote = false;
    }

    renderHeader() {
        return this._editing ? 'Редактирование заметки' : 'Просмотр заметки';
    }

    async firstUpdated() {
        super.firstUpdated?.();
        this._editing = this.startInEditMode === true;
        await this._loadEntityTypes();
        await this._loadRelationshipTypes();
        await this._loadRelatedEntities();
    }

    async _loadEntityTypes() {
        const crmApi = this.services.get('crmApi');
        const types = await CRMStore.loadEntityTypes(crmApi);
        if (!Array.isArray(types)) {
            throw new Error('Entity types must be array');
        }
        this._entityTypes = types;
    }

    async _loadRelationshipTypes() {
        const crmApi = this.services.get('crmApi');
        const types = await CRMStore.loadRelationshipTypes(crmApi);
        if (!Array.isArray(types)) {
            throw new Error('Relationship types must be array');
        }
        this._relationshipTypes = types;
    }

    async _loadRelatedEntities() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        if (this.draftMode) {
            this._relatedEntities = [];
            this._relationships = [];
            return;
        }
        if (typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        const crmApi = this.services.get('crmApi');
        const card = await crmApi.getEntityCard(this.note.entity_id);
        if (!card || !Array.isArray(card.related_entities) || !Array.isArray(card.relationships)) {
            throw new Error('Entity card must contain related_entities and relationships arrays');
        }
        this._relatedEntities = card.related_entities;
        this._relationships = card.relationships;
    }

    async _openEntityModal(event) {
        const detail = event.detail;
        if (!detail || typeof detail !== 'object' || !detail.entity || typeof detail.entity !== 'object') {
            throw new Error('entity-open payload is required');
        }
        const entityPayload = detail.entity;
        if (typeof entityPayload.entity_id !== 'string' || entityPayload.entity_id.trim().length === 0) {
            throw new Error('Entity ID is required');
        }

        const crmApi = this.services.get('crmApi');
        const entity = await crmApi.getEntity(entityPayload.entity_id);
        if (!entity || typeof entity !== 'object') {
            throw new Error('Entity must be object');
        }
        if (typeof entity.entity_id !== 'string' || entity.entity_id.trim().length === 0) {
            throw new Error('Loaded entity must contain entity_id');
        }

        CRMStore.setCurrentEntity(entity.entity_id);
        const modal = document.createElement('entity-modal');
        modal.entityId = entity.entity_id;
        modal.entity = entity;
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    _openShareModal() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const shareModal = document.createElement('share-modal');
        shareModal.entityId = this.note.entity_id;
        shareModal.shareType = 'user';
        document.body.appendChild(shareModal);
        shareModal.showModal();
        shareModal.addEventListener('close', () => shareModal.remove());
    }

    async _refreshEntitiesFromNote() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const noteText = this.note.description;
        if (typeof noteText !== 'string' || noteText.trim().length === 0) {
            throw new Error('Note description is required for analysis');
        }

        this._processingEntities = true;
        const analysisModal = document.createElement('ai-analysis-modal');
        analysisModal.loading = true;
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
        try {
            const crmApi = this.services.get('crmApi');
            CRMStore.setCurrentNote(this.note.entity_id);
            await CRMStore.analyzeText(crmApi, noteText, this.note.entity_id);
        } finally {
            this._processingEntities = false;
            analysisModal.loading = false;
        }

        this._syncNoteFromStore();
        analysisModal.addEventListener('saved', async () => {
            this._syncNoteFromStore();
            await this._loadRelatedEntities();
        });
    }

    _openAnalysisDraftModal() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        CRMStore.openNoteAnalysisDraft(this.note.entity_id);
        const analysisModal = document.createElement('ai-analysis-modal');
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
        analysisModal.addEventListener('saved', async () => {
            this._syncNoteFromStore();
            await this._loadRelatedEntities();
        });
    }

    async _deleteNote() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        if (this.draftMode) {
            this.close();
            return;
        }
        if (typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }

        this._deleting = true;
        try {
            const crmApi = this.services.get('crmApi');
            await CRMStore.deleteNote(crmApi, this.note.entity_id);
        } finally {
            this._deleting = false;
        }
        this.close();
    }

    _handleShareNote() {
        this._openShareModal();
    }

    async _handleSummaryRefresh() {
        await this._refreshEntitiesFromNote();
    }

    _handleOpenAnalysisDraft() {
        this._openAnalysisDraftModal();
    }

    async _handleDeleteNote() {
        await this._deleteNote();
    }

    _handleEditNote() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        this._editing = true;
    }

    _handleCancelEdit() {
        if (this.draftMode) {
            this.close();
            return;
        }
        this._editing = false;
        this._syncNoteFromStore();
    }

    async _handleSaveNote(event) {
        const detail = event.detail;
        if (!detail || typeof detail !== 'object') {
            throw new Error('save-note payload is required');
        }
        const noteName = detail.name;
        if (typeof noteName !== 'string' || noteName.trim().length === 0) {
            throw new Error('Note name is required');
        }
        const noteDescription = detail.description;
        if (typeof noteDescription !== 'string') {
            throw new Error('Note description must be string');
        }
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        this._savingNote = true;
        try {
            const crmApi = this.services.get('crmApi');
            if (this.draftMode) {
                const createdNote = await CRMStore.createNote(crmApi, {
                    name: noteName.trim(),
                    description: noteDescription,
                    note_date: this.note.note_date || new Date().toISOString().slice(0, 10),
                });
                this.note = createdNote;
                this.draftMode = false;
                this.dispatchEvent(new CustomEvent('note-created', {
                    detail: { noteId: createdNote.entity_id },
                    bubbles: true,
                    composed: true,
                }));
            } else {
                await CRMStore.updateNote(crmApi, this.note.entity_id, {
                    name: noteName.trim(),
                    description: noteDescription,
                });
            }
        } finally {
            this._savingNote = false;
        }
        this._syncNoteFromStore();
        this._editing = false;
        await this._loadRelatedEntities();
    }

    _syncNoteFromStore() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        if (this.draftMode) {
            return;
        }
        const currentNote = CRMStore.state.entities.notes.find((item) => item.entity_id === this.note.entity_id);
        if (!currentNote) {
            throw new Error(`Note not found in store: ${this.note.entity_id}`);
        }
        this.note = currentNote;
    }

    _getNoteSummaryText() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.ai_summary === 'string' && attrs.ai_summary.trim().length > 0) {
            return attrs.ai_summary;
        }
        return '';
    }

    _getNoteSummaryGeneratedAt() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        if (typeof attrs.ai_summary_generated_at !== 'string' || attrs.ai_summary_generated_at.trim().length === 0) {
            return '';
        }
        const parsedDate = new Date(attrs.ai_summary_generated_at);
        if (Number.isNaN(parsedDate.getTime())) {
            return '';
        }
        const hours = String(parsedDate.getHours()).padStart(2, '0');
        const minutes = String(parsedDate.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _getNoteSummaryEntities() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return [];
        }
        const summaryEntities = attrs.ai_summary_entities;
        if (!Array.isArray(summaryEntities)) {
            return [];
        }
        return summaryEntities
            .filter((item) => typeof item === 'string' && item.trim().length > 0)
            .slice(0, 8);
    }

    _hasAnalysisDraft() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return false;
        }
        return typeof attrs.ai_analysis_draft === 'object' && attrs.ai_analysis_draft !== null;
    }

    _getAnalysisDraftGeneratedAt() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        const attrs = this.note.attributes;
        if (!attrs || typeof attrs !== 'object') {
            return '';
        }
        const draft = attrs.ai_analysis_draft;
        if (!draft || typeof draft !== 'object' || typeof draft.saved_at !== 'string') {
            return '';
        }
        const parsedDate = new Date(draft.saved_at);
        if (Number.isNaN(parsedDate.getTime())) {
            return '';
        }
        const hours = String(parsedDate.getHours()).padStart(2, '0');
        const minutes = String(parsedDate.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    renderBody() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        return html`
            <div class="note-view-shell">
                <note-content
                    .note=${this.note}
                    .relatedEntities=${this._relatedEntities}
                    .relationships=${this._relationships}
                    .entityTypes=${this._entityTypes}
                    .relationshipTypes=${this._relationshipTypes}
                    .summaryText=${this._getNoteSummaryText()}
                    .summaryGeneratedAt=${this._getNoteSummaryGeneratedAt()}
                    .summaryEntities=${this._getNoteSummaryEntities()}
                    .hasAnalysisDraft=${this._hasAnalysisDraft()}
                    .analysisDraftGeneratedAt=${this._getAnalysisDraftGeneratedAt()}
                    .processingEntities=${this._processingEntities}
                    .deletingNote=${this._deleting}
                    .editable=${this._editing}
                    .savingNote=${this._savingNote}
                    .draftMode=${this.draftMode}
                    @entity-open=${this._openEntityModal}
                    @share-note=${this._handleShareNote}
                    @summary-refresh=${this._handleSummaryRefresh}
                    @open-analysis-draft=${this._handleOpenAnalysisDraft}
                    @delete-note=${this._handleDeleteNote}
                    @edit-note=${this._handleEditNote}
                    @cancel-edit-note=${this._handleCancelEdit}
                    @save-note=${this._handleSaveNote}
                ></note-content>
            </div>
        `;
    }
}

customElements.define('note-view-modal', NoteViewModal);
