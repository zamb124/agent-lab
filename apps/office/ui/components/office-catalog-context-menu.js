/**
 * office-catalog-context-menu — контекстное меню каталога в explorer tree.
 *
 * Шлёт DOM-событие `ctx-action` с detail = { action, catalog }.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class OfficeCatalogContextMenu extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        x: { type: Number },
        y: { type: Number },
        catalog: { type: Object, attribute: false },
        hasChildCatalogs: { type: Boolean, attribute: 'has-child-catalogs' },
        visible: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                z-index: 30;
                display: none;
                min-width: 200px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: 10px;
                backdrop-filter: blur(12px);
                padding: 4px;
                box-shadow: var(--glass-shadow-medium);
                pointer-events: auto;
            }

            :host([visible]) {
                display: block;
            }

            .ctx-item {
                display: flex;
                align-items: center;
                gap: 8px;
                width: 100%;
                padding: 7px 12px;
                border: none;
                border-radius: 7px;
                background: none;
                color: var(--text-primary);
                font-size: 13px;
                cursor: pointer;
                text-align: left;
            }

            .ctx-item:hover {
                background: var(--glass-solid-medium);
            }

            .ctx-item.danger {
                color: var(--danger);
            }

            .ctx-item:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }

            .separator {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: 3px 8px;
            }
        `,
    ];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.catalog = null;
        this.hasChildCatalogs = false;
        this.visible = false;
    }

    updated(changed) {
        if (changed.has('x') || changed.has('y')) {
            this.style.left = `${this.x}px`;
            this.style.top = `${this.y}px`;
        }
    }

    _onAction(action) {
        if (!this.catalog || typeof this.catalog !== 'object') {
            return;
        }
        this.emit('ctx-action', { action, catalog: this.catalog });
    }

    _canDelete() {
        const catalog = this.catalog;
        if (!catalog || catalog.is_owner !== true) {
            return false;
        }
        const fileCount = typeof catalog.file_count === 'number' ? catalog.file_count : 0;
        return fileCount === 0 && this.hasChildCatalogs !== true;
    }

    render() {
        const catalog = this.catalog;
        if (!catalog || typeof catalog !== 'object') {
            return html``;
        }
        if (catalog.is_owner !== true) {
            return html``;
        }
        const isPublic = catalog.is_public === true;
        const canDelete = this._canDelete();
        return html`
            <button class="ctx-item" type="button" @click=${() => this._onAction('edit')}>
                <platform-icon name="edit" size="16"></platform-icon>
                ${this.t('catalog_context_menu.edit')}
            </button>
            <button class="ctx-item" type="button" @click=${() => this._onAction('access')}>
                <platform-icon name="link" size="16"></platform-icon>
                ${this.t('catalog_context_menu.access')}
            </button>
            ${!isPublic ? html`
                <button class="ctx-item" type="button" @click=${() => this._onAction('members')}>
                    <platform-icon name="users" size="16"></platform-icon>
                    ${this.t('catalog_context_menu.members')}
                </button>
            ` : null}
            <button class="ctx-item" type="button" @click=${() => this._onAction('rag')}>
                <platform-icon name="search" size="16"></platform-icon>
                ${this.t('catalog_context_menu.rag')}
            </button>
            <div class="separator"></div>
            <button
                class="ctx-item danger"
                type="button"
                ?disabled=${!canDelete}
                @click=${() => this._onAction('delete')}
            >
                <platform-icon name="trash" size="16"></platform-icon>
                ${this.t('catalog_context_menu.delete')}
            </button>
        `;
    }
}

customElements.define('office-catalog-context-menu', OfficeCatalogContextMenu);
