import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { CRMStore } from '../store/crm.store.js';
import './entity-modal.js';
import '../components/note-content.js';

export class NoteViewModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        note: { type: Object },
        summaryText: { type: String },
        summaryGeneratedAt: { type: String },
        summaryEntities: { type: Array },
        _relatedEntities: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .note-view-shell {
                height: 100%;
                min-height: 0;
                overflow-y: auto;
                overflow-x: hidden;
                padding: 8px;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.note = null;
        this.summaryText = '';
        this.summaryGeneratedAt = '';
        this.summaryEntities = [];
        this._relatedEntities = [];
    }

    renderHeader() {
        return 'Просмотр заметки';
    }

    async firstUpdated() {
        super.firstUpdated?.();
        await this._loadRelatedEntities();
    }

    async _loadRelatedEntities() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        if (typeof this.note.entity_id !== 'string' || this.note.entity_id.trim().length === 0) {
            throw new Error('Note entity_id is required');
        }
        const crmApi = this.services.get('crmApi');
        const card = await crmApi.getEntityCard(this.note.entity_id);
        if (!card || !Array.isArray(card.related_entities)) {
            throw new Error('Entity card must contain related_entities array');
        }
        this._relatedEntities = card.related_entities;
    }

    _openEntityModal(event) {
        const detail = event.detail;
        if (!detail || typeof detail !== 'object' || !detail.entity || typeof detail.entity !== 'object') {
            throw new Error('entity-open payload is required');
        }
        const entity = detail.entity;
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

    renderBody() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        return html`
            <div class="note-view-shell">
                <note-content
                    .note=${this.note}
                    .relatedEntities=${this._relatedEntities}
                    .summaryText=${this.summaryText}
                    .summaryGeneratedAt=${this.summaryGeneratedAt}
                    .summaryEntities=${this.summaryEntities}
                    @entity-open=${this._openEntityModal}
                ></note-content>
            </div>
        `;
    }
}

customElements.define('note-view-modal', NoteViewModal);
