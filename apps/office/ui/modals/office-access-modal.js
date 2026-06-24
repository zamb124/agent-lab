/**
 * OfficeAccessModal — единая модалка доступа для каталога и файла.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';

const CATALOG_ACCESS_GET = 'office/catalog_access_get';
const CATALOG_ACCESS_PATCH = 'office/catalog_access_update';
const CATALOG_ACCESS_ROTATE = 'office/catalog_access_rotate_link';
const DOCUMENT_ACCESS_GET = 'office/document_access_get';
const DOCUMENT_ACCESS_PATCH = 'office/document_access_update';
const DOCUMENT_ACCESS_ROTATE = 'office/document_access_rotate_link';
const COMPANY_MEMBERS = 'office/company_members';

export class OfficeAccessModal extends PlatformFormModal {
    static modalKind = 'office.access';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        resourceKind: { type: String },
        resourceId: { type: String },
        resourceTitle: { type: String },
        _companyVisible: { state: true },
        _linkEnabled: { state: true },
        _linkPermission: { state: true },
        _publicUrl: { state: true },
        _memberUserIds: { state: true },
        _query: { state: true },
        _loading: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .access-grid { display: grid; gap: var(--space-4); }
            .section-title {
                font-size: var(--text-xs);
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            .resource-title {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: 500;
            }
            .switch-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-2) 0;
            }
            .switch-label {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: 500;
            }
            .permission-row {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-2) 0;
            }
            .permission-row platform-field {
                min-width: 0;
            }
            .link-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                margin-top: var(--space-2);
            }
            .link-url {
                flex: 1 1 100%;
                min-width: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                word-break: break-all;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .link-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .members-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 180px;
                overflow-y: auto;
                margin-bottom: var(--space-3);
            }
            .member-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .member-row .remove-btn {
                margin-left: auto;
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
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                max-height: 160px;
                overflow-y: auto;
                margin-top: var(--space-2);
            }
            .candidate-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                cursor: pointer;
                text-align: left;
                width: 100%;
            }
            .candidate-row:hover { background: var(--glass-solid-medium); }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.resourceKind = 'catalog';
        this.resourceId = '';
        this.resourceTitle = '';
        this._companyVisible = true;
        this._linkEnabled = false;
        this._linkPermission = 'view';
        this._publicUrl = '';
        this._memberUserIds = [];
        this._query = '';
        this._loading = true;
        this.size = 'md';
        this._accessGet = null;
        this._accessPatch = null;
        this._accessRotate = null;
        this._companyMembers = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._accessGet = this.useOp(
            this.resourceKind === 'binding' ? DOCUMENT_ACCESS_GET : CATALOG_ACCESS_GET,
        );
        this._accessPatch = this.useOp(
            this.resourceKind === 'binding' ? DOCUMENT_ACCESS_PATCH : CATALOG_ACCESS_PATCH,
        );
        this._accessRotate = this.useOp(
            this.resourceKind === 'binding' ? DOCUMENT_ACCESS_ROTATE : CATALOG_ACCESS_ROTATE,
        );
        this._companyMembers = this.useOp(COMPANY_MEMBERS);
        void this._loadAccess();
        this._companyMembers.run(null);
    }

    async _loadAccess() {
        this._loading = true;
        const payload = this.resourceKind === 'binding'
            ? { bindingId: this.resourceId }
            : { catalogId: this.resourceId };
        const data = await this._accessGet.run(payload);
        if (data) {
            this._companyVisible = data.company_visible === true;
            this._linkEnabled = data.link_enabled === true;
            this._linkPermission = data.link_permission === 'edit' ? 'edit' : 'view';
            this._publicUrl = typeof data.public_url === 'string' ? data.public_url : '';
            this._memberUserIds = Array.isArray(data.members)
                ? data.members.map((m) => m.user_id).filter((id) => typeof id === 'string')
                : [];
        }
        this._loading = false;
    }

    _isCatalog() {
        return this.resourceKind === 'catalog';
    }

    _onCompanyVisibleChange(e) {
        if (!this._isCatalog()) return;
        this._companyVisible = Boolean(e.detail.value);
    }

    _onLinkEnabledChange(e) {
        this._linkEnabled = Boolean(e.detail.value);
    }

    _linkPermissionConfig() {
        return {
            values: [
                { value: 'view', label: this.t('access.permissionView') },
                { value: 'edit', label: this.t('access.permissionEdit') },
            ],
        };
    }

    _setLinkPermission(value) {
        this._linkPermission = value === 'edit' ? 'edit' : 'view';
    }

    _removeMember(userId) {
        this._memberUserIds = this._memberUserIds.filter((id) => id !== userId);
    }

    _addMember(userId) {
        if (this._memberUserIds.includes(userId)) return;
        this._memberUserIds = [...this._memberUserIds, userId];
        this._query = '';
    }

    _filteredCandidates() {
        const company = Array.isArray(this._companyMembers.lastResult)
            ? this._companyMembers.lastResult
            : [];
        const q = this._query.trim().toLowerCase();
        return company.filter((item) => {
            if (typeof item.user_id !== 'string') return false;
            if (this._memberUserIds.includes(item.user_id)) return false;
            if (q.length === 0) return true;
            const name = typeof item.name === 'string' ? item.name.toLowerCase() : '';
            const email = typeof item.email === 'string' ? item.email.toLowerCase() : '';
            return name.includes(q) || email.includes(q) || item.user_id.toLowerCase().includes(q);
        });
    }

    async _copyPublicUrl() {
        if (this._publicUrl.length === 0) return;
        await navigator.clipboard.writeText(this._publicUrl);
        this.toast('access.linkCopied', { namespace: 'documents' });
    }

    async _rotateLink() {
        const payload = this.resourceKind === 'binding'
            ? { bindingId: this.resourceId }
            : { catalogId: this.resourceId };
        const result = await this._accessRotate.run(payload);
        if (result && typeof result.public_url === 'string') {
            this._publicUrl = result.public_url;
            await this._copyPublicUrl();
        }
    }

    async _submit() {
        const patchPayload = this.resourceKind === 'binding'
            ? {
                bindingId: this.resourceId,
                linkEnabled: this._linkEnabled,
                linkPermission: this._linkPermission,
                memberUserIds: this._memberUserIds,
            }
            : {
                catalogId: this.resourceId,
                companyVisible: this._companyVisible,
                linkEnabled: this._linkEnabled,
                linkPermission: this._linkPermission,
                memberUserIds: this._companyVisible ? null : this._memberUserIds,
            };
        const result = await this._accessPatch.run(patchPayload);
        if (result) {
            if (typeof result.public_url === 'string' && result.public_url.length > 0) {
                this._publicUrl = result.public_url;
            }
            this._linkEnabled = result.link_enabled === true;
            this._linkPermission = result.link_permission === 'edit' ? 'edit' : 'view';
            if (this._isCatalog()) {
                this._companyVisible = result.company_visible === true;
            }
        }
        this.close();
    }

    renderHeader() {
        return this.t('access.modalTitle', { title: this.resourceTitle });
    }

    renderSaveHeaderButton() {
        return '';
    }

    renderBody() {
        if (this._loading) {
            return html`<div>${this.t('access.loading')}</div>`;
        }
        const showMembers = this._isCatalog() ? !this._companyVisible : true;
        return html`
            <div class="access-grid">
                <div>
                    <div class="section-title">${this.t('access.resourceTitle')}</div>
                    <div class="resource-title">${this.resourceTitle}</div>
                </div>
                ${this._isCatalog() ? html`
                    <div>
                        <div class="section-title">${this.t('access.companySection')}</div>
                        <div class="switch-row">
                            <span class="switch-label">${this.t('access.companyVisible')}</span>
                            <platform-switch
                                ?checked=${this._companyVisible}
                                @change=${this._onCompanyVisibleChange}
                            ></platform-switch>
                        </div>
                    </div>
                ` : ''}
                ${showMembers ? html`
                    <div>
                        <div class="section-title">${this.t('access.membersSection')}</div>
                        <div class="members-list">
                            ${this._memberUserIds.map((userId) => html`
                                <div class="member-row">
                                    <platform-user-chip user-id=${userId}></platform-user-chip>
                                    <button class="remove-btn" type="button" @click=${() => this._removeMember(userId)}>
                                        ${this.t('access.removeMember')}
                                    </button>
                                </div>
                            `)}
                        </div>
                        <platform-field
                            type="string"
                            input-type="search"
                            mode="edit"
                            .placeholder=${this.t('access.memberSearchPlaceholder')}
                            .value=${this._query}
                            @change=${(e) => { this._query = e.detail.value; }}
                        ></platform-field>
                        <div class="candidate-list">
                            ${this._filteredCandidates().map((item) => html`
                                <button class="candidate-row" type="button" @click=${() => this._addMember(item.user_id)}>
                                    <platform-user-chip user-id=${item.user_id}></platform-user-chip>
                                </button>
                            `)}
                        </div>
                    </div>
                ` : ''}
                <div>
                    <div class="section-title">${this.t('access.publicLinkSection')}</div>
                    <div class="switch-row">
                        <span class="switch-label">${this.t('access.linkEnabled')}</span>
                        <platform-switch
                            ?checked=${this._linkEnabled}
                            @change=${this._onLinkEnabledChange}
                        ></platform-switch>
                    </div>
                    <div class="permission-row">
                        <platform-field
                            type="enum"
                            mode="edit"
                            .label=${this.t('access.linkPermission')}
                            .value=${this._linkPermission}
                            .config=${this._linkPermissionConfig()}
                            ?disabled=${!this._linkEnabled}
                            @change=${(e) => this._setLinkPermission(e.detail.value)}
                        ></platform-field>
                    </div>
                    ${this._publicUrl ? html`
                        <div class="link-row">
                            <span class="link-url">${this._publicUrl}</span>
                            <div class="link-actions">
                                <button class="btn btn-secondary" type="button" @click=${this._copyPublicUrl}>
                                    ${this.t('access.copyLink')}
                                </button>
                                <button class="btn btn-secondary" type="button" @click=${this._rotateLink}>
                                    ${this.t('access.rotateLink')}
                                </button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button class="btn btn-secondary" type="button" @click=${() => this.close()}>
                    ${this.t('access.cancel')}
                </button>
                <button class="btn btn-primary" type="button" @click=${() => void this._submit()}>
                    ${this.t('access.save')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-access-modal', OfficeAccessModal);
registerModalKind(OfficeAccessModal.modalKind, 'office-access-modal');
