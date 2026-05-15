/**
 * OfficeDocumentRow — строка документа в таблице/списке.
 *
 * Презентационный компонент. props:
 *   - document: OfficeDocumentItem (binding_id, title, document_type,
 *     created_at, created_by_display_name, created_by_avatar_url, ...)
 *
 * Эмитит DOM-события для родителя (page) через `this.emit`:
 *   - 'open'    — клик по строке/иконке
 *   - 'rename'  — кнопка переименовать
 *   - 'delete'  — кнопка удалить
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/platform-icon.js';

export class OfficeDocumentRow extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        document: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .row {
                display: grid;
                grid-template-columns: 1fr auto auto auto auto;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: var(--motion-transition-interactive);
            }
            .row:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            .title {
                display: inline-flex; align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                cursor: pointer;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .meta {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                white-space: nowrap;
            }
            .actions { display: flex; gap: var(--space-1); }
            .btn-icon {
                display: inline-flex; align-items: center; justify-content: center;
                width: 32px; height: 32px;
                background: transparent;
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .btn-icon:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .btn-icon.danger:hover { color: var(--danger); }
            @media (max-width: 767px) {
                .row {
                    grid-template-columns: 1fr auto;
                }
                .meta { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this.document = null;
    }

    _onOpen() {
        if (!this.document) return;
        this.emit('open', { bindingId: this.document.binding_id });
    }

    _onRename() {
        if (!this.document) return;
        this.emit('rename', { document: this.document });
    }

    _onDelete() {
        if (!this.document) return;
        this.emit('delete', { document: this.document });
    }

    _docTypeLabel() {
        if (!this.document) return '';
        const typeKey = this.document.document_type;
        if (typeof typeKey !== 'string' || typeKey.length === 0) return '';
        return this.t(`list.docType.${typeKey}`);
    }

    render() {
        if (!this.document) return html``;
        const doc = this.document;
        const created = doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '';
        return html`
            <div class="row">
                <span class="title" @click=${this._onOpen}>
                    <platform-icon file-icon name=${resolveFileIconKey(doc.title, '')} size="20"></platform-icon>
                    <span>${doc.title}</span>
                </span>
                <span class="meta">${created}</span>
                <span class="meta">${doc.created_by_display_name}</span>
                <span class="meta">${this._docTypeLabel()}</span>
                <span class="actions">
                    <button class="btn-icon" type="button"
                            title=${this.t('list.rename')}
                            @click=${this._onRename}>
                        <platform-icon name="edit" size="16"></platform-icon>
                    </button>
                    <button class="btn-icon danger" type="button"
                            title=${this.t('list.delete')}
                            @click=${this._onDelete}>
                        <platform-icon name="trash" size="16"></platform-icon>
                    </button>
                </span>
            </div>
        `;
    }
}

customElements.define('office-document-row', OfficeDocumentRow);
