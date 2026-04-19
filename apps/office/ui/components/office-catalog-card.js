/**
 * OfficeCatalogCard — карточка каталога в дашборде каталогов.
 *
 * props:
 *   - catalog: OfficeCatalogListItem (catalog_id, title, file_count,
 *     owner_user_id, owner_display_name, is_owner, is_public)
 *
 * Эмитит:
 *   - 'open'             — клик по заголовку → перейти в список с фильтром
 *   - 'manage-members'   — управление участниками
 *   - 'edit'             — редактировать (title / is_public)
 *   - 'delete'           — удалить каталог
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';

export class OfficeCatalogCard extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        catalog: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .card {
                position: relative;
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                display: flex; flex-direction: column;
                gap: var(--space-3);
                transition: all var(--duration-fast);
                min-height: 160px;
            }
            .card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
                transform: translateY(-2px);
                box-shadow: var(--glass-shadow-medium);
            }
            .tag {
                position: absolute;
                top: var(--space-3); right: var(--space-3);
                font-size: var(--text-xs);
                padding: 2px var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-strong);
                color: var(--text-secondary);
            }
            .tag.public { background: var(--accent-subtle); color: var(--accent); }
            .header { display: flex; align-items: center; gap: var(--space-3); }
            .icon {
                width: 40px; height: 40px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--accent-subtle);
                color: var(--accent);
                flex-shrink: 0;
            }
            .title {
                font-size: var(--text-lg);
                font-weight: 600;
                color: var(--text-primary);
                cursor: pointer;
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .meta { font-size: var(--text-sm); color: var(--text-tertiary); }
            .actions {
                display: flex; gap: var(--space-2);
                margin-top: auto;
            }
            .btn {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                color: var(--text-secondary);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .btn:hover {
                color: var(--accent);
                border-color: var(--accent);
            }
            .btn.danger:hover {
                color: var(--danger);
                border-color: var(--danger);
            }
        `,
    ];

    constructor() {
        super();
        this.catalog = null;
    }

    _onOpen() {
        if (!this.catalog) return;
        this.emit('open', { catalogId: this.catalog.catalog_id });
    }

    _onManageMembers() {
        if (!this.catalog) return;
        this.emit('manage-members', {
            catalogId: this.catalog.catalog_id,
            catalogTitle: this.catalog.title,
            isPublic: Boolean(this.catalog.is_public),
        });
    }

    _onEdit() {
        if (!this.catalog) return;
        this.emit('edit', {
            catalogId: this.catalog.catalog_id,
            title: this.catalog.title,
            isPublic: Boolean(this.catalog.is_public),
        });
    }

    _onDelete() {
        if (!this.catalog) return;
        this.emit('delete', {
            catalogId: this.catalog.catalog_id,
            title: this.catalog.title,
        });
    }

    render() {
        if (!this.catalog) return html``;
        const c = this.catalog;
        const tag = c.is_public
            ? html`<span class="tag public">${this.t('catalogs.tagPublic')}</span>`
            : html`<span class="tag">${this.t('catalogs.tagPrivate')}</span>`;
        return html`
            <div class="card">
                ${tag}
                <div class="header">
                    <div class="icon"><platform-icon name="folder" size="20"></platform-icon></div>
                    <div class="title" @click=${this._onOpen}>${c.title}</div>
                </div>
                <div class="meta">${this.t('catalogs.fileCount', { count: c.file_count })}</div>
                ${c.owner_user_id ? html`
                    <platform-user-chip user-id=${c.owner_user_id}></platform-user-chip>
                ` : ''}
                <div class="actions">
                    <button class="btn" type="button" @click=${this._onManageMembers}>
                        ${this.t('catalogs.manageAccess')}
                    </button>
                    ${c.is_owner ? html`
                        <button class="btn" type="button" @click=${this._onEdit}>
                            ${this.t('list.rename')}
                        </button>
                        <button class="btn danger" type="button" @click=${this._onDelete}>
                            ${this.t('catalogs.delete')}
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('office-catalog-card', OfficeCatalogCard);
