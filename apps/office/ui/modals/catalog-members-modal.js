/**
 * OfficeCatalogMembersModal — управление участниками приватного каталога.
 *
 * props: { catalogId, catalogTitle, isPublic }.
 *   - useOp('office/catalog_members') autoload в connectedCallback по catalogId
 *   - useOp('office/company_members') autoload (общий список компании)
 *   - useOp('office/catalog_member_add')   — кнопка add
 *   - useOp('office/catalog_member_remove') — кнопка remove
 *
 * Для публичного каталога секция add скрыта (бэкенд отклоняет POST members).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';

const MEMBERS_NAME = 'office/catalog_members';
const COMPANY_MEMBERS_NAME = 'office/company_members';
const MEMBER_ADD_NAME = 'office/catalog_member_add';
const MEMBER_REMOVE_NAME = 'office/catalog_member_remove';

export class OfficeCatalogMembersModal extends PlatformFormModal {
    static modalKind = 'office.catalog_members';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        catalogTitle: { type: String },
        isPublic: { type: Boolean },
        _query: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .members-grid { display: grid; gap: var(--space-4); }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }
            .members-list {
                display: flex; flex-direction: column;
                gap: var(--space-2);
            }
            .member-row {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .member-row .name { flex: 1; font-size: var(--text-sm); color: var(--text-primary); }
            .member-row .remove-btn {
                background: transparent;
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                padding: 4px var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .member-row .remove-btn:hover {
                color: var(--danger);
                border-color: var(--danger);
            }
            .candidate-list {
                display: flex; flex-direction: column;
                gap: var(--space-1);
                max-height: 220px;
                overflow-y: auto;
            }
            .candidate-row {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                border-radius: var(--radius-md);
            }
            .candidate-row:hover {
                background: var(--glass-solid-medium);
            }
            .empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                padding: var(--space-3);
                text-align: center;
            }
            .footer-actions {
                display: flex; justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.hideHeaderClose = false;
        this.catalogId = '';
        this.catalogTitle = '';
        this.isPublic = false;
        this._query = '';
        this._members = this.useOp(MEMBERS_NAME);
        this._company = this.useOp(COMPANY_MEMBERS_NAME);
        this._add = this.useOp(MEMBER_ADD_NAME);
        this._remove = this.useOp(MEMBER_REMOVE_NAME);
        this._loaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._company.lastResult && !this._company.busy) {
            this._company.run(null);
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (!this._loaded && typeof this.catalogId === 'string' && this.catalogId.length > 0) {
            this._members.run({ catalogId: this.catalogId });
            this._loaded = true;
        }
        this.isDirty = false;
    }

    _onQueryInput(e) { this._query = e.target.value; }

    _onAdd(userId) {
        if (typeof userId !== 'string' || userId.length === 0) return;
        this._add.run({ catalogId: this.catalogId, userId });
    }

    _onRemove(userId) {
        if (typeof userId !== 'string' || userId.length === 0) return;
        this._remove.run({ catalogId: this.catalogId, userId });
    }

    _activeMembers() {
        const items = this._members.state.items;
        return Array.isArray(items) ? items : [];
    }

    _candidates() {
        const company = Array.isArray(this._company.lastResult) ? this._company.lastResult : [];
        const memberIds = new Set(this._activeMembers().map((m) => m.user_id));
        const q = this._query.trim().toLowerCase();
        return company.filter((u) => {
            if (memberIds.has(u.user_id)) return false;
            if (q.length === 0) return true;
            const name = typeof u.name === 'string' ? u.name.toLowerCase() : '';
            const email = typeof u.email === 'string' ? u.email.toLowerCase() : '';
            const id = typeof u.user_id === 'string' ? u.user_id.toLowerCase() : '';
            return name.includes(q) || email.includes(q) || id.includes(q);
        });
    }

    renderHeader() {
        if (typeof this.catalogTitle === 'string' && this.catalogTitle.length > 0) {
            return this.t('catalog_members_modal.header', { title: this.catalogTitle });
        }
        return this.t('catalog_members_modal.header_generic');
    }

    renderSaveHeaderButton() { return ''; }

    _renderMembers() {
        const items = this._activeMembers();
        if (this._members.busy && items.length === 0) {
            return html`<div class="empty">${this.t('catalog_members_modal.members_loading')}</div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty">—</div>`;
        }
        return html`
            <div class="members-list">
                ${items.map((m) => html`
                    <div class="member-row">
                        <span class="name">${m.display_name}</span>
                        <button class="remove-btn" type="button"
                                ?disabled=${this._remove.busy}
                                @click=${() => this._onRemove(m.user_id)}>
                            ${this.t('catalog_members_modal.remove_member')}
                        </button>
                    </div>
                `)}
            </div>
        `;
    }

    _renderInvite() {
        if (this.isPublic) {
            return html`<div class="hint">${this.t('catalog_members_modal.members_public_hint')}</div>`;
        }
        const candidates = this._candidates();
        return html`
            <div class="hint">${this.t('catalog_members_modal.members_private_hint')}</div>
            <input type="search" class="form-input"
                   placeholder=${this.t('catalog_members_modal.search_placeholder')}
                   .value=${this._query}
                   @input=${this._onQueryInput} />
            ${candidates.length === 0 ? html`
                <div class="empty">${
                    this._query.trim().length > 0
                        ? this.t('catalog_members_modal.no_member_matches')
                        : this.t('catalog_members_modal.all_in_catalog')
                }</div>
            ` : html`
                <div class="candidate-list">
                    ${candidates.map((u) => html`
                        <div class="candidate-row" @click=${() => this._onAdd(u.user_id)}>
                            <platform-icon name="user" size="16"></platform-icon>
                            <span class="name">${u.name || u.user_id}</span>
                            <button class="remove-btn" type="button"
                                    ?disabled=${this._add.busy}>
                                ${this.t('catalog_members_modal.add_member')}
                            </button>
                        </div>
                    `)}
                </div>
            `}
        `;
    }

    renderBody() {
        return html`
            <div class="members-grid">
                ${this._renderMembers()}
                ${this._renderInvite()}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('catalog_members_modal.close')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-catalog-members-modal', OfficeCatalogMembersModal);
registerModalKind(OfficeCatalogMembersModal.modalKind, 'office-catalog-members-modal');
