/**
 * Дашборд каталогов документов: карточки, счётчик файлов, владелец, доступ.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { OfficeStore } from '../store/office.store.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';

const OFFICE_CATALOG_MEMBERS_STYLE_ID = 'office-catalog-members-modal-global-styles';

/**
 * glass-modal при open переносится в document.body — стили shadow дашборда на слот не действуют.
 */
function ensureOfficeCatalogMembersModalGlobalStyles() {
    if (document.getElementById(OFFICE_CATALOG_MEMBERS_STYLE_ID)) {
        return;
    }
    const el = document.createElement('style');
    el.id = OFFICE_CATALOG_MEMBERS_STYLE_ID;
    el.textContent = `
.office-catalog-members-modal .ocsm-section-label {
    display: block;
    font-size: var(--text-xs, 0.75rem);
    font-weight: var(--font-semibold, 600);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-tertiary, #94a3b8);
    margin-bottom: var(--space-2, 0.5rem);
}
.office-catalog-members-modal .ocsm-member-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2, 0.5rem);
    padding: var(--space-2, 0.5rem) 0;
    border-bottom: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.2));
}
.office-catalog-members-modal .ocsm-member-row:last-child {
    border-bottom: none;
}
.office-catalog-members-modal .ocsm-member-main {
    display: flex;
    align-items: center;
    gap: var(--space-2, 0.5rem);
    min-width: 0;
    flex: 1;
}
.office-catalog-members-modal .ocsm-user-avatar {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    overflow: hidden;
    border: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.25));
    background: var(--glass-solid-medium, rgba(148, 163, 184, 0.12));
}
.office-catalog-members-modal .ocsm-user-avatar-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}
.office-catalog-members-modal .ocsm-user-avatar-initials {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: var(--font-semibold, 600);
    color: #fff;
    letter-spacing: 0.02em;
}
.office-catalog-members-modal .ocsm-member-name {
    color: var(--text-primary, #f8fafc);
    font-weight: var(--font-medium, 500);
    font-size: var(--text-sm, 0.875rem);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.office-catalog-members-modal .ocsm-member-sub {
    color: var(--text-tertiary, #94a3b8);
    font-size: 10px;
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.office-catalog-members-modal .ocsm-search {
    width: 100%;
    padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
    border-radius: var(--radius-lg, 12px);
    border: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.25));
    background: var(--glass-solid-subtle, rgba(15, 23, 42, 0.4));
    color: var(--text-primary, #f8fafc);
    font-size: var(--text-sm, 0.875rem);
    font-family: inherit;
    outline: none;
    box-sizing: border-box;
    margin-bottom: var(--space-2, 0.5rem);
}
.office-catalog-members-modal .ocsm-search:focus {
    border-color: var(--accent, #38bdf8);
}
.office-catalog-members-modal .ocsm-pick-scroll {
    max-height: 220px;
    overflow-y: auto;
    border: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.25));
    border-radius: var(--radius-lg, 12px);
    margin-bottom: var(--space-3, 0.75rem);
}
.office-catalog-members-modal .ocsm-pick-row {
    display: flex;
    align-items: center;
    gap: var(--space-2, 0.5rem);
    width: 100%;
    margin: 0;
    padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
    border: none;
    border-bottom: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.15));
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    box-sizing: border-box;
}
.office-catalog-members-modal .ocsm-pick-row:last-child {
    border-bottom: none;
}
.office-catalog-members-modal .ocsm-pick-row:hover {
    background: var(--glass-solid-subtle, rgba(148, 163, 184, 0.08));
}
.office-catalog-members-modal .ocsm-pick-row--selected {
    background: color-mix(in srgb, var(--accent, #38bdf8) 14%, transparent);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent, #38bdf8) 45%, transparent);
}
.office-catalog-members-modal .ocsm-pick-meta {
    min-width: 0;
    flex: 1;
}
.office-catalog-members-modal .ocsm-add-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 0.5rem);
    align-items: center;
}
.office-catalog-members-modal .ocsm-empty-hint {
    padding: var(--space-3, 0.75rem);
    font-size: var(--text-sm, 0.875rem);
    color: var(--text-secondary, #cbd5e1);
}
.office-catalog-members-modal .ocsm-remove-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    border-radius: var(--radius-md, 8px);
    background: transparent;
    color: var(--text-secondary, #cbd5e1);
    cursor: pointer;
}
.office-catalog-members-modal .ocsm-remove-btn:hover {
    background: var(--glass-solid-medium, rgba(148, 163, 184, 0.15));
    color: var(--accent, #38bdf8);
}
.office-catalog-members-modal .ocsm-vis-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3, 0.75rem);
    margin-bottom: var(--space-4, 1rem);
    padding-bottom: var(--space-3, 0.75rem);
    border-bottom: 1px solid var(--glass-border-subtle, rgba(148, 163, 184, 0.2));
}
.office-catalog-members-modal .ocsm-vis-copy {
    flex: 1;
    min-width: 0;
}
.office-catalog-members-modal .ocsm-vis-hint {
    margin: var(--space-2, 0.5rem) 0 0;
    font-size: var(--text-xs, 0.75rem);
    line-height: 1.45;
    color: var(--text-secondary, #cbd5e1);
}
`;
    document.head.appendChild(el);
}

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
        _membersAddSearch: { state: true },
        _createIsPublic: { state: true },
        _membersIsPublic: { state: true },
        _membersIsOwner: { state: true },
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
                background: var(
                    --documents-title-gradient,
                    linear-gradient(105deg, #3ec9d8 0%, #6cb1e1 42%, #737ce9 100%)
                );
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                color: transparent;
            }
            .catalog-empty-body {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: min(52vh, 440px);
            }
            .catalog-empty-wrap {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8) var(--space-4);
                box-sizing: border-box;
            }
            .catalog-empty {
                text-align: center;
                max-width: 26rem;
            }
            .catalog-empty-icon-wrap {
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto var(--space-5);
                width: 88px;
                height: 88px;
                border-radius: var(--radius-2xl);
                background: color-mix(in srgb, var(--documents-selected-text) 12%, transparent);
                border: 1px solid color-mix(in srgb, var(--documents-stroke) 55%, transparent);
            }
            .catalog-empty-icon-wrap platform-icon {
                opacity: 0.42;
                color: var(--documents-selected-text);
            }
            .catalog-empty-title {
                margin: 0 0 var(--space-2);
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.25;
            }
            .catalog-empty-hint {
                margin: 0 0 var(--space-5);
                font-size: var(--text-base);
                line-height: 1.5;
                color: var(--text-secondary);
            }
            .catalog-empty-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: center;
                flex-wrap: wrap;
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
                position: relative;
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
            .card-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
            }
            .card-title {
                flex: 1;
                min-width: 0;
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                text-align: left;
            }
            .card-visibility-tag {
                flex-shrink: 0;
                font-size: 10px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                padding: 4px 8px;
                border-radius: var(--radius-full);
                border: 1px solid var(--documents-stroke);
                line-height: 1.2;
                max-width: 42%;
                text-align: center;
            }
            .card-visibility-tag--public {
                color: var(--accent);
                border-color: color-mix(in srgb, var(--accent) 45%, var(--documents-stroke));
                background: color-mix(in srgb, var(--accent) 10%, transparent);
            }
            .card-visibility-tag--private {
                color: var(--text-secondary);
                background: var(--glass-solid-medium);
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
            .person-inline {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1;
                pointer-events: none;
            }
            .person-avatar {
                position: relative;
                flex: 0 0 32px;
                width: 32px;
                height: 32px;
                border-radius: var(--radius-full);
                overflow: hidden;
                background: var(--glass-solid-medium);
                border: 1px solid var(--documents-stroke);
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .person-initial {
                font-size: 11px;
                font-weight: 700;
                color: var(--text-secondary);
                line-height: 1;
            }
            .person-img {
                position: absolute;
                inset: 0;
                z-index: 1;
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .person-name {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
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
        this._membersAddSearch = '';
        this._createIsPublic = true;
        this._membersIsPublic = true;
        this._membersIsOwner = false;
        this._onReload = () => {
            void this._load();
        };
    }

    connectedCallback() {
        super.connectedCallback();
        ensureOfficeCatalogMembersModalGlobalStyles();
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
        OfficeStore.setActiveCatalogId(catalogId);
        OfficeStore.setFilterCatalogIds([catalogId]);
        window.dispatchEvent(new CustomEvent('office-documents-list-reload', { bubbles: true }));
        window.dispatchEvent(
            new CustomEvent('navigate', { detail: { path: '/documents' } }),
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
        const pub = row.is_public;
        this._membersIsPublic = typeof pub === 'boolean' ? pub : true;
        this._membersIsOwner = row.is_owner === true;
        this._membersOpen = true;
        this._membersLoading = true;
        this._membersRows = [];
        this._addUserId = '';
        this._membersAddSearch = '';
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
        this._membersAddSearch = '';
        this._membersIsPublic = true;
        this._membersIsOwner = false;
    }

    async _onMembersPublicChange(e) {
        const next = Boolean(e.detail?.value);
        const prev = this._membersIsPublic;
        const cid = this._membersCatalogId;
        const api = this.services.officeApi;
        if (!api || typeof cid !== 'string' || cid === '') {
            this._membersIsPublic = prev;
            this.requestUpdate();
            return;
        }
        this._membersIsPublic = next;
        this.requestUpdate();
        try {
            await api.patchCatalog(cid, { is_public: next });
            await this._load();
            const refreshed = (this._items || []).find((x) => x.catalog_id === cid);
            if (refreshed && typeof refreshed.is_public === 'boolean') {
                this._membersIsPublic = refreshed.is_public;
            }
            this.success(this.i18n.t('catalogs.visibilityUpdated'));
        } catch (err) {
            this._membersIsPublic = prev;
            this.requestUpdate();
            const msg = err instanceof Error ? err.message : String(err);
            this.error(msg);
        }
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
            this._membersAddSearch = '';
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
        this._createIsPublic = true;
        this._createOpen = true;
    }

    _closeCreate() {
        this._createOpen = false;
        this._createTitle = '';
        this._createIsPublic = true;
    }

    async _saveCreate() {
        const api = this.services.officeApi;
        const title = (this._createTitle || '').trim();
        if (!api || title.length === 0) {
            return;
        }
        try {
            await api.createCatalog(title, { is_public: this._createIsPublic });
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

    /**
     * @param {string} userId
     * @returns {Record<string, unknown> | null}
     */
    _companyMemberById(userId) {
        const id = typeof userId === 'string' ? userId : '';
        if (id === '') {
            return null;
        }
        const list = this._companyUsers || [];
        const found = list.find((u) => u.user_id === id);
        return found ?? null;
    }

    /**
     * @param {string} userId
     */
    _hueFromUserId(userId) {
        let h = 0;
        const s = typeof userId === 'string' ? userId : '';
        for (let i = 0; i < s.length; i++) {
            h = (h * 31 + s.charCodeAt(i)) >>> 0;
        }
        return h % 360;
    }

    /**
     * @param {string} userId
     * @param {string} [catalogAvatarUrl]
     */
    _resolveMemberAvatarUrl(userId, catalogAvatarUrl) {
        const ca =
            typeof catalogAvatarUrl === 'string' && catalogAvatarUrl.trim() !== ''
                ? catalogAvatarUrl.trim()
                : '';
        if (ca !== '') {
            return ca;
        }
        const cm = this._companyMemberById(userId);
        const ua =
            cm &&
            typeof cm.avatar_url === 'string' &&
            cm.avatar_url.trim() !== ''
                ? cm.avatar_url.trim()
                : '';
        return ua;
    }

    /**
     * @param {string} userId
     * @param {string} displayName
     * @param {string} [catalogAvatarUrl]
     */
    _renderOcsmAvatar(userId, displayName, catalogAvatarUrl) {
        const url = this._resolveMemberAvatarUrl(userId, catalogAvatarUrl);
        const label = String(displayName || userId || '').trim();
        const initial = (label.slice(0, 1) || '?').toUpperCase();
        const hue = this._hueFromUserId(userId);
        return html`
            <div class="ocsm-user-avatar" aria-hidden="true">
                ${url !== ''
                    ? html`
                          <img
                              class="ocsm-user-avatar-img"
                              src=${url}
                              alt=""
                              @error=${(e) => {
                                  const el = e.target;
                                  if (el instanceof HTMLImageElement) {
                                      el.replaceWith(
                                          Object.assign(document.createElement('span'), {
                                              className: 'ocsm-user-avatar-initials',
                                              textContent: initial,
                                              style: `background:hsl(${hue} 48% 42%)`,
                                          }),
                                      );
                                  }
                              }}
                          />
                      `
                    : html`
                          <span
                              class="ocsm-user-avatar-initials"
                              style=${`background:hsl(${hue} 48% 42%)`}
                              >${initial}</span
                          >
                      `}
            </div>
        `;
    }

    _candidatesForCatalogAdd() {
        const base = this._selectableUsers();
        const q = (this._membersAddSearch || '').trim().toLowerCase();
        if (q === '') {
            return base;
        }
        return base.filter((u) => {
            const name = typeof u.name === 'string' ? u.name.toLowerCase() : '';
            const id = typeof u.user_id === 'string' ? u.user_id.toLowerCase() : '';
            return name.includes(q) || id.includes(q);
        });
    }

    /**
     * @param {string} uid
     */
    _onPickCatalogMember(uid) {
        const id = typeof uid === 'string' ? uid : '';
        if (id === '') {
            return;
        }
        this._addUserId = this._addUserId === id ? '' : id;
        this.requestUpdate();
    }

    /**
     * @param {string} displayName
     */
    _personInitial(displayName) {
        const s = String(displayName || '').trim();
        if (s.length === 0) {
            return '?';
        }
        return s.charAt(0).toUpperCase();
    }

    /**
     * @param {string} displayName
     * @param {string} [avatarUrl]
     * @param {string} ariaLabel
     */
    _renderPersonInline(displayName, avatarUrl, ariaLabel) {
        const name = String(displayName || '').trim() || '—';
        const url =
            typeof avatarUrl === 'string' && avatarUrl.trim() !== '' ? avatarUrl.trim() : '';
        const initial = this._personInitial(name);
        return html`
            <div class="person-inline" role="group" aria-label=${ariaLabel}>
                <div class="person-avatar" aria-hidden="true">
                    <span class="person-initial">${initial}</span>
                    ${url
                        ? html`
                              <img
                                  class="person-img"
                                  src=${url}
                                  alt=""
                                  @error=${(e) => {
                                      const el = e.target;
                                      if (el instanceof HTMLImageElement) {
                                          el.style.display = 'none';
                                      }
                                  }}
                              />
                          `
                        : null}
                </div>
                <span class="person-name">${name}</span>
            </div>
        `;
    }

    render() {
        const t = (k, p) => this.i18n.t(k, p);
        const selectable = this._selectableUsers();
        const addCandidates = this._candidatesForCatalogAdd();
        return html`
            <h1 class="dash-heading">${t('catalogs.heading')}</h1>
            ${this._loading
                ? html`<p>${t('list.loading')}</p>`
                : (this._items || []).length > 0
                  ? html`
                        <div class="dash-toolbar">
                            <platform-button variant="primary" @click=${this._openCreate}>
                                ${t('catalogs.create')}
                            </platform-button>
                        </div>
                        <div class="grid">
                            ${(this._items || []).map(
                                (row) => html`
                                    <button
                                        type="button"
                                        class="card"
                                        @click=${() => this._openCatalog(row.catalog_id)}
                                    >
                                        <div class="card-head">
                                            <h2 class="card-title">${row.title}</h2>
                                            <span
                                                class="card-visibility-tag ${typeof row.is_public === 'boolean'
                                                    ? row.is_public
                                                        ? 'card-visibility-tag--public'
                                                        : 'card-visibility-tag--private'
                                                    : 'card-visibility-tag--public'}"
                                                aria-label=${typeof row.is_public === 'boolean' && !row.is_public
                                                    ? t('catalogs.tagPrivate')
                                                    : t('catalogs.tagPublic')}
                                                >${typeof row.is_public === 'boolean' && !row.is_public
                                                    ? t('catalogs.tagPrivate')
                                                    : t('catalogs.tagPublic')}</span
                                            >
                                        </div>
                                        <div class="card-meta">
                                            ${t('catalogs.fileCount', { count: row.file_count })}
                                        </div>
                                        <div class="card-footer">
                                            ${this._renderPersonInline(
                                                typeof row.owner_display_name === 'string'
                                                    ? row.owner_display_name
                                                    : String(row.owner_user_id ?? ''),
                                                typeof row.owner_avatar_url === 'string'
                                                    ? row.owner_avatar_url
                                                    : '',
                                                t('catalogs.ownerAria', {
                                                    name:
                                                        typeof row.owner_display_name === 'string' &&
                                                        row.owner_display_name.trim() !== ''
                                                            ? row.owner_display_name
                                                            : String(row.owner_user_id ?? ''),
                                                }),
                                            )}
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
                    `
                  : html`
                        <div
                            class="catalog-empty-body"
                            role="region"
                            aria-label=${t('catalogs.emptyStateAria')}
                        >
                            <div class="catalog-empty-wrap">
                                <div class="catalog-empty">
                                    <div class="catalog-empty-icon-wrap" aria-hidden="true">
                                        <platform-icon name="folder" size="44"></platform-icon>
                                    </div>
                                    <h2 class="catalog-empty-title">${t('catalogs.emptyStateTitle')}</h2>
                                    <p class="catalog-empty-hint">${t('catalogs.emptyStateHint')}</p>
                                    <div class="catalog-empty-actions">
                                        <platform-button variant="primary" @click=${this._openCreate}>
                                            ${t('catalogs.create')}
                                        </platform-button>
                                    </div>
                                </div>
                            </div>
                        </div>
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
                    <div
                        style="display:flex;align-items:flex-start;justify-content:space-between;gap:var(--space-3);margin-top:var(--space-4);"
                    >
                        <div style="flex:1;min-width:0;">
                            <span
                                style="display:block;font-size:var(--text-xs);font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.06em;"
                                >${t('catalogs.switchPublicCatalog')}</span
                            >
                            <p
                                style="margin:var(--space-2) 0 0;font-size:var(--text-xs);line-height:1.45;color:var(--text-tertiary);"
                            >
                                ${t('catalogs.createPublicHint')}
                            </p>
                        </div>
                        <platform-switch
                            .checked=${this._createIsPublic}
                            @change=${(e) => {
                                this._createIsPublic = Boolean(e.detail?.value);
                            }}
                        ></platform-switch>
                    </div>
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
                              <div class="office-catalog-members-modal">
                                  ${this._membersIsOwner
                                      ? html`
                                            <div class="ocsm-vis-row">
                                                <div class="ocsm-vis-copy">
                                                    <span class="ocsm-section-label"
                                                        >${t('catalogs.switchPublicCatalog')}</span
                                                    >
                                                    <p class="ocsm-vis-hint">
                                                        ${this._membersIsPublic
                                                            ? t('catalogs.membersPublicHint')
                                                            : t('catalogs.membersPrivateHint')}
                                                    </p>
                                                </div>
                                                <platform-switch
                                                    .checked=${this._membersIsPublic}
                                                    @change=${(e) => void this._onMembersPublicChange(e)}
                                                ></platform-switch>
                                            </div>
                                        `
                                      : null}
                                  ${(this._membersRows || []).map((m) => {
                                      const uid =
                                          typeof m.user_id === 'string' ? m.user_id : '';
                                      const isOwner = uid === this._membersOwner;
                                      const canRemove =
                                          this._companyUsers.length > 0 && !isOwner;
                                      const displayName =
                                          typeof m.display_name === 'string' &&
                                          m.display_name.trim() !== ''
                                              ? m.display_name.trim()
                                              : uid;
                                      const catAv =
                                          typeof m.avatar_url === 'string' ? m.avatar_url : '';
                                      return html`
                                          <div
                                              class="ocsm-member-row"
                                              role="group"
                                              aria-label=${t('catalogs.memberAria', {
                                                  name: displayName,
                                              })}
                                          >
                                              <div class="ocsm-member-main">
                                                  ${this._renderOcsmAvatar(
                                                      uid,
                                                      displayName,
                                                      catAv,
                                                  )}
                                                  <div class="ocsm-pick-meta">
                                                      <div class="ocsm-member-name">${displayName}</div>
                                                      <div class="ocsm-member-sub">${uid}</div>
                                                  </div>
                                              </div>
                                              ${canRemove
                                                  ? html`
                                                        <button
                                                            type="button"
                                                            class="ocsm-remove-btn"
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
                                  ${this._membersIsOwner &&
                                  !this._membersIsPublic &&
                                  this._companyUsers.length > 0
                                      ? html`
                                            <div style="margin-top:var(--space-4);">
                                                <span class="ocsm-section-label"
                                                    >${t('catalogs.pickUser')}</span
                                                >
                                                ${selectable.length === 0
                                                    ? html`<p class="ocsm-empty-hint">${t('catalogs.allInCatalog')}</p>`
                                                    : html`
                                                          <input
                                                              type="search"
                                                              class="ocsm-search"
                                                              placeholder=${t(
                                                                  'catalogs.searchMemberPlaceholder',
                                                              )}
                                                              .value=${this._membersAddSearch}
                                                              @input=${(e) => {
                                                                  const el = e.target;
                                                                  if (el instanceof HTMLInputElement) {
                                                                      this._membersAddSearch = el.value;
                                                                      const next =
                                                                          this._candidatesForCatalogAdd();
                                                                      const pick = this._addUserId;
                                                                      if (
                                                                          pick !== '' &&
                                                                          !next.some(
                                                                              (u) => u.user_id === pick,
                                                                          )
                                                                      ) {
                                                                          this._addUserId = '';
                                                                      }
                                                                      this.requestUpdate();
                                                                  }
                                                              }}
                                                          />
                                                          <div class="ocsm-pick-scroll">
                                                              ${addCandidates.length === 0
                                                                  ? html`<div class="ocsm-empty-hint">
                                                                        ${t('catalogs.noMemberMatches')}
                                                                    </div>`
                                                                  : addCandidates.map(
                                                                        (u) => {
                                                                            const id =
                                                                                typeof u.user_id ===
                                                                                'string'
                                                                                    ? u.user_id
                                                                                    : '';
                                                                            const nm =
                                                                                typeof u.name ===
                                                                                'string'
                                                                                    ? u.name
                                                                                    : id;
                                                                            const selected =
                                                                                this._addUserId === id;
                                                                            return html`
                                                                                <button
                                                                                    type="button"
                                                                                    class="ocsm-pick-row ${selected
                                                                                        ? 'ocsm-pick-row--selected'
                                                                                        : ''}"
                                                                                    @click=${() =>
                                                                                        this._onPickCatalogMember(
                                                                                            id,
                                                                                        )}
                                                                                >
                                                                                    ${this._renderOcsmAvatar(
                                                                                        id,
                                                                                        nm,
                                                                                        typeof u.avatar_url ===
                                                                                            'string'
                                                                                            ? u.avatar_url
                                                                                            : '',
                                                                                    )}
                                                                                    <div
                                                                                        class="ocsm-pick-meta"
                                                                                    >
                                                                                        <div
                                                                                            class="ocsm-member-name"
                                                                                        >
                                                                                            ${nm}
                                                                                        </div>
                                                                                        <div
                                                                                            class="ocsm-member-sub"
                                                                                        >
                                                                                            ${id}
                                                                                        </div>
                                                                                    </div>
                                                                                </button>
                                                                            `;
                                                                        },
                                                                    )}
                                                          </div>
                                                          <div class="ocsm-add-toolbar">
                                                              <platform-button
                                                                  variant="secondary"
                                                                  ?disabled=${!this._addUserId}
                                                                  @click=${() => void this._addMember()}
                                                              >
                                                                  ${t('catalogs.addMember')}
                                                              </platform-button>
                                                          </div>
                                                      `}
                                            </div>
                                        `
                                      : null}
                              </div>
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
