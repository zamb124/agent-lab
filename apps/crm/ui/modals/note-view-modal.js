import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { CRMStore } from '../store/crm.store.js';
import './entity-modal.js';
import './share-modal.js';
import './ai-analysis-modal.js';
import '../components/note-editor.js';
import './note-graph-modal.js';

export class NoteViewModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        note: { type: Object },
        startInEditMode: { type: Boolean },
        draftMode: { type: Boolean },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .note-view-shell {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .note-view-shell > note-editor {
                flex: 1;
                min-height: 0;
            }

            .header-btn.graph-open-btn {
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.note = null;
        this.startInEditMode = false;
        this.draftMode = false;
    }

    renderHeader() {
        if (!this.note || typeof this.note !== 'object') {
            return this.i18n.t('note_view_modal.header_view');
        }
        return this.note.name || this.i18n.t('note_page.untitled', {}, 'crm');
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
        modal.addEventListener('close', () => modal.remove());
        document.body.appendChild(modal);
        modal.showModal();
    }

    renderBody() {
        if (!this.note || typeof this.note !== 'object') {
            throw new Error('note is required');
        }
        return html`
            <div class="note-view-shell">
                <note-editor
                    .note=${this.note}
                    .draftMode=${this.draftMode}
                    .startInEditMode=${this.startInEditMode}
                    .showTitle=${false}
                    @close=${() => this.close()}
                ></note-editor>
            </div>
        `;
    }
}

customElements.define('note-view-modal', NoteViewModal);
