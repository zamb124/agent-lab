/**
 * OfficeAccessModal — единая модалка доступа для каталога и файла.
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-spinner.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function accessRecord(value: unknown): Record<string, unknown> | null {
    if (value === null || value === undefined) return null;
    if (!isPlainRecord(value)) {
        throw new Error('office.access: response must be an object');
    }
    return value;
}

function companyMemberRows(items: unknown[]): Record<string, unknown>[] {
    const rows: Record<string, unknown>[] = [];
    for (const item of items) {
        if (!isPlainRecord(item)) {
            throw new Error('office.access: company member must be an object');
        }
        rows.push(item);
    }
    return rows;
}

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

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        resourceKind: { type: String },
        resourceId: { type: String },
        resourceTitle: { type: String },
        _companyVisible: { state: true },
        _linkEnabled: { state: true },
        _linkPermission: { state: true },
        _publicUrl: { state: true },
        _members: { state: true },
        _query: { state: true },
    }
    declare resourceKind: string;
    declare resourceId: string;
    declare resourceTitle: string;
    declare _companyVisible: unknown;
    declare _linkEnabled: unknown;
    declare _linkPermission: unknown;
    declare _publicUrl: string;
    declare _members: Array<{ user_id: string; relation: 'viewer' | 'editor' }>;
    declare _query: string;


    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
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
                color: var(--error);
                border-color: var(--error);
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
        this._linkPermission = 'viewer';
        this._publicUrl = '';
        this._members = [];
        this._query = '';
        this.size = 'md';
        this._accessGet = null;
        this._accessPatch = null;
        this._accessRotate = null;
        this._companyMembers = null;
    }
    private _accessGet: OpController | null;

    private get _loading(): boolean {
        return this._accessGet === null || this._accessGet.busy;
    }
    private _accessPatch: OpController | null;
    private _accessRotate: OpController | null;
    private _companyMembers: OpController | null;

    private _requireMembers(): OpController {
        const op = this._companyMembers;
        if (op === null) throw new Error('office.access: company members op required');
        return op;
    }

    private _requireAccessGet(): OpController {
        const op = this._accessGet;
        if (op === null) throw new Error('office.access: access get op required');
        return op;
    }

    private _requireAccessRotate(): OpController {
        const op = this._accessRotate;
        if (op === null) throw new Error('office.access: access rotate op required');
        return op;
    }

    private _requireAccessPatch(): OpController {
        const op = this._accessPatch;
        if (op === null) throw new Error('office.access: access patch op required');
        return op;
    }

    override connectedCallback(): void {
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
        this._requireMembers().run(null);
    }

    private async _loadAccess() {
        const payload = this.resourceKind === 'binding'
            ? { file_id: this.resourceId }
            : { catalog_id: this.resourceId };
        const data = accessRecord(await this._requireAccessGet().run(payload));
        if (data !== null) {
            this._companyVisible = data.company_visible === true;
            this._linkEnabled = data.link_enabled === true;
            if (data.link_permission !== 'viewer' && data.link_permission !== 'editor') {
                throw new Error('office.access: link_permission must be viewer|editor');
            }
            this._linkPermission = data.link_permission;
            this._publicUrl = typeof data.public_url === 'string' ? data.public_url : '';
            const members = data.members;
            const rows: { user_id: string; relation: 'viewer' | 'editor' }[] = [];
            if (Array.isArray(members)) {
                for (const member of members) {
                    if (member === null || member === undefined) continue;
                    if (!isPlainRecord(member)) {
                        throw new Error('office.access: member must be an object');
                    }
                    if (member.relation !== 'viewer' && member.relation !== 'editor') {
                        throw new Error('office.access: member.relation must be viewer|editor');
                    }
                    const userId = member.user_id;
                    if (typeof userId !== 'string' || userId.length === 0) continue;
                    rows.push({ user_id: userId, relation: member.relation });
                }
            }
            this._members = rows;
        }
    }

    private _isCatalog() {
        return this.resourceKind === 'catalog';
    }

    _onCompanyVisibleChange(e: CustomEvent<{ value?: unknown }>) {
        if (!this._isCatalog()) return;
        this._companyVisible = Boolean(e.detail.value);
    }

    private _onLinkEnabledChange(e: CustomEvent<{ value?: unknown }>) {
        this._linkEnabled = Boolean(e.detail.value);
    }

    private _linkPermissionConfig() {
        return {
            values: [
                { value: 'viewer', label: this.t('access.permissionViewer') },
                { value: 'editor', label: this.t('access.permissionEditor') },
            ],
        };
    }

    private _setLinkPermission(value: unknown) {
        this._linkPermission = value === 'editor' ? 'editor' : 'viewer';
    }

    private _removeMember(userId: string) {
        this._members = this._members.filter((member) => member.user_id !== userId);
    }

    private _addMember(userId: string) {
        if (this._members.some((member) => member.user_id === userId)) return;
        this._members = [...this._members, { user_id: userId, relation: 'viewer' }];
        this._query = '';
    }

    private _buildMembersPayload() {
        return this._members.map((member) => ({
            user_id: member.user_id,
            relation: member.relation === 'editor' ? 'editor' : 'viewer',
        }));
    }

    private _companyMemberItems(): Array<Record<string, unknown>> {
        const result = this._requireMembers().lastResult;
        if (result === null || result === undefined) {
            return [];
        }
        if (!isPlainRecord(result)) {
            throw new Error('office.access: company_members.lastResult.items required');
        }
        const items = result.items;
        if (!Array.isArray(items)) {
            throw new Error('office.access: company_members.lastResult.items required');
        }
        return companyMemberRows(items);
    }

    private _filteredCandidates() {
        const company = this._companyMemberItems();
        const q = this._query.trim().toLowerCase();
        return company.filter((item: Record<string, unknown>) => {
            if (typeof item.user_id !== 'string') return false;
            if (this._members.some((member) => member.user_id === item.user_id)) return false;
            if (q.length === 0) return true;
            const name = typeof item.name === 'string' ? item.name.toLowerCase() : '';
            const email = typeof item.email === 'string' ? item.email.toLowerCase() : '';
            return name.includes(q) || email.includes(q) || (item.user_id as string).toLowerCase().includes(q);
        });
    }

    private async _copyPublicUrl() {
        if (this._publicUrl.length === 0) {
            throw new Error('office.access: public url is empty');
        }
        await copyTextToClipboard(this._publicUrl);
        this.toast('access.linkCopied', { namespace: 'documents' });
    }

    private async _rotateLink() {
        const payload = this.resourceKind === 'binding'
            ? { file_id: this.resourceId, origin: window.location.origin }
            : { catalog_id: this.resourceId, origin: window.location.origin };
        const result = accessRecord(await this._requireAccessRotate().run(payload));
        if (result === null) return;
        const publicUrl = result.public_url;
        if (typeof publicUrl !== 'string' || publicUrl.length === 0) {
            return;
        }
        this._publicUrl = publicUrl;
        await this.updateComplete;
        await this._copyPublicUrl();
    }

    private async _submit() {
        const patchPayload = this.resourceKind === 'binding'
            ? {
                file_id: this.resourceId,
                origin: window.location.origin,
                link_enabled: this._linkEnabled,
                link_permission: this._linkPermission,
                members: this._buildMembersPayload(),
            }
            : {
                catalog_id: this.resourceId,
                origin: window.location.origin,
                company_visible: this._companyVisible,
                link_enabled: this._linkEnabled,
                link_permission: this._linkPermission,
                members: this._companyVisible ? null : this._buildMembersPayload(),
            };
        const result = accessRecord(await this._requireAccessPatch().run(patchPayload));
        if (result !== null) {
            const publicUrl = result.public_url;
            if (typeof publicUrl === 'string' && publicUrl.length > 0) {
                this._publicUrl = publicUrl;
            }
            this._linkEnabled = result.link_enabled === true;
            if (result.link_permission !== 'viewer' && result.link_permission !== 'editor') {
                throw new Error('office.access: link_permission must be viewer|editor');
            }
            this._linkPermission = result.link_permission;
            if (this._isCatalog()) {
                this._companyVisible = result.company_visible === true;
            }
        }
        this.close();
    }

    override renderHeader() {
        return this.t('access.modalTitle', { title: this.resourceTitle });
    }

    override renderSaveHeaderButton() {
        return html``;
    }

    override renderBody() {
        if (this._loading) {
            return html`<div><platform-spinner></platform-spinner></div>`;
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
                            ${this._members.map((member) => html`
                                <div class="member-row">
                                    <platform-user-chip user-id=${member.user_id}></platform-user-chip>
                                    <button class="remove-btn" type="button" @click=${() => this._removeMember(member.user_id)}>
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
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._query = typeof e.detail?.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                        <div class="candidate-list">
                            ${this._filteredCandidates().map((item: Record<string, unknown>) => html`
                                <button class="candidate-row" type="button" @click=${() => this._addMember(item.user_id as string)}>
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
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._setLinkPermission(e.detail?.value)}
                        ></platform-field>
                    </div>
                    ${this._linkEnabled ? html`
                        <div class="link-row">
                            ${this._publicUrl ? html`<span class="link-url">${this._publicUrl}</span>` : nothing}
                            <div class="link-actions">
                                ${this._publicUrl ? html`
                                    <button class="btn btn-secondary" type="button" @click=${this._copyPublicUrl}>
                                        ${this.t('access.copyLink')}
                                    </button>
                                ` : nothing}
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

    override renderFooter() {
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
