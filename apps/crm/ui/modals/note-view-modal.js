import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { CRMStore } from '../store/crm.store.js';
import './entity-modal.js';
import './share-modal.js';
import './ai-analysis-modal.js';
import '../components/note-content.js';
import './note-graph-modal.js';

export class NoteViewModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        note: { type: Object },
        startInEditMode: { type: Boolean },
        draftMode: { type: Boolean },
        _relatedEntities: { state: true },
        _relationships: { state: true },
        _entityTypes: { state: true },
        _noteSubtypes: { state: true },
        _relationshipTypes: { state: true },
        _attachments: { state: true },
        _storeAnalyzingNoteId: { state: true },
        _pendingAttachmentFiles: { state: true },
        _processingAttachment: { state: true },
        _processingRelationship: { state: true },
        _deleting: { state: true },
        _editing: { state: true },
        _savingNote: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .note-view-shell {
                display: flex;
                flex-direction: column;
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

            .header-btn.graph-open-btn {
                color: var(--text-secondary);
            }

            @media (max-width: 1279px) {
                .note-view-shell {
                    height: auto;
                    min-height: 100%;
                    overflow-y: visible;
                }

                .note-view-shell > note-content {
                    flex: 0 0 auto;
                    height: auto;
                    min-height: 0;
                }
            }

            @media (max-width: 767px) {
                .note-view-shell {
                    padding: 0;
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
        this._noteSubtypes = [];
        this._relationshipTypes = [];
        this._attachments = [];
        this._storeAnalyzingNoteId = null;
        this._pendingAttachmentFiles = [];
        this._processingAttachment = false;
        this._processingRelationship = false;
        this._deleting = false;
        this._editing = false;
        this._savingNote = false;
        this._crmStoreUnsub = null;
    }

    renderHeader() {
        return this._editing
            ? this.i18n.t('note_view_modal.header_edit')
            : this.i18n.t('note_view_modal.header_view');
    }

    renderHeaderActions() {
        if (!this.note || typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            return html``;
        }
        return html`
            <button
                class="header-btn graph-open-btn"
                type="button"
                title=${this.i18n.t('note_view_modal.graph_open_title')}
                @click=${this._openNoteGraphModal}
            >
                <platform-icon name="network" size="16"></platform-icon>
            </button>
        `;
    }

    _openNoteGraphModal() {
        if (!this.note || typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required for graph');
        }
        const modal = document.createElement('note-graph-modal');
        modal.entityId = this.note.entity_id.trim();
        const onEntityOpen = (event) => {
            this._openEntityFromGraphNode(event);
        };
        modal.addEventListener('entity-open', onEntityOpen);
        modal.addEventListener('close', () => {
            modal.removeEventListener('entity-open', onEntityOpen);
            modal.remove();
        });
        document.body.appendChild(modal);
        modal.showModal();
    }

    _openEntityFromGraphNode(event) {
        const entityId = event.detail?.entityId;
        if (typeof entityId !== 'string' || entityId.trim().length === 0) {
            throw new Error('entityId is required');
        }
        return this._openEntityModal({
            detail: { entity: { entity_id: entityId.trim(), name: '' } },
        });
    }

    connectedCallback() {
        super.connectedCallback();
        const syncAnalyzingNoteId = () => {
            const aid = CRMStore.state.ai.analyzingNoteId;
            const next = typeof aid === 'string' && aid.trim().length > 0 ? aid.trim() : null;
            if (next !== this._storeAnalyzingNoteId) {
                this._storeAnalyzingNoteId = next;
            }
        };
        syncAnalyzingNoteId();
        this._crmStoreUnsub = CRMStore.subscribe(() => {
            syncAnalyzingNoteId();
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._crmStoreUnsub?.();
        this._crmStoreUnsub = null;
    }

    async firstUpdated() {
        super.firstUpdated?.();
        this._editing = this.startInEditMode === true;
        await this._loadEntityTypes();
        await this._loadRelationshipTypes();
        await this._loadRelatedEntities();
    }

    async _loadEntityTypes() {
        const crmApi = this.crmApi;
        const types = await CRMStore.loadEntityTypes(crmApi);
        if (!Array.isArray(types)) {
            throw new Error('Entity types must be array');
        }
        this._entityTypes = types;
        this._noteSubtypes = types.filter((type) => type?.parent_type_id === 'note');
    }

    async _loadRelationshipTypes() {
        const crmApi = this.crmApi;
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
            this._attachments = [];
            return;
        }
        if (typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        const crmApi = this.crmApi;
        const card = await CRMStore.loadEntityCard(crmApi, this.note.entity_id, { updateStore: false });
        if (!card) {
            this._relatedEntities = [];
            this._relationships = [];
            this._attachments = [];
            return;
        }
        if (
            !Array.isArray(card.related_entities)
            || !Array.isArray(card.relationships)
            || !Array.isArray(card.attachments)
        ) {
            throw new Error('Entity card must contain related_entities, relationships and attachments arrays');
        }
        this._relatedEntities = card.related_entities;
        this._relationships = card.relationships;
        this._attachments = card.attachments;
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

        const crmApi = this.crmApi;
        const entity = await CRMStore.getEntityById(crmApi, entityPayload.entity_id);
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

        const analysisModal = document.createElement('ai-analysis-modal');
        analysisModal.loading = true;
        document.body.appendChild(analysisModal);
        analysisModal.showModal();
        analysisModal.addEventListener('close', () => analysisModal.remove());
        try {
            const crmApi = this.crmApi;
            CRMStore.setCurrentNote(this.note.entity_id);
            const extractEntityTypes = this._entityTypes
                .map((type) => type?.type_id)
                .filter((typeId) => typeof typeId === 'string' && typeId.trim().length > 0);
            const extractRelationshipTypes = this._relationshipTypes
                .map((type) => type?.type_id)
                .filter((typeId) => typeof typeId === 'string' && typeId.trim().length > 0 && typeId !== 'linked');
            const mentionedEntityIds = this._relatedEntities
                .map((entity) => entity?.entity_id)
                .filter((entityId) => typeof entityId === 'string' && entityId.trim().length > 0);
            await CRMStore.analyzeNote(crmApi, this.note.entity_id, {
                checkDuplicates: true,
                extractEntityTypes,
                extractRelationshipTypes,
                mentionedEntityIds,
            });
        } finally {
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
            const crmApi = this.crmApi;
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
        try {
            await this._refreshEntitiesFromNote();
        } catch (error) {
            const message = error instanceof Error
                ? error.message
                : this.i18n.t('note_view_modal.err_summary_refresh');
            this.error(message);
            throw error;
        }
    }

    _handleOpenAnalysisDraft() {
        this._openAnalysisDraftModal();
    }

    async _handleDeleteNote() {
        await this._deleteNote();
    }

    async _handleUploadAttachment(event) {
        if (!event.detail || typeof event.detail !== 'object') {
            throw new Error('upload-attachment payload is required');
        }
        const file = event.detail.file;
        if (!(file instanceof File)) {
            throw new Error('Attachment file is required');
        }
        if (this.draftMode) {
            const pendingId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
            this._pendingAttachmentFiles = [
                ...this._pendingAttachmentFiles,
                { file, _pendingId: pendingId, filename: file.name, content_type: file.type },
            ];
            return;
        }
        if (!this.note || typeof this.note !== 'object' || typeof this.note.entity_id !== 'string') {
            throw new Error('Note entity_id is required');
        }
        this._processingAttachment = true;
        try {
            const crmApi = this.crmApi;
            await CRMStore.uploadEntityAttachment(crmApi, this.note.entity_id, file);
            await this._loadRelatedEntities();
        } finally {
            this._processingAttachment = false;
        }
    }

    _resolveAttachmentId(attachment) {
        const attachmentId = attachment?.attachment_id || attachment?.document_id || attachment?.id;
        if (typeof attachmentId !== 'string' || attachmentId.trim().length === 0) {
            throw new Error('Attachment id is required');
        }
        return attachmentId;
    }

    async _handleDeleteAttachment(event) {
        if (!event.detail || typeof event.detail !== 'object') {
            throw new Error('delete-attachment payload is required');
        }
        const attachment = event.detail.attachment;
        if (!attachment || typeof attachment !== 'object') {
            throw new Error('Attachment payload is required');
        }
        if (typeof attachment._pendingId === 'string') {
            this._pendingAttachmentFiles = this._pendingAttachmentFiles.filter(
                (p) => p._pendingId !== attachment._pendingId,
            );
            return;
        }
        if (!this.note || typeof this.note !== 'object' || typeof this.note.entity_id !== 'string') {
            throw new Error('Note entity_id is required');
        }
        const attachmentId = this._resolveAttachmentId(attachment);
        this._processingAttachment = true;
        try {
            const crmApi = this.crmApi;
            await CRMStore.deleteEntityAttachment(crmApi, this.note.entity_id, attachmentId);
            await this._loadRelatedEntities();
        } finally {
            this._processingAttachment = false;
        }
    }

    _resolveRelationshipId(relationship) {
        const relationshipId = relationship?.relationship_id || relationship?.id;
        if (typeof relationshipId !== 'string' || relationshipId.trim().length === 0) {
            throw new Error('Relationship id is required');
        }
        return relationshipId;
    }

    async _handleDeleteRelationship(event) {
        if (!event.detail || typeof event.detail !== 'object') {
            throw new Error('delete-relationship payload is required');
        }
        const relationship = event.detail.relationship;
        if (!relationship || typeof relationship !== 'object') {
            throw new Error('Relationship payload is required');
        }
        if (this.draftMode) {
            throw new Error('Relationship delete is not available in draft mode');
        }
        const relationshipId = this._resolveRelationshipId(relationship);
        this._processingRelationship = true;
        try {
            const crmApi = this.crmApi;
            await CRMStore.deleteRelationshipById(crmApi, relationshipId, this.note.entity_id);
            await this._loadRelatedEntities();
        } finally {
            this._processingRelationship = false;
        }
    }

    async _buildVoiceContextPayload(crmApi, detail, options) {
        if (!detail || typeof detail !== 'object') {
            throw new Error('save-note detail is required');
        }
        const isUpdate = Boolean(options && options.isUpdate);
        const out = {};
        const mode = detail.voiceMode;
        if (mode === 'none') {
            out.voice_entity_id = null;
        } else if (mode === 'self') {
            const person = await crmApi.getPersonEntitySelf();
            out.voice_entity_id = person.entity_id;
        } else if (mode === 'manual') {
            const raw = typeof detail.voiceEntityId === 'string' ? detail.voiceEntityId.trim() : '';
            if (raw.length > 0) {
                out.voice_entity_id = raw;
            } else {
                out.voice_entity_id = null;
            }
        }
        const ctx = typeof detail.contextEntityId === 'string' ? detail.contextEntityId.trim() : '';
        if (ctx.length > 0) {
            out.context_entity_id = ctx;
        } else if (isUpdate) {
            out.context_entity_id = null;
        }
        return out;
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
        const entitySubtype = detail.entitySubtype;
        if (entitySubtype !== null && typeof entitySubtype !== 'string') {
            throw new Error('Note subtype must be string or null');
        }
        const noteDate = detail.noteDate;
        if (typeof noteDate !== 'string' || noteDate.trim().length === 0) {
            throw new Error('Note date is required');
        }
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        this._savingNote = true;
        try {
            try {
                const crmApi = this.crmApi;
                if (this.draftMode) {
                    const voiceExtra = await this._buildVoiceContextPayload(crmApi, detail, { isUpdate: false });
                    const createdNote = await CRMStore.createNote(crmApi, {
                        name: noteName.trim(),
                        description: noteDescription,
                        entity_subtype: typeof entitySubtype === 'string' && entitySubtype.trim().length > 0
                            ? entitySubtype.trim()
                            : null,
                        note_date: noteDate.trim(),
                        ...voiceExtra,
                    });
                    this.note = createdNote;
                    this.draftMode = false;
                    for (const pending of this._pendingAttachmentFiles) {
                        await CRMStore.uploadEntityAttachment(crmApi, createdNote.entity_id, pending.file);
                    }
                    this._pendingAttachmentFiles = [];
                    this.dispatchEvent(new CustomEvent('note-created', {
                        detail: { noteId: createdNote.entity_id },
                        bubbles: true,
                        composed: true,
                    }));
                } else {
                    const voiceExtra = await this._buildVoiceContextPayload(crmApi, detail, { isUpdate: true });
                    await CRMStore.updateNote(crmApi, this.note.entity_id, {
                        name: noteName.trim(),
                        description: noteDescription,
                        entity_subtype: typeof entitySubtype === 'string' && entitySubtype.trim().length > 0
                            ? entitySubtype.trim()
                            : null,
                        note_date: noteDate.trim(),
                        ...voiceExtra,
                    });
                }
            } catch (error) {
                const message = error instanceof Error
                    ? error.message
                    : this.i18n.t('note_view_modal.err_save_note');
                this.error(message);
                throw error;
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
        const draft = attrs.ai_analysis_draft;
        return typeof draft === 'object'
            && draft !== null
            && typeof draft.draft_version === 'number';
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
        if (!draft || typeof draft !== 'object' || typeof draft.updated_at !== 'string') {
            return '';
        }
        const parsedDate = new Date(draft.updated_at);
        if (Number.isNaN(parsedDate.getTime())) {
            return '';
        }
        const hours = String(parsedDate.getHours()).padStart(2, '0');
        const minutes = String(parsedDate.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    _isNoteAiAnalyzing() {
        if (!this.note || typeof this.note !== 'object') {
            return false;
        }
        const id = this.note.entity_id;
        if (typeof id !== 'string' || id.trim().length === 0) {
            return false;
        }
        return this._storeAnalyzingNoteId === id.trim();
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
                    .noteSubtypes=${this._noteSubtypes}
                    .relationshipTypes=${this._relationshipTypes}
                    .attachments=${[...this._attachments, ...this._pendingAttachmentFiles]}
                    .summaryText=${this._getNoteSummaryText()}
                    .summaryGeneratedAt=${this._getNoteSummaryGeneratedAt()}
                    .summaryEntities=${this._getNoteSummaryEntities()}
                    .hasAnalysisDraft=${this._hasAnalysisDraft()}
                    .analysisDraftGeneratedAt=${this._getAnalysisDraftGeneratedAt()}
                    .processingEntities=${this._isNoteAiAnalyzing()}
                    .deletingNote=${this._deleting}
                    .editable=${this._editing}
                    .savingNote=${this._savingNote}
                    .draftMode=${this.draftMode}
                    .processingAttachment=${this._processingAttachment}
                    .processingRelationship=${this._processingRelationship}
                    @entity-open=${this._openEntityModal}
                    @share-note=${this._handleShareNote}
                    @summary-refresh=${this._handleSummaryRefresh}
                    @open-analysis-draft=${this._handleOpenAnalysisDraft}
                    @delete-note=${this._handleDeleteNote}
                    @upload-attachment=${this._handleUploadAttachment}
                    @delete-attachment=${this._handleDeleteAttachment}
                    @delete-relationship=${this._handleDeleteRelationship}
                    @edit-note=${this._handleEditNote}
                    @cancel-edit-note=${this._handleCancelEdit}
                    @save-note=${this._handleSaveNote}
                ></note-content>
            </div>
        `;
    }
}

customElements.define('note-view-modal', NoteViewModal);
