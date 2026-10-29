/**
 * CRMNamespaceModal — единая модалка создания и редактирования namespace.
 *
 * Свойства:
 *   - mode: 'create' | 'edit' — обязательный.
 *   - name?: string           — обязателен для mode='edit'.
 *
 * Поток (mode='create'):
 *   - templates подгружаются через `useResource('crm/templates', { autoload })`.
 *   - стартовый draft: template_id + пустые name/description.
 *   - submit → форма шлёт `namespacesResource.events.CREATE_REQUESTED`.
 *   - На CREATED — `setPlatformNamespaceSelection(company_id, name)` +
 *     `closeAfterSave()`.
 *
 * Поток (mode='edit'):
 *   - preflight `useOp('crm/namespace_editability')` для бейджа со статистикой.
 *   - стартовый draft: description из `namespacesResource.byId[name]`; name только для чтения.
 *   - submit → форма шлёт `namespaceUpdateOp.events.REQUESTED`.
 *   - На SUCCEEDED — `namespacesResource.load()` + `closeAfterSave()`.
 */

import { html, css, nothing } from 'lit';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';

function grantUserId(user: { user_id: string } | null): string {
    if (user === null || user.user_id.length === 0) {
        throw new Error('namespace-modal: grant user required');
    }
    return user.user_id;
}

function anyRecord(value: unknown): Record<string, unknown> | null {
    return isPlainRecord(value) ? value : null;
}

function recordList(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    const rows: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) {
            throw new Error('namespace-modal: list item must be an object');
        }
        rows.push(item);
    }
    return rows;
}
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { setPlatformNamespaceSelection } from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    FacetsController,
    FormController,
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const CREATE_FORM = 'crm/namespace_create_form';
const EDIT_FORM = 'crm/namespace_edit_form';
const TEMPLATES_NAME = 'crm/templates';
const NAMESPACES_NAME = 'crm/namespaces';
const EDITABILITY_OP = 'crm/namespace_editability';
const UPDATE_OP = 'crm/namespace_update';
const GRANTS_LIST_OP = 'crm/grants_list';
const GRANT_CREATE_OP = 'crm/grant_create';
const GRANT_REVOKE_OP = 'crm/grant_revoke';
const TEAM_SEARCH_FACETS = 'crm/team_search';

const MODE_CREATE = 'create';
const MODE_EDIT = 'edit';

const TAB_INFO = 'info';
const TAB_GRANTS = 'grants';

const SUBJECT_PUBLIC = 'public';
const SUBJECT_USER = 'user';
const SUBJECT_COMPANY = 'company';

const CRM_INTEGRATION_ICON_BASE = '/crm/ui/static/assets/integrations';

function crmIntegrationIconHref(providerId: unknown): string {
    if (typeof providerId !== 'string' || providerId.length === 0) {
        throw new Error('crmIntegrationIconHref: providerId required');
    }
    return `${CRM_INTEGRATION_ICON_BASE}/${encodeURIComponent(providerId)}.svg`;
}

const ROLE_VIEWER = 'viewer';
const ROLE_EDITOR = 'editor';
const ROLE_ADMIN = 'admin';
const ROLES = [ROLE_VIEWER, ROLE_EDITOR, ROLE_ADMIN];

export class CRMNamespaceModal extends PlatformFormModal {
    static modalKind = 'crm.namespace';
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        mode: { type: String },
        name: { type: String },
        _activeTab: { state: true },
        _grantSubject: { state: true },
        _grantRole: { state: true },
        _grantUserQuery: { state: true },
        _grantSelectedUser: { state: true },
        _grantCompanyId: { state: true },
        _grantSubmitError: { state: true },
    };
    declare mode: string;
    declare name: string;
    declare _activeTab: string;
    declare _grantSubject: string;
    declare _grantRole: string;
    declare _grantUserQuery: string;
    declare _grantSelectedUser: { user_id: string; label: string } | null;
    declare _grantCompanyId: string;
    declare _grantSubmitError: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-4); }

            /* Строка только для раскладки: без наложения pill chrome .form-group и inner .field-pill из platform-field. */
            .crm-namespace-field-row {
                display: flex;
                flex-direction: column;
                gap: var(--field-pill-gap);
                margin-bottom: var(--space-6);
                min-width: 0;
            }
            .crm-namespace-field-row:last-child {
                margin-bottom: 0;
            }

            .template-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
            .template-card {
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                background: var(--crm-surface-muted);
                padding: var(--space-3);
                cursor: pointer;
                text-align: left;
                transition: border-color var(--duration-fast),
                            background var(--duration-fast),
                            transform var(--duration-fast);
            }
            .template-card:hover {
                border-color: var(--crm-selected-stroke);
                transform: translateY(-1px);
            }
            .template-card.active {
                border-color: var(--crm-selected-stroke);
                background: var(--crm-selected-bg);
            }
            .template-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 600;
                margin-bottom: var(--space-1);
            }
            .template-description {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.4;
            }
            .template-id {
                margin-top: var(--space-2);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-full);
                display: inline-flex;
                padding: 2px var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }

            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            .form-label-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .empty-templates {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }

            .meta {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
            }
            .meta-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .meta-row strong { color: var(--text-primary); font-weight: 600; }
            .meta-loading { color: var(--text-tertiary); font-style: italic; }

            .modal-actions {
                display: none !important;
            }

            .namespace-integrations {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 6px;
            }
            .namespace-integration-icon-wrap {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                overflow: hidden;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: #242428;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            .namespace-integration-icon {
                width: 70%;
                height: 70%;
                object-fit: contain;
                display: block;
            }
            .integrations-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .tabs {
                display: flex;
                gap: 2px;
                border-bottom: 1px solid var(--crm-stroke);
                margin-bottom: var(--space-3);
            }
            .tab {
                padding: var(--space-2) var(--space-3);
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                margin-bottom: -1px;
            }
            .tab.active {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
            }

            .grants-list {
                display: grid;
                gap: var(--space-2);
            }
            .grant-item {
                display: grid;
                grid-template-columns: auto 1fr auto auto;
                gap: var(--space-2);
                align-items: center;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
            }
            .grant-icon {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-sm);
            }
            .grant-content { display: grid; gap: 2px; min-width: 0; }
            .grant-target {
                font-size: var(--text-sm);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .grant-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .grant-role {
                padding: 2px 8px;
                border-radius: var(--radius-full);
                background: var(--crm-selected-bg);
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .revoke-btn {
                background: transparent;
                border: none;
                color: var(--color-danger);
                cursor: pointer;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
            }
            .revoke-btn:hover:not(:disabled) {
                background: rgba(244, 63, 94, 0.1);
            }
            .empty-block {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
            }

            .grant-form {
                display: grid;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface-muted);
                margin-top: var(--space-3);
            }
            .field-label {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .subject-chips {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .subject-chip {
                display: grid;
                gap: 2px;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                cursor: pointer;
                text-align: left;
            }
            .subject-chip.picked {
                border-color: var(--accent);
                background: var(--crm-selected-bg);
            }
            .subject-chip:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .subject-chip .chip-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: 500;
            }
            .subject-chip .chip-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .role-chips {
                display: flex;
                gap: var(--space-2);
            }
            .role-chip {
                padding: 4px 12px;
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .role-chip.picked {
                border-color: var(--accent);
                background: var(--accent);
                color: white;
            }
            .text-input, .date-input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-size: var(--text-sm);
                box-sizing: border-box;
            }
            .typeahead {
                display: grid;
                gap: var(--space-2);
            }
            .typeahead .selected {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px var(--space-2);
                background: var(--crm-selected-bg);
                border: 1px solid var(--accent);
                border-radius: var(--radius-full);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: fit-content;
            }
            .clear-btn {
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
                display: inline-flex;
                align-items: center;
            }
            .results {
                display: grid;
                gap: 2px;
                max-height: 180px;
                overflow-y: auto;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
            }
            .result-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                border: none;
                background: transparent;
                color: var(--text-primary);
                text-align: left;
                font-size: var(--text-sm);
            }
            .result-row:hover { background: var(--crm-selected-bg); }
            .result-row .email {
                margin-left: auto;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .hint-row {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .submit-error {
                color: var(--color-danger);
                font-size: var(--text-sm);
            }
            .grant-form-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
            }

            .create-body-wrap {
                position: relative;
                min-height: 120px;
            }
            .create-busy-overlay {
                position: absolute;
                inset: 0;
                z-index: 2;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--crm-surface) 86%, var(--text-primary) 14%);
                pointer-events: all;
            }
            .create-busy-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                text-align: center;
            }
        `,
    ];

    private _createForm: FormController;
    private _editForm: FormController;
    private _namespaces: ResourceController;
    private _templates: ResourceController;
    private _editability: OpController;
    private _update: OpController;
    private _grantsListOp: OpController;
    private _grantCreateOp: OpController;
    private _grantRevokeOp: OpController;
    private _teamSearch: FacetsController;
    private _authSel: SelectController<AuthUser | null>;
    private _templateSeeded: boolean;
    private _editSeedAttempted: boolean;
    private _grantsLoaded: boolean;

    constructor() {
        super();
        this.size = 'xl';
        this.headerSavePrimary = true;
        this.mode = '';
        this.name = '';

        this._activeTab = TAB_INFO;
        this._grantSubject = SUBJECT_USER;
        this._grantRole = ROLE_VIEWER;
        this._grantUserQuery = '';
        this._grantSelectedUser = null;
        this._grantCompanyId = '';
        this._grantSubmitError = '';

        this._createForm = this.useForm(CREATE_FORM);
        this._editForm = this.useForm(EDIT_FORM);
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._templates = this.useResource(TEMPLATES_NAME);
        this._editability = this.useOp(EDITABILITY_OP);
        this._update = this.useOp(UPDATE_OP);
        this._grantsListOp = this.useOp(GRANTS_LIST_OP);
        this._grantCreateOp = this.useOp(GRANT_CREATE_OP);
        this._grantRevokeOp = this.useOp(GRANT_REVOKE_OP);
        this._teamSearch = this.useFacets(TEAM_SEARCH_FACETS);

        this._authSel = this.select((state) => state.auth.user);
        this._templateSeeded = false;
        this._editSeedAttempted = false;
        this._grantsLoaded = false;
    }

    _formLabelWithHint(labelKey: string, hintKey: string): TemplateResult {
        return html`
            <div class="form-label-row">
                <span class="form-label">${this.t(labelKey)}</span>
                <platform-help-hint
                    .text=${this.t(hintKey)}
                    label=${this.t('templates_page.field_hint_button_aria')}
                ></platform-help-hint>
            </div>
        `;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (this.mode !== MODE_CREATE && this.mode !== MODE_EDIT) {
            throw new Error(`CRMNamespaceModal: prop "mode" must be 'create' or 'edit', got '${this.mode}'`);
        }
        if (this.mode === MODE_EDIT && (typeof this.name !== 'string' || this.name.length === 0)) {
            throw new Error('CRMNamespaceModal: prop "name" required for mode=edit');
        }

        if (this.mode === MODE_CREATE) {
            this._createForm.openForm({ template_id: '', name: '', description: '' });
            this._templates.load();
            this.useEvent(this._namespaces.resource.events.CREATED, (event) => {
                const payload = anyRecord(event.payload);
                const item = payload === null ? null : anyRecord(payload.item);
                if (item === null) {
                    throw new Error('namespace-modal: created item required');
                }
                this._onCreated(item);
            });
            this.useEvent(this._namespaces.resource.events.CREATE_FAILED, () => {
                this._createForm.openForm(this._createForm.draft);
            });
            return;
        }

        this._editForm.openForm({ name: '', description: '' });
        this.useEvent(this._update.op.events.SUCCEEDED, () => this.closeAfterSave());
        this.useEvent(this._update.op.events.FAILED, () => {
            this._editForm.openForm(this._editForm.draft);
        });

        this.useEvent(this._grantCreateOp.op.events.SUCCEEDED, () => this._resetGrantForm());
        this.useEvent(this._grantCreateOp.op.events.FAILED, (event) => {
            const payload = anyRecord(event.payload);
            const message = payload !== null && typeof payload.message === 'string'
                ? payload.message
                : this.t('namespace_modal.grants_submit_failed');
            this._grantSubmitError = message;
        });
    }

    override disconnectedCallback(): void {
        this._activeForm().close();
        super.disconnectedCallback();
    }

    _activeForm() {
        return this.mode === MODE_CREATE ? this._createForm : this._editForm;
    }

    _isCreate() { return this.mode === MODE_CREATE; }

    _isCreateOperationBusy() {
        if (!this._isCreate()) return false;
        return this._createForm.submitting || this._namespaces.createInFlight;
    }

    _onPickTab(tab: string) {
        if (tab !== TAB_INFO && tab !== TAB_GRANTS) return;
        this._activeTab = tab;
        if (tab === TAB_GRANTS && !this._grantsLoaded) {
            this._reloadGrants();
            this._grantsLoaded = true;
        }
    }

    _reloadGrants() {
        this._grantsListOp.run({ resource_type: 'namespace', resource_id: this.name });
    }

    _resetGrantForm() {
        this._grantSubject = SUBJECT_USER;
        this._grantRole = ROLE_VIEWER;
        this._grantUserQuery = '';
        this._grantSelectedUser = null;
        this._grantCompanyId = '';
        this._grantSubmitError = '';
    }

    _grants(): Record<string, unknown>[] {
        const result = anyRecord(this._grantsListOp.lastResult);
        if (result === null || !Array.isArray(result.items)) return [];
        return recordList(result.items);
    }

    _hasPublicGrant() {
        return this._grants().some((grant) => grant.grant_type === SUBJECT_PUBLIC);
    }

    _onPickSubject(subject: string) {
        this._grantSubject = subject;
        this._grantSubmitError = '';
    }

    _onPickRole(role: string) {
        this._grantRole = role;
    }

    _onUserQueryInput(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('namespace-modal: user query input required');
        }
        const value = input.value;
        this._grantUserQuery = value;
        this._teamSearch.search('users', value);
    }

    _onUserPick(user: Record<string, unknown>) {
        const userId = user.user_id;
        if (typeof userId !== 'string' || userId.length === 0) {
            throw new Error('namespace-modal: grant user required');
        }
        const name = typeof user.name === 'string' ? user.name : '';
        const email = typeof user.email === 'string' ? user.email : '';
        this._grantSelectedUser = {
            user_id: userId,
            label: email.length > 0 ? `${name} <${email}>` : name,
        };
        this._grantUserQuery = '';
    }

    _onUserClear() {
        this._grantSelectedUser = null;
    }

    _onCompanyIdInput(e: CustomEvent) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('namespace-modal: company id field expects change detail.value string');
        }
        this._grantCompanyId = e.detail.value;
    }

    _validateGrantBeforeSubmit() {
        if (this._grantSubject === SUBJECT_USER) {
            if (!this._grantSelectedUser || typeof this._grantSelectedUser.user_id !== 'string' || this._grantSelectedUser.user_id.length === 0) {
                return this.t('namespace_modal.grants_err_pick_user');
            }
        }
        if (this._grantSubject === SUBJECT_COMPANY) {
            if (typeof this._grantCompanyId !== 'string' || this._grantCompanyId.trim().length === 0) {
                return this.t('namespace_modal.grants_err_company_id_required');
            }
        }
        return null;
    }

    _onSubmitGrant() {
        const error = this._validateGrantBeforeSubmit();
        if (typeof error === 'string') {
            this._grantSubmitError = error;
            return;
        }
        this._grantSubmitError = '';

        if (this._grantSubject === SUBJECT_USER) {
            this._grantCreateOp.run({
                resource_type: 'namespace',
                resource_id: this.name,
                subject: SUBJECT_USER,
                user_id: grantUserId(this._grantSelectedUser),
                role: this._grantRole,
            });
            return;
        }
        this._grantCreateOp.run({
            resource_type: 'namespace',
            resource_id: this.name,
            subject: SUBJECT_COMPANY,
            company_id: this._grantCompanyId.trim(),
            role: this._grantRole,
        });
    }

    _onRevokeGrant(grantId: string) {
        this._grantRevokeOp.run({ grant_id: grantId });
    }

    _iconForSubject(subject: string): string {
        if (subject === SUBJECT_PUBLIC) return 'globe';
        if (subject === SUBJECT_USER) return 'user';
        if (subject === SUBJECT_COMPANY) return 'building';
        return 'lock';
    }

    _formatGrantTarget(grant: Record<string, unknown>): string {
        const grantType = grant.grant_type;
        if (typeof grantType !== 'string' || grantType.length === 0) {
            throw new Error('namespace-modal: grant_type required');
        }
        if (grantType === SUBJECT_PUBLIC) return this.t('namespace_modal.grants_target_public');
        if (grantType === SUBJECT_USER) {
            const target = grant.target_user_id;
            return typeof target === 'string' && target.length > 0
                ? target
                : this.t('namespace_modal.grants_target_user_unknown');
        }
        if (grantType === SUBJECT_COMPANY) {
            const target = grant.target_company_id;
            return typeof target === 'string' && target.length > 0
                ? target
                : this.t('namespace_modal.grants_target_company_unknown');
        }
        return grantType;
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (this._isCreate()) {
            this._maybeSeedTemplate();
            this.isDirty = this._isCreateDraftDirty();
            return;
        }
        this._maybeSeedEdit();
        this.isDirty = this._isEditDraftDirty();
    }

    _maybeSeedTemplate() {
        if (this._templateSeeded) return;
        const items = this._templates.items;
        if (items.length === 0) return;
        const draft = this._createForm.draft;
        if (typeof draft.template_id === 'string' && draft.template_id.length > 0) {
            this._templateSeeded = true;
            return;
        }
        const first = items[0];
        if (!isPlainRecord(first) || typeof first.template_id !== 'string' || first.template_id.length === 0) {
            throw new Error('namespace-modal: template_id required');
        }
        this._createForm.setField('template_id', first.template_id);
        this._templateSeeded = true;
    }

    _maybeSeedEdit() {
        if (this._editSeedAttempted) return;
        const item = this._namespaces.byId[this.name];
        if (!item) {
            if (!this._namespaces.loading) this._namespaces.load();
            return;
        }
        this._editSeedAttempted = true;
        const description = typeof item.description === 'string' ? item.description : '';
        this._editForm.openForm({ name: this.name, description });
        this._editability.run({ name: this.name });
        this._namespaces.get(this.name);
    }

    _isCreateDraftDirty() {
        const draft = this._createForm.draft;
        if (typeof draft.name === 'string' && draft.name.length > 0) return true;
        if (typeof draft.description === 'string' && draft.description.length > 0) return true;
        return false;
    }

    _isEditDraftDirty() {
        if (!this._editSeedAttempted) return false;
        const item = this._namespaces.byId[this.name];
        if (!item) return false;
        const original = typeof item.description === 'string' ? item.description : '';
        const draft = typeof this._editForm.draft.description === 'string' ? this._editForm.draft.description : '';
        return original.trim() !== draft.trim();
    }

    _onCreated(item: Record<string, unknown>) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('CRMNamespaceModal: cannot select created namespace without company_id');
        }
        const namespaceName = item.name;
        if (typeof namespaceName !== 'string' || namespaceName.length === 0) {
            throw new Error('CRMNamespaceModal: created namespace name required');
        }
        setPlatformNamespaceSelection(user.company_id, namespaceName);
        this.closeAfterSave();
    }

    _onTemplateSelect(template_id: string) {
        this._createForm.setField('template_id', template_id);
    }

    _onNameChange(event: CustomEvent<{ value?: unknown }>) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._createForm.setField('name', v);
    }

    _onDescriptionChange(event: CustomEvent) {
        const v = event.detail && typeof event.detail.value === 'string' ? event.detail.value : '';
        this._activeForm().setField('description', v);
    }

    _onOpenNamespaceSettings() {
        if (typeof this.name !== 'string' || this.name.length === 0) {
            throw new Error('CRMNamespaceModal: name required to open namespace settings');
        }
        this.navigate('namespace', { itemId: this.name });
        this.close();
    }

    override async _performSave() {
        this._activeForm().submit();
    }

    override _saveHeaderTitle() {
        const submitting = this._isCreate() ? this._createForm.submitting : this._update.busy;
        if (submitting) return this.t('namespace_modal.action_saving');
        return this._isCreate()
            ? this.t('namespace_modal.action_create')
            : this.t('namespace_modal.action_save');
    }

    override renderHeader() {
        return this._isCreate()
            ? this.t('namespace_modal.header_create')
            : this.t('namespace_modal.header_edit');
    }

    override renderHeaderActions() {
        if (this._isCreate()) {
            return nothing;
        }
        if (this._activeTab !== TAB_INFO) {
            return nothing;
        }
        if (typeof this.name !== 'string' || this.name.length === 0) {
            return nothing;
        }
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('namespace_modal.action_open_namespace_settings')}
                aria-label=${this.t('namespace_modal.action_open_namespace_settings')}
                @click=${() => this._onOpenNamespaceSettings()}
            >
                <platform-icon name="arrow-right" size="16"></platform-icon>
            </button>
        `;
    }

    override renderSaveHeaderButton(): TemplateResult {
        if (this._isCreate()) {
            const draft = this._createForm.draft;
            const has_name = typeof draft.name === 'string' && draft.name.trim().length > 0;
            const has_template = typeof draft.template_id === 'string' && draft.template_id.length > 0;
            const disabled = this._createForm.submitting || !has_name || !has_template;
            return this._renderHeaderSaveIcon({
                onClick: () => this._performSave(),
                disabled,
                title: this._saveHeaderTitle(),
            });
        }
        if (this._activeTab !== TAB_INFO) return html``;
        const disabled = this._update.busy || !this._editSeedAttempted || !this.isDirty;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled,
            title: this._saveHeaderTitle(),
        });
    }

    _renderTemplates() {
        const items = this._templates.items;
        if (this._templates.loading && items.length === 0) {
            return html`<div class="empty-templates"><glass-spinner></glass-spinner></div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty-templates">${this.t('namespace_modal.templates_empty')}</div>`;
        }
        const draft = this._createForm.draft;
        return html`
            <div class="template-grid">
                ${recordList(items).map((template) => {
                    const templateId = template.template_id;
                    if (typeof templateId !== 'string' || templateId.length === 0) {
                        throw new Error('namespace-modal: template_id required');
                    }
                    const templateName = typeof template.name === 'string' ? template.name : templateId;
                    const templateDescription = typeof template.description === 'string' ? template.description : '';
                    return html`
                    <button
                        type="button"
                        class="template-card ${draft.template_id === templateId ? 'active' : ''}"
                        @click=${() => this._onTemplateSelect(templateId)}
                    >
                        <div class="template-title">
                            <platform-icon name=${this._templateIcon(template.icon)} size="16"></platform-icon>
                            ${templateName}
                        </div>
                        <div class="template-description">
                            ${templateDescription.length > 0 ? templateDescription : this.t('namespace_modal.template_no_description')}
                        </div>
                        <div class="template-id">${templateId}</div>
                    </button>
                `;
                })}
            </div>
        `;
    }

    _templateIcon(icon: unknown): string {
        if (typeof icon !== 'string') return 'folder';
        const value = icon.trim();
        return value.length === 0 ? 'folder' : value;
    }

    _namespaceItemForEdit(): Record<string, unknown> | null {
        if (this._isCreate() || typeof this.name !== 'string' || this.name.length === 0) {
            return null;
        }
        return anyRecord(this._namespaces.byId[this.name]);
    }

    _connectedIntegrationBadges(item: Record<string, unknown> | null): Record<string, unknown>[] {
        if (!item || !Array.isArray(item.integration_badges)) {
            throw new Error('CRMNamespaceModal: integration_badges required');
        }
        const badges: Record<string, unknown>[] = [];
        for (const badge of item.integration_badges) {
            if (!isPlainRecord(badge)) continue;
            if (badge.connected !== true) continue;
            if (typeof badge.provider_id !== 'string' || badge.provider_id.length === 0) continue;
            badges.push(badge);
        }
        return badges;
    }

    _renderEditIntegrationsRow(item: Record<string, unknown>): TemplateResult {
        const badges = this._connectedIntegrationBadges(item);
        return html`
            <div class="form-group">
                ${this._formLabelWithHint('namespace_modal.label_integrations', 'namespace_modal.label_integrations_hint')}
                ${badges.length === 0
                    ? html`<p class="integrations-hint">${this.t('namespace_modal.integrations_empty')}</p>`
                    : html`
                        <div
                            class="namespace-integrations"
                            aria-label=${this.t('namespace_modal.integrations_aria')}
                        >
                            ${badges.map((badge) => {
                                const providerId = badge.provider_id;
                                if (typeof providerId !== 'string' || providerId.length === 0) {
                                    throw new Error('namespace-modal: provider_id required');
                                }
                                return html`
                                    <span
                                        class="namespace-integration-icon-wrap"
                                        title=${providerId}
                                    >
                                        <img
                                            class="namespace-integration-icon"
                                            src=${crmIntegrationIconHref(providerId)}
                                            alt=""
                                            loading="lazy"
                                            decoding="async"
                                        />
                                    </span>
                                `;
                            })}
                        </div>
                    `}
            </div>
        `;
    }

    _fieldError(field: string): string {
        const error_key = this._activeForm().errors[field];
        return error_key ? this.t(error_key) : '';
    }

    _renderFieldError(field: string): TemplateResult | null {
        const text = this._fieldError(field);
        if (!text) return null;
        return html`<div class="form-error">${text}</div>`;
    }

    _renderEditabilityBadge() {
        const result = anyRecord(this._editability.lastResult);
        if (this._editability.busy && !result) {
            return html`<div class="meta-loading"><glass-spinner></glass-spinner></div>`;
        }
        if (!result) return null;
        const usedTypeIds = result.used_type_ids;
        if (!Array.isArray(usedTypeIds)) {
            throw new Error('namespace-modal: used_type_ids required');
        }
        return html`
            <div class="meta">
                <div class="meta-row">
                    <span>${this.t('namespace_modal.entity_count')}</span>
                    <strong>${result.entity_count}</strong>
                </div>
                <div class="meta-row">
                    <span>${this.t('namespace_modal.used_types')}</span>
                    <strong>${usedTypeIds.length}</strong>
                </div>
                <div class="meta-row">
                    <span>${this.t('namespace_modal.can_update_types')}</span>
                    <strong>${result.can_update_allowed_types ? this.t('namespace_modal.yes') : this.t('namespace_modal.no')}</strong>
                </div>
            </div>
        `;
    }

    override renderBody() {
        if (this._isCreate()) return this._renderCreateBody();
        return this._renderEditBody();
    }

    _renderCreateBody() {
        const busy = this._isCreateOperationBusy();
        return html`
            <div class="create-body-wrap">
                ${this._renderCreateFormInner()}
                ${busy
                    ? html`
                        <div
                            class="create-busy-overlay"
                            role="status"
                            aria-live="polite"
                            aria-busy="true"
                        >
                            <glass-spinner size="lg"></glass-spinner>
                            <span class="create-busy-label">${this.t('namespace_modal.creating_progress')}</span>
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }

    _renderCreateFormInner() {
        const draft = this._createForm.draft;
        return html`
            <form class="form-grid" @submit=${(event: Event) => { event.preventDefault(); this._performSave(); }}>
                <div class="form-group">
                    ${this._formLabelWithHint('namespace_modal.label_template', 'namespace_modal.label_template_hint')}
                    ${this._renderTemplates()}
                    ${this._renderFieldError('template_id')}
                    <div class="hint">${this.t('namespace_modal.template_hint')}</div>
                </div>

                <div class="crm-namespace-field-row">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('namespace_modal.label_name')}
                        .hint=${this.t('namespace_modal.name_hint')}
                        .placeholder=${this.t('namespace_modal.name_placeholder')}
                        .value=${draft.name}
                        .error=${this._fieldError('name')}
                        ?disabled=${this._createForm.submitting}
                        @change=${this._onNameChange}
                    ></platform-field>
                </div>

                <div class="crm-namespace-field-row">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('namespace_modal.label_description')}
                        .hint=${this.t('namespace_modal.label_description_hint')}
                        .placeholder=${this.t('namespace_modal.description_placeholder')}
                        .value=${draft.description}
                        .error=${this._fieldError('description')}
                        ?disabled=${this._createForm.submitting}
                        @change=${this._onDescriptionChange}
                    ></platform-field>
                </div>
            </form>
        `;
    }

    _renderEditBody() {
        return html`
            <div class="tabs">
                <button
                    type="button"
                    class="tab ${this._activeTab === TAB_INFO ? 'active' : ''}"
                    @click=${() => this._onPickTab(TAB_INFO)}
                >${this.t('namespace_modal.tab_info')}</button>
                <button
                    type="button"
                    class="tab ${this._activeTab === TAB_GRANTS ? 'active' : ''}"
                    @click=${() => this._onPickTab(TAB_GRANTS)}
                >${this.t('namespace_modal.tab_grants')}</button>
            </div>
            ${this._activeTab === TAB_INFO ? this._renderEditInfoBody() : this._renderEditGrantsBody()}
        `;
    }

    _renderEditInfoBody() {
        const draft = this._editForm.draft;
        const nsItem = this._namespaceItemForEdit();
        return html`
            <form class="form-grid" @submit=${(event: Event) => { event.preventDefault(); this._performSave(); }}>
                <div class="crm-namespace-field-row">
                    <platform-field
                        type="string"
                        mode="view"
                        .label=${this.t('namespace_modal.label_name')}
                        .hint=${this.t('namespace_modal.label_name_readonly_hint')}
                        .value=${draft.name}
                    >
                        <platform-icon slot="prefix" name="folder" size="14"></platform-icon>
                    </platform-field>
                </div>

                <div class="crm-namespace-field-row">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('namespace_modal.label_description')}
                        .hint=${this.t('namespace_modal.label_description_hint')}
                        .placeholder=${this.t('namespace_modal.description_placeholder')}
                        .value=${draft.description}
                        ?disabled=${this._update.busy}
                        @change=${this._onDescriptionChange}
                    ></platform-field>
                </div>

                ${nsItem !== null ? this._renderEditIntegrationsRow(nsItem) : nothing}

                <div class="crm-namespace-field-row">
                    ${this._renderEditabilityBadge()}
                </div>
            </form>
        `;
    }

    _renderEditGrantsBody() {
        const grants = this._grants();
        const loading = this._grantsListOp.busy && grants.length === 0;
        return html`
            <div class="form-grid">
                ${loading
                    ? html`<div class="empty-block"><glass-spinner></glass-spinner></div>`
                    : grants.length === 0
                        ? html`<div class="empty-block">${this.t('namespace_modal.grants_empty')}</div>`
                        : html`
                            <div class="grants-list">
                                ${grants.map((grant) => this._renderGrantItem(grant))}
                            </div>
                        `}
                ${this._renderGrantForm()}
            </div>
        `;
    }

    _renderGrantItem(grant: Record<string, unknown>): TemplateResult {
        const target = this._formatGrantTarget(grant);
        return html`
            <div class="grant-item">
                <div class="grant-icon">
                    <platform-icon name=${this._iconForSubject(typeof grant.grant_type === 'string' ? grant.grant_type : '')} size="14"></platform-icon>
                </div>
                <div class="grant-content">
                    <div class="grant-target">${target}</div>
                </div>
                <span class="grant-role">${this.t(`namespace_modal.grants_role_${typeof grant.role === 'string' ? grant.role : ''}`)}</span>
                <button
                    type="button"
                    class="revoke-btn"
                    ?disabled=${this._grantRevokeOp.busy}
                    @click=${() => {
                        const grantId = grant.grant_id;
                        if (typeof grantId !== 'string' || grantId.length === 0) {
                            throw new Error('namespace-modal: grant_id required');
                        }
                        this._onRevokeGrant(grantId);
                    }}
                >
                    ${this.t('namespace_modal.grants_revoke')}
                </button>
            </div>
        `;
    }

    _renderGrantForm() {
        const busy = this._grantCreateOp.busy;
        return html`
            <div class="grant-form">
                <div class="field-label">${this.t('namespace_modal.grants_add_title')}</div>
                <div>
                    <div class="field-label">${this.t('namespace_modal.grants_subject_label')}</div>
                    <div class="subject-chips">
                        ${this._renderSubjectChip(SUBJECT_USER, 'user', false)}
                        ${this._renderSubjectChip(SUBJECT_COMPANY, 'building', false)}
                    </div>
                </div>
                ${this._grantSubject === SUBJECT_USER ? this._renderUserPicker() : nothing}
                ${this._grantSubject === SUBJECT_COMPANY ? this._renderCompanyInput() : nothing}
                ${this._renderRolePicker()}
                ${this._grantSubmitError.length > 0
                    ? html`<div class="submit-error">${this._grantSubmitError}</div>`
                    : nothing}
                <div class="grant-form-actions">
                    <button
                        type="button"
                        class="btn btn-primary"
                        ?disabled=${busy}
                        @click=${() => this._onSubmitGrant()}
                    >
                        ${busy
                            ? this.t('namespace_modal.grants_submitting')
                            : this.t('namespace_modal.grants_submit')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderSubjectChip(subject: string, icon: string, disabled: boolean): TemplateResult {
        const picked = this._grantSubject === subject;
        return html`
            <button
                type="button"
                class="subject-chip ${picked ? 'picked' : ''}"
                ?disabled=${disabled && !picked}
                @click=${() => this._onPickSubject(subject)}
            >
                <span class="chip-title">
                    <platform-icon name=${icon} size="14"></platform-icon>
                    ${this.t(`namespace_modal.grants_subject_${subject}`)}
                </span>
                <span class="chip-desc">${this.t(`namespace_modal.grants_subject_${subject}_desc`)}</span>
            </button>
        `;
    }

    _renderRolePicker() {
        return html`
            <div>
                <div class="field-label">${this.t('namespace_modal.grants_role_label')}</div>
                <div class="role-chips">
                    ${ROLES.map((role) => html`
                        <button
                            type="button"
                            class="role-chip ${this._grantRole === role ? 'picked' : ''}"
                            @click=${() => this._onPickRole(role)}
                        >${this.t(`namespace_modal.grants_role_${role}`)}</button>
                    `)}
                </div>
            </div>
        `;
    }

    _renderUserPicker() {
        const items = recordList(this._teamSearch.items('users'));
        const loading = this._teamSearch.loading('users');
        return html`
            <div>
                <div class="field-label">${this.t('namespace_modal.grants_user_label')}</div>
                <div class="typeahead">
                    ${this._grantSelectedUser !== null
                        ? html`
                            <span class="selected">
                                <platform-icon name="user" size="12"></platform-icon>
                                ${this._grantSelectedUser.label}
                                <button
                                    type="button"
                                    class="clear-btn"
                                    title=${this.t('namespace_modal.grants_user_clear')}
                                    @click=${() => this._onUserClear()}
                                >
                                    <platform-icon name="close" size="12"></platform-icon>
                                </button>
                            </span>
                        `
                        : html`
                            <input
                                type="text"
                                class="text-input"
                                data-canon="search-as-you-type"
                                placeholder=${this.t('namespace_modal.grants_user_placeholder')}
                                .value=${this._grantUserQuery}
                                @input=${this._onUserQueryInput}
                            />
                            ${this._grantUserQuery.length >= 2
                                ? html`
                                    <div class="results">
                                        ${loading
                                            ? html`<div class="hint-row" style="padding: var(--space-2);">${this.t('namespace_modal.grants_user_searching')}</div>`
                                            : items.length === 0
                                                ? html`<div class="hint-row" style="padding: var(--space-2);">${this.t('namespace_modal.grants_user_no_results')}</div>`
                                                : items.map((user) => {
                                                    const userId = user.user_id;
                                                    if (typeof userId !== 'string' || userId.length === 0) {
                                                        throw new Error('namespace-modal: search user required');
                                                    }
                                                    const name = typeof user.name === 'string' ? user.name : '';
                                                    const email = typeof user.email === 'string' ? user.email : '';
                                                    return html`
                                                    <button type="button" class="result-row" @click=${() => this._onUserPick(user)}>
                                                        <platform-icon name="user" size="14"></platform-icon>
                                                        <span>${name}</span>
                                                        ${email.length > 0 ? html`<span class="email">${email}</span>` : nothing}
                                                    </button>
                                                `;
                                                })}
                                    </div>
                                `
                                : html`<div class="hint-row">${this.t('namespace_modal.grants_user_min_query')}</div>`}
                        `}
                </div>
            </div>
        `;
    }

    _renderCompanyInput() {
        return html`
            <platform-field
                type="string"
                mode="edit"
                label=${this.t('namespace_modal.grants_company_id_label')}
                placeholder=${this.t('namespace_modal.grants_company_id_placeholder')}
                .value=${this._grantCompanyId}
                @change=${this._onCompanyIdInput}
            ></platform-field>
        `;
    }

    override renderFooter(): TemplateResult {
        return html``;
    }
}

customElements.define('crm-namespace-modal', CRMNamespaceModal);
registerModalKind(CRMNamespaceModal.modalKind, 'crm-namespace-modal');
