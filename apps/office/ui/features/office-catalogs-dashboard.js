/**
 * Дашборд каталогов документов: карточки, счётчик файлов, владелец, доступ.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';

export class OfficeCatalogsDashboard extends PlatformElement {
    static properties = {
        _items: { state: true },
        _loading: { state: true },
        _membersOpen: { state: true },
        _membersCatalogId: { state: true },
        _membersTitle: { state: true },
        _membersRows: { state: true },
        _membersOwner: { state: true },
        _membersLoading: { state: true },
        _createOpen: { state: true },
        _createTitle: { state: true },
        _companyUsers: { state: true },
        _addUserId: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: block;
                width: 100%;
            }
            .dash-heading {
                margin: 0 0 var(--space-4);
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                color: var(--text-primary);
            }
            .dash-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
                align-items: center;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
                gap: var(--space-4);
            }
            .card {
                border-radius: var(--radius-lg);
                border: 1px solid var(--documents-stroke);
                background: var(--glass-solid-subtle);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 140px;
                text-align: left;
                cursor: pointer;
                font: inherit;
                color: inherit;
                transition:
                    border-color var(--duration-fast) var(--easing-default),
                    box-shadow var(--duration-fast) var(--easing-default);
            }
            .card:hover {
                border-color: var(--documents-selected-stroke);
                box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06);
            }
            .card-title {
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
            }
            .card-meta {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .card-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-top: auto;
            }
            .card-actions {
                display: flex;
                gap: var(--space-1);
            }
            .card-action-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .card-action-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--accent);
            }
            .member-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .member-row:last-child {
                border-bottom: none;
            }
            .add-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
                align-items: center;
            }
            .add-row select {
                flex: 1;
                min-width: 160px;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this._items = [];
        this._loading = true;
        this._membersOpen = false;
        this._membersCatalogId = '';
        this._membersTitle = '';
        this._membersRows = [];
        this._membersOwner = '';
        this._membersLoading = false;
        this._createOpen = false;
        this._createTitle = '';
        this._companyUsers = [];
        this._addUserId = '';
        this._onReload = () => {
            void this._load();
        };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('office-documents-list-reload', this._onReload);
        void this._load();
    }

    disconnectedCallback() {
        window.removeEventListener('office-documents-list-reload', this._onReload);
        super.disconnectedCallback();
    }

    async _load() {
        const api = this.services.officeApi;
        if (!api) {
            return;
        }
        this._loading = true;
        this.requestUpdate();
        try {
            const res = await api.listCatalogs();
            this._items = Array.isArray(res.items) ? res.items : [];
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
            this._items = [];
        } finally {
            this._loading = false;
            this.requestUpdate();
        }
    }

    _openCatalog(catalogId) {
        window.dispatchEvent(
            new CustomEvent('navigate', {
                detail: { path: `/documents/catalog/${encodeURIComponent(catalogId)}` },
            }),
        );
    }

    _stopCard(e) {
        e.stopPropagation();
    }

    async _openMembers(e, row) {
        e.stopPropagation();
        this._membersCatalogId = row.catalog_id;
        this._membersTitle = row.title;
        this._membersOwner = row.owner_user_id;
        this._membersOpen = true;
        this._membersLoading = true;
        this._membersRows = [];
        this._addUserId = '';
        this.requestUpdate();
        const api = this.services.officeApi;
        if (!api) {
            this._membersLoading = false;
            return;
        }
        try {
            const [memRes, teamRes] = await Promise.all([
                api.listCatalogMembers(row.catalog_id),
                row.is_owner ? api.listCompanyMembers() : Promise.resolve([]),
            ]);
            this._membersRows = Array.isArray(memRes.members) ? memRes.members : [];
            this._companyUsers = Array.isArray(teamRes) ? teamRes : [];
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.error(msg);
        } finally {
            this._membersLoading = false;
            this.requestUpdate();
        }
    }

    _closeMembers() {
        this._membersOpen = false;
        this._membersCatalogId = '';
        this._membersTitle = '';
        this._membersRows = [];
        this._companyUsers = [];
        this._addUserId = '';
    }

    async _addMember() {
        const api = this.services.officeApi;
        const cid = this._membersCatalogId;
        const uid = (this._addUserId || '').trim();
        if (!api || !cid || !uid) {
            return;
        }
        try {
            const res = await api.addCatalogMember(cid, uid);
            this._membersRows = Array.isArray(res.members) ? res.members : [];
            this.success(this.i18n.t('catalogs.memberAdded'));
            this._addUserId = '';
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
        this.requestUpdate();
    }

    async _removeMember(userId) {
        const api = this.services.officeApi;
        const cid = this._membersCatalogId;
        if (!api || !cid) {
            return;
        }
        try {
            await api.removeCatalogMember(cid, userId);
            const res = await api.listCatalogMembers(cid);
            this._membersRows = Array.isArray(res.members) ? res.members : [];
            this.success(this.i18n.t('catalogs.memberRemoved'));
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
        this.requestUpdate();
    }

    _openCreate() {
        this._createTitle = '';
        this._createOpen = true;
    }

    _closeCreate() {
        this._createOpen = false;
        this._createTitle = '';
    }

    async _saveCreate() {
        const api = this.services.officeApi;
        const title = (this._createTitle || '').trim();
        if (!api || title.length === 0) {
            return;
        }
        try {
            await api.createCatalog(title);
            this.success(this.i18n.t('catalogs.created'));
            this._closeCreate();
            await this._load();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    async _confirmDelete(row) {
        const t = (k, p) => this.i18n.t(k, p);
        const ok = await platformConfirm(t('catalogs.deleteConfirm', { title: row.title }), {
            title: t('catalogs.deleteTitle'),
            confirmText: t('catalogs.delete'),
            cancelText: t('list.cancel'),
            variant: 'danger',
            confirmVariant: 'danger',
        });
        if (!ok) {
            return;
        }
        const api = this.services.officeApi;
        if (!api) {
            return;
        }
        try {
            await api.deleteCatalog(row.catalog_id);
            this.success(this.i18n.t('catalogs.deleted'));
            await this._load();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    _selectableUsers() {
        const memberIds = new Set(
            (this._membersRows || []).map((m) => (typeof m.user_id === 'string' ? m.user_id : '')),
        );
        return (this._companyUsers || []).filter((u) => {
            const id = typeof u.user_id === 'string' ? u.user_id : '';
            return id.length > 0 && !memberIds.has(id);
        });
    }

    render() {
        const t = (k, p) => this.i18n.t(k, p);
        const selectable = this._selectableUsers();
        return html`
            <h1 class="dash-heading">${t('catalogs.heading')}</h1>
            <div class="dash-toolbar">
                <platform-button variant="primary" @click=${this._openCreate}>
                    ${t('catalogs.create')}
                </platform-button>
            </div>
            ${this._loading
                ? html`<p>${t('list.loading')}</p>`
                : html`
                      <div class="grid">
                          ${(this._items || []).map(
                              (row) => html`
                                  <button
                                      type="button"
                                      class="card"
                                      @click=${() => this._openCatalog(row.catalog_id)}
                                  >
                                      <h2 class="card-title">${row.title}</h2>
                                      <div class="card-meta">
                                          ${t('catalogs.fileCount', { count: row.file_count })}
                                      </div>
                                      <div class="card-footer">
                                          <platform-user
                                              .userId=${row.owner_user_id}
                                              .name=${row.owner_display_name}
                                              .avatarUrl=${row.owner_avatar_url ?? ''}
                                              size="sm"
                                          ></platform-user>
                                          <div class="card-actions" @click=${this._stopCard}>
                                              ${row.is_owner
                                                  ? html`
                                                        <button
                                                            type="button"
                                                            class="card-action-btn"
                                                            title=${t('catalogs.manageAccess')}
                                                            aria-label=${t('catalogs.manageAccess')}
                                                            @click=${(e) => this._openMembers(e, row)}
                                                        >
                                                            <platform-icon name="users" .size=${20}></platform-icon>
                                                        </button>
                                                        <button
                                                            type="button"
                                                            class="card-action-btn"
                                                            title=${t('catalogs.delete')}
                                                            aria-label=${t('catalogs.delete')}
                                                            @click=${() => this._confirmDelete(row)}
                                                        >
                                                            <platform-icon name="trash" .size=${20}></platform-icon>
                                                        </button>
                                                    `
                                                  : html`
                                                        <button
                                                            type="button"
                                                            class="card-action-btn"
                                                            title=${t('catalogs.viewMembers')}
                                                            aria-label=${t('catalogs.viewMembers')}
                                                            @click=${(e) => this._openMembers(e, row)}
                                                        >
                                                            <platform-icon name="users" .size=${20}></platform-icon>
                                                        </button>
                                                    `}
                                          </div>
                                      </div>
                                  </button>
                              `,
                          )}
                      </div>
                      ${(this._items || []).length === 0
                          ? html`<p>${t('catalogs.empty')}</p>`
                          : null}
                  `}
            <glass-modal
                .open=${this._createOpen}
                heading=${t('catalogs.createHeading')}
                @modal-closed=${() => this._closeCreate()}
            >
                <div slot="content">
                    <label
                        style="display:block;margin-bottom:var(--space-2);font-size:var(--text-xs);font-weight:500;color:var(--text-secondary);"
                        >${t('catalogs.createLabel')}</label
                    >
                    <glass-input
                        .value=${this._createTitle}
                        @input=${(e) => {
                            const v = e.detail?.value;
                            if (typeof v === 'string') {
                                this._createTitle = v;
                            }
                        }}
                    ></glass-input>
                </div>
                <div slot="actions" style="display:flex;gap:var(--space-3);justify-content:flex-end;">
                    <platform-button variant="secondary" @click=${this._closeCreate}
                        >${t('list.cancel')}</platform-button
                    >
                    <platform-button variant="primary" @click=${() => void this._saveCreate()}
                        >${t('catalogs.create')}</platform-button
                    >
                </div>
            </glass-modal>
            <glass-modal
                .open=${this._membersOpen}
                heading=${this._membersTitle
                    ? t('catalogs.membersHeading', { title: this._membersTitle })
                    : t('catalogs.membersHeadingGeneric')}
                @modal-closed=${() => this._closeMembers()}
            >
                <div slot="content">
                    ${this._membersLoading
                        ? html`<p>${t('list.loading')}</p>`
                        : html`
                              ${(this._membersRows || []).map((m) => {
                                  const uid =
                                      typeof m.user_id === 'string' ? m.user_id : '';
                                  const isOwner = uid === this._membersOwner;
                                  const canRemove =
                                      this._companyUsers.length > 0 && !isOwner;
                                  return html`
                                      <div class="member-row">
                                          <platform-user
                                              .userId=${uid}
                                              .name=${m.display_name}
                                              .avatarUrl=${m.avatar_url ?? ''}
                                              size="sm"
                                          ></platform-user>
                                          ${canRemove
                                              ? html`
                                                    <button
                                                        type="button"
                                                        class="card-action-btn"
                                                        title=${t('catalogs.removeMember')}
                                                        aria-label=${t('catalogs.removeMember')}
                                                        @click=${() => void this._removeMember(uid)}
                                                    >
                                                        <platform-icon name="trash" .size=${18}></platform-icon>
                                                    </button>
                                                `
                                              : null}
                                      </div>
                                  `;
                              })}
                              ${this._companyUsers.length > 0
                                  ? html`
                                        <div class="add-row">
                                            <select
                                                .value=${this._addUserId}
                                                @change=${(e) => {
                                                    const el = e.target;
                                                    if (el instanceof HTMLSelectElement) {
                                                        this._addUserId = el.value;
                                                    }
                                                }}
                                            >
                                                <option value="">${t('catalogs.pickUser')}</option>
                                                ${selectable.map(
                                                    (u) => html`
                                                        <option
                                                            value=${typeof u.user_id === 'string'
                                                                ? u.user_id
                                                                : ''}
                                                        >
                                                            ${typeof u.name === 'string'
                                                                ? u.name
                                                                : u.user_id}
                                                        </option>
                                                    `,
                                                )}
                                            </select>
                                            <platform-button
                                                variant="secondary"
                                                ?disabled=${selectable.length === 0 ||
                                                !this._addUserId}
                                                @click=${() => void this._addMember()}
                                            >
                                                ${t('catalogs.addMember')}
                                            </platform-button>
                                        </div>
                                    `
                                  : null}
                          `}
                </div>
                <div slot="actions">
                    <platform-button variant="secondary" @click=${this._closeMembers}
                        >${t('list.cancel')}</platform-button
                    >
                </div>
            </glass-modal>
        `;
    }
}

customElements.define('office-catalogs-dashboard', OfficeCatalogsDashboard);
