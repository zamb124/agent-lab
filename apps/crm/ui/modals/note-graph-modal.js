/**
 * CRMNoteGraphModal — мини-граф связей вокруг конкретной заметки.
 *
 * Props:
 *   - noteId: string — обязательный, id заметки.
 *
 * Поток:
 *   1. На open `entitiesResource.get(noteId)` подгружает имя заметки в шапку.
 *   2. Тело — `<crm-mini-graph-preview entity-id=noteId>`, компонент сам
 *      загружает граф через `useOp('crm/influence_graph')` и рендерит 3D-сцену.
 *   3. Клик по сущности в графе — `entity-open` событие → close модалку и
 *      navigate('entity', { itemId }).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/mini-graph-preview.js';

const ENTITIES_NAME = 'crm/entities';

export class CRMNoteGraphModal extends PlatformModal {
    static modalKind = 'crm.note_graph';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        noteId: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .body {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 480px;
                height: 60vh;
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .head .name {
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .graph-wrap {
                flex: 1;
                min-height: 0;
                display: flex;
            }
            crm-mini-graph-preview {
                flex: 1;
                min-height: 0;
            }
            .footer-actions {
                display: flex;
                justify-content: flex-end;
                width: 100%;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:hover { background: var(--crm-surface-muted); color: var(--text-primary); }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.noteId = '';
        this._entities = this.useResource(ENTITIES_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.noteId !== 'string' || this.noteId.length === 0) {
            throw new Error('CRMNoteGraphModal: prop "noteId" required');
        }
        this._entities.get(this.noteId);
    }

    _note() {
        const item = this._entities.byId[this.noteId];
        return item === undefined ? null : item;
    }

    _onEntityOpen(event) {
        const entityId = event.detail && event.detail.entityId ? event.detail.entityId : '';
        if (typeof entityId !== 'string' || entityId.length === 0) return;
        if (entityId === this.noteId) return;
        this.close();
        this.navigate('entity', { itemId: entityId });
    }

    renderHeader() {
        return this.t('note_graph_modal.header');
    }

    renderBody() {
        const note = this._note();
        const name = note !== null && typeof note.name === 'string' && note.name.length > 0
            ? note.name
            : this.noteId;
        return html`
            <div class="body">
                <div class="head">
                    <platform-icon name="git-branch" size="14"></platform-icon>
                    <span>${this.t('note_graph_modal.subtitle')}</span>
                    <span class="name">${name}</span>
                </div>
                <div class="graph-wrap">
                    <crm-mini-graph-preview
                        fill-container
                        entity-id=${this.noteId}
                        .maxDepth=${3}
                        .initialDisplayDepth=${2}
                        @entity-open=${this._onEntityOpen}
                    ></crm-mini-graph-preview>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn" @click=${() => this.close()}>
                    ${this.t('note_graph_modal.close')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-note-graph-modal', CRMNoteGraphModal);
registerModalKind(CRMNoteGraphModal.modalKind, 'crm-note-graph-modal');
