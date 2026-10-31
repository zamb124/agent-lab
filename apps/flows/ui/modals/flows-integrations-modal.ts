/**
 * flows-integrations-modal — OAuth credentials + Google Workspace Connect / company SA.
 *
 * User Connect: flows/google_workspace_authorize → location.assign(authorize_url).
 * Company SA: GET public status; admin PUT/DELETE.
 * List/disconnect: flows/integrations_list / flows/integrations_remove.
 */

import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/fields/platform-field.js';
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

function companyStatus(value: unknown): Record<string, unknown> | null {
    return isPlainObject(value) ? value : null;
}

function impersonateEmail(company: Record<string, unknown> | null): string | null {
    if (company === null) return null;
    const email = company.impersonate_email;
    return typeof email === 'string' ? email : null;
}

const WORKSPACE_SERVICES = new Set(['workspace', 'docs', 'sheets']);

export class FlowsIntegrationsModal extends PlatformModal {
    static modalKind = 'flows.integrations';
    static i18nNamespace = 'flows';

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .int-section {
                margin-bottom: var(--space-5);
                padding-bottom: var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            .int-section:last-of-type {
                border-bottom: none;
                margin-bottom: var(--space-3);
                padding-bottom: 0;
            }
            .int-section-title {
                margin: 0 0 var(--space-2);
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
            }
            .int-hint {
                margin: 0 0 var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                line-height: 1.4;
            }
            .int-status {
                margin: 0 0 var(--space-3);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .int-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .int-form {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                margin-top: var(--space-2);
            }
            .int-search {
                margin-bottom: var(--space-3);
            }
            .int-table {
                width: 100%;
                border-collapse: collapse;
                color: var(--text-secondary);
            }
            .int-table th,
            .int-table td {
                padding: var(--space-2);
                text-align: left;
                border-bottom: 1px solid var(--border-subtle);
            }
            .int-empty {
                text-align: center;
                color: var(--text-tertiary);
                padding: var(--space-4);
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        _query: { state: true },
        _saJsonDraft: { state: true },
        _impersonateDraft: { state: true },
    }
    declare _query: string;
    declare _saJsonDraft: string;
    declare _impersonateDraft: string;
;
    private _listOp: OpController;
    private _removeOp: OpController;
    private _authorizeOp: OpController;
    private _companyGetOp: OpController;
    private _companyPutOp: OpController;
    private _companyDeleteOp: OpController;
    private _authSelect: SelectController<{ activeCompanyId: string | null; user: AuthUser | null }>;

    constructor() {
        super();
        this.size = 'lg';
        this._query = '';
        this._saJsonDraft = '';
        this._impersonateDraft = '';
        this._listOp = this.useOp('flows/integrations_list');
        this._removeOp = this.useOp('flows/integrations_remove');
        this._authorizeOp = this.useOp('flows/google_workspace_authorize');
        this._companyGetOp = this.useOp('flows/google_workspace_company_get');
        this._companyPutOp = this.useOp('flows/google_workspace_company_put');
        this._companyDeleteOp = this.useOp('flows/google_workspace_company_delete');
        this._authSelect = this.select((s) => ({
            activeCompanyId: s.auth.activeCompanyId,
            user: s.auth.user,
        }));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._reload();
    }

    async _reload() {
        await Promise.all([
            this._listOp.run({}),
            this._companyGetOp.run({}),
        ]);
        const email = impersonateEmail(companyStatus(this._companyGetOp.lastResult));
        if (email !== null) {
            this._impersonateDraft = email;
        }
    }

    _listItems(): unknown[] {
        const result = this._listOp.lastResult;
        if (isPlainObject(result) && Array.isArray(result.items)) {
            return result.items;
        }
        if (Array.isArray(result)) {
            return result;
        }
        return [];
    }

    _userWorkspaceConnected() {
        return this._listItems().some((item) => this._isWorkspaceItem(item, null));
    }

    _userWorkspaceCredential(): Record<string, unknown> | null {
        const items = this._listItems();
        const canonical = items.find((item) => this._isWorkspaceItem(item, 'workspace'));
        if (isPlainObject(canonical)) {
            return canonical;
        }
        const found = items.find((item) => this._isWorkspaceItem(item, null));
        return isPlainObject(found) ? found : null;
    }

    _isWorkspaceItem(item: unknown, service: string | null): boolean {
        if (!isPlainObject(item) || item.provider !== 'google' || typeof item.service !== 'string') {
            return false;
        }
        if (service !== null) {
            return item.service === service;
        }
        return WORKSPACE_SERVICES.has(item.service);
    }

    async _connectWorkspace() {
        const returnPath = `${globalThis.location.pathname}${globalThis.location.search}`;
        const returnOrigin = globalThis.location.origin;
        const authorizeUrl = await this._authorizeOp.run({
            return_path: returnPath,
            return_origin: returnOrigin,
        });
        if (typeof authorizeUrl !== 'string' || authorizeUrl.length === 0) {
            throw new Error('flows-integrations-modal: empty authorize_url');
        }
        globalThis.location.assign(authorizeUrl);
    }

    async _disconnectWorkspace() {
        const cred = this._userWorkspaceCredential();
        if (!cred) {
            return;
        }
        await this._delete(cred);
    }

    async _saveCompanySa() {
        const json = this._saJsonDraft.trim();
        if (json.length === 0) {
            this.toast('integrations_modal.workspace_company_json_required', { type: 'error' });
            return;
        }
        await this._companyPutOp.run({
            service_account_json: json,
            impersonate_email: this._impersonateDraft.trim(),
        });
        this._saJsonDraft = '';
        await this._companyGetOp.run({});
        const email = impersonateEmail(companyStatus(this._companyGetOp.lastResult));
        this._impersonateDraft = email === null ? '' : email;
    }

    async _deleteCompanySa() {
        const ok = await platformConfirm(
            this.t('integrations_modal.workspace_company_delete_message'),
            {
                title: this.t('integrations_modal.workspace_company_delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('integrations_modal.action_delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._companyDeleteOp.run({});
        this._saJsonDraft = '';
        this._impersonateDraft = '';
        await this._companyGetOp.run({});
    }

    async _delete(item: Record<string, unknown>) {
        const provider = item.provider;
        const service = item.service;
        if (typeof provider !== 'string' || provider.length === 0 || typeof service !== 'string' || service.length === 0) {
            throw new Error('flows-integrations-modal: provider and service required');
        }
        const ok = await platformConfirm(
            this.t('integrations_modal.delete_message', { provider, service }),
            {
                title: this.t('integrations_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('integrations_modal.action_delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._removeOp.run({ provider, service });
        await this._listOp.run({});
    }

    _onSearchChange(e: CustomEvent) {
        const rawValue = e.detail.value;
        if (typeof rawValue !== 'string') {
            throw new TypeError('flows-integrations-modal: search expects string detail.value');
        }
        this._query = rawValue;
    }

    _filteredItems(): Record<string, unknown>[] {
        const query = this._query.trim().toLocaleLowerCase();
        const records: Record<string, unknown>[] = [];
        for (const item of this._listItems()) {
            if (!isPlainObject(item)) {
                throw new Error('flows-integrations-modal: integration must be an object');
            }
            if (query.length === 0) {
                records.push(item);
                continue;
            }
            const provider = typeof item.provider === 'string' ? item.provider : '';
            const service = typeof item.service === 'string' ? item.service : '';
            if (`${provider} ${service}`.toLocaleLowerCase().includes(query)) {
                records.push(item);
            }
        }
        return records;
    }

    _renderWorkspaceUserSection() {
        const connected = this._userWorkspaceConnected();
        const busy = this._authorizeOp.busy || this._removeOp.busy;
        return html`
            <section class="int-section">
                <h3 class="int-section-title">${this.t('integrations_modal.workspace_user_title')}</h3>
                <p class="int-hint">${this.t('integrations_modal.workspace_user_hint')}</p>
                <p class="int-status">
                    ${connected
                        ? this.t('integrations_modal.workspace_user_connected')
                        : this.t('integrations_modal.workspace_user_not_connected')}
                </p>
                <div class="int-actions">
                    <platform-button
                        ?disabled=${busy}
                        @click=${() => void this._connectWorkspace()}
                    >
                        ${connected
                            ? this.t('integrations_modal.workspace_reconnect')
                            : this.t('integrations_modal.workspace_connect')}
                    </platform-button>
                    ${connected
                        ? html`
                            <platform-button
                                danger
                                ?disabled=${busy}
                                @click=${() => void this._disconnectWorkspace()}
                            >
                                ${this.t('integrations_modal.action_disconnect')}
                            </platform-button>
                        `
                        : nothing}
                </div>
            </section>
        `;
    }

    _renderCompanySection() {
        const company = companyStatus(this._companyGetOp.lastResult);
        const configured = company !== null && company.configured === true;
        const email = impersonateEmail(company);
        const impersonate = email !== null && email.length > 0 ? email : '';
        const isAdmin = company !== null && company.can_admin === true;
        const busy = this._companyPutOp.busy || this._companyDeleteOp.busy || this._companyGetOp.busy;
        return html`
            <section class="int-section">
                <h3 class="int-section-title">${this.t('integrations_modal.workspace_company_title')}</h3>
                <p class="int-hint">${this.t('integrations_modal.workspace_company_hint')}</p>
                <p class="int-status">
                    ${configured
                        ? this.t('integrations_modal.workspace_company_configured', {
                            email: impersonate || this.t('integrations_modal.workspace_company_no_subject'),
                        })
                        : this.t('integrations_modal.workspace_company_not_configured')}
                </p>
                ${isAdmin
                    ? html`
                        <div class="int-form">
                            <platform-field
                                type="text"
                                mode="edit"
                                name="service_account_json"
                                .label=${this.t('integrations_modal.workspace_company_json_label')}
                                .value=${this._saJsonDraft}
                                @change=${(e: CustomEvent) => {
                                    this._saJsonDraft = typeof e.detail.value === 'string' ? e.detail.value : '';
                                }}
                            ></platform-field>
                            <platform-field
                                type="string"
                                mode="edit"
                                input-type="email"
                                name="impersonate_email"
                                .label=${this.t('integrations_modal.workspace_company_impersonate_label')}
                                .value=${this._impersonateDraft}
                                @change=${(e: CustomEvent) => {
                                    this._impersonateDraft = typeof e.detail.value === 'string' ? e.detail.value : '';
                                }}
                            ></platform-field>
                            <div class="int-actions">
                                <platform-button
                                    ?disabled=${busy}
                                    @click=${() => void this._saveCompanySa()}
                                >
                                    ${this.t('integrations_modal.workspace_company_save')}
                                </platform-button>
                                ${configured
                                    ? html`
                                        <platform-button
                                            danger
                                            ?disabled=${busy}
                                            @click=${() => void this._deleteCompanySa()}
                                        >
                                            ${this.t('integrations_modal.workspace_company_remove')}
                                        </platform-button>
                                    `
                                    : nothing}
                            </div>
                        </div>
                    `
                    : nothing}
            </section>
        `;
    }

    _renderRows() {
        const items = this._filteredItems();
        if (this._listOp.busy && items.length === 0 && this._query.trim().length === 0) {
            return html`<tr><td colspan="3"><platform-spinner></platform-spinner></td></tr>`;
        }
        if (items.length === 0) {
            return html`<tr><td colspan="3" class="int-empty">${this.t('integrations_modal.empty')}</td></tr>`;
        }
        return items.map((item) => {
            const provider = typeof item.provider === 'string' ? item.provider : '';
            const service = typeof item.service === 'string' ? item.service : '';
            return html`
            <tr>
                <td>${provider}</td>
                <td>${service}</td>
                <td>
                    <platform-button danger @click=${() => void this._delete(item)}>
                        ${this.t('integrations_modal.action_disconnect')}
                    </platform-button>
                </td>
            </tr>
        `;
        });
    }

    override renderHeader() {
        return this.t('integrations_modal.title');
    }

    override renderBody() {
        return html`
            ${this._renderWorkspaceUserSection()}
            ${this._renderCompanySection()}
            <section class="int-section">
                <h3 class="int-section-title">${this.t('integrations_modal.all_title')}</h3>
                <platform-modal-search-field
                    class="int-search"
                    layout="fill"
                    .value=${this._query}
                    placeholder=${this.t('integrations_modal.search')}
                    @change=${this._onSearchChange}
                ></platform-modal-search-field>
                <table class="int-table">
                    <thead>
                        <tr>
                            <th>${this.t('integrations_modal.col_provider')}</th>
                            <th>${this.t('integrations_modal.col_service')}</th>
                            <th>${this.t('integrations_modal.col_actions')}</th>
                        </tr>
                    </thead>
                    <tbody>${this._renderRows()}</tbody>
                </table>
            </section>
        `;
    }
}

customElements.define('flows-integrations-modal', FlowsIntegrationsModal);
registerModalKind(FlowsIntegrationsModal.modalKind, 'flows-integrations-modal');
