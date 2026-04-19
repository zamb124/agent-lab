/**
 * CRMShareModal — управление доступом к сущности (entity grants).
 *
 * Props:
 *   - entityId: string — обязательный, сущность для шаринга.
 *
 * Поток:
 *   1. На open: `entitiesResource.get(entityId)` подгружает имя/тип/namespace
 *      для шапки; `entityGrantsListOp.run({ entity_id })` загружает текущие
 *      гранты. Список грантов читается из `_grantsListOp.lastResult.items`.
 *   2. UI разделён на две части:
 *        - список существующих грантов (public/user/company с ролью + revoke);
 *        - форма создания нового гранта.
 *   3. Форма создания:
 *        - subject (radio): public | user | company.
 *        - role (chip): viewer | editor | admin.
 *        - expires_at (date, опциональный) — переводится в ISO для backend.
 *        - для subject=user — typeahead через `teamSearchFacets.users` (поиск
 *          по имени/email; выбранный пользователь хранится локально как
 *          { user_id, label }).
 *        - для subject=company — текстовый ввод company_id.
 *        - для subject=public — никаких дополнительных полей.
 *   4. Submit → `entityGrantCreateOp.run({ entity_id, subject, body })`.
 *      На SUCCEEDED перезагружаем список и сбрасываем форму.
 *   5. Revoke → `grantRevokeOp.run({ grant_id })`. На SUCCEEDED — refresh.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const ENTITIES_NAME = 'crm/entities';
const GRANTS_LIST_OP = 'crm/entity_grants_list';
const GRANT_CREATE_OP = 'crm/entity_grant_create';
const GRANT_REVOKE_OP = 'crm/grant_revoke';
const TEAM_SEARCH_FACETS = 'crm/team_search';

const SUBJECT_PUBLIC = 'public';
const SUBJECT_USER = 'user';
const SUBJECT_COMPANY = 'company';

const ROLE_VIEWER = 'viewer';
const ROLE_EDITOR = 'editor';
const ROLE_ADMIN = 'admin';

const ROLES = [ROLE_VIEWER, ROLE_EDITOR, ROLE_ADMIN];

function _toIsoOrNull(dateStr) {
    if (typeof dateStr !== 'string' || dateStr.length === 0) return null;
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return null;
    return d.toISOString();
}

export class CRMShareModal extends PlatformModal {
    static modalKind = 'crm.share';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        _subject: { state: true },
        _role: { state: true },
        _expiresAt: { state: true },
        _userQuery: { state: true },
        _selectedUser: { state: true },
        _companyId: { state: true },
        _submitFailedMessage: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .body {
                display: grid;
                gap: var(--space-5);
                padding: var(--space-2) 0;
            }
            .entity-head {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .entity-head .icon {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-md);
            }
            .entity-head .meta { display: grid; gap: 2px; min-width: 0; }
            .entity-head .name {
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .entity-head .sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                padding-top: var(--space-2);
                border-top: 1px solid var(--crm-stroke);
            }

            .grants-list {
                display: grid;
                gap: var(--space-2);
            }
            .grant-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .grant-icon {
                width: 32px;
                height: 32px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--crm-surface);
                color: var(--accent);
            }
            .grant-content { flex: 1; min-width: 0; display: grid; gap: 2px; }
            .grant-target {
                font-size: var(--text-sm);
                font-weight: 500;
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
                padding: 2px var(--space-2);
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .revoke-btn {
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .revoke-btn:hover {
                background: rgba(220, 38, 38, 0.1);
                border-color: var(--color-danger);
                color: var(--color-danger);
            }
            .revoke-btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .empty-block {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                border: 1px dashed var(--crm-stroke);
                border-radius: var(--radius-md);
            }

            .form-grid {
                display: grid;
                gap: var(--space-3);
            }
            .field-label {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .subject-chips {
                display: flex;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .subject-chip {
                flex: 1 1 140px;
                display: grid;
                gap: 2px;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                cursor: pointer;
                color: var(--text-primary);
            }
            .subject-chip.picked {
                border-color: var(--accent);
                background: var(--crm-selected-bg);
                box-shadow: 0 0 0 1px var(--accent) inset;
            }
            .subject-chip .chip-title {
                font-size: var(--text-sm);
                font-weight: 600;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
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
                flex: 1;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
                cursor: pointer;
                font-size: var(--text-sm);
                text-align: center;
            }
            .role-chip.picked {
                border-color: var(--accent);
                background: var(--crm-selected-bg);
                color: var(--accent);
                font-weight: 600;
            }

            .text-input,
            .date-input {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-size: var(--text-sm);
                box-sizing: border-box;
            }

            .typeahead {
                position: relative;
                display: grid;
                gap: var(--space-1);
            }
            .typeahead .selected {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: 4px var(--space-2);
                background: var(--crm-selected-bg);
                border: 1px solid var(--accent);
                border-radius: var(--radius-full);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: fit-content;
            }
            .typeahead .selected .clear-btn {
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
                display: inline-flex;
                align-items: center;
            }
            .typeahead .results {
                display: grid;
                gap: 2px;
                max-height: 220px;
                overflow-y: auto;
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
                background: var(--crm-surface);
            }
            .typeahead .results .result-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                border: none;
                background: transparent;
                color: var(--text-primary);
                text-align: left;
                width: 100%;
                font-size: var(--text-sm);
            }
            .typeahead .results .result-row:hover {
                background: var(--crm-selected-bg);
            }
            .typeahead .results .result-row .email {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-left: auto;
            }
            .typeahead .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .footer-actions .submit-error {
                margin-right: auto;
                color: var(--color-danger);
                font-size: var(--text-sm);
                align-self: center;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid transparent;
            }
            .btn-secondary {
                background: var(--crm-surface);
                border-color: var(--crm-stroke);
                color: var(--text-secondary);
            }
            .btn-secondary:hover {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--accent);
                border-color: var(--accent);
                color: white;
            }
            .btn-primary:hover:not(:disabled) {
                filter: brightness(1.05);
            }
            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.headerSavePrimary = false;
        this.entityId = '';

        this._subject = SUBJECT_USER;
        this._role = ROLE_VIEWER;
        this._expiresAt = '';
        this._userQuery = '';
        this._selectedUser = null;
        this._companyId = '';
        this._submitFailedMessage = '';

        this._entities = this.useResource(ENTITIES_NAME);
        this._grantsListOp = this.useOp(GRANTS_LIST_OP);
        this._grantCreateOp = this.useOp(GRANT_CREATE_OP);
        this._grantRevokeOp = this.useOp(GRANT_REVOKE_OP);
        this._teamSearch = this.useFacets(TEAM_SEARCH_FACETS);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.entityId !== 'string' || this.entityId.length === 0) {
            throw new Error('CRMShareModal: prop "entityId" required');
        }

        this.useEvent(this._grantCreateOp.op.events.SUCCEEDED, () => {
            this._resetForm();
            this._reloadGrants();
        });
        this.useEvent(this._grantCreateOp.op.events.FAILED, (event) => {
            const message = event && event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : this.t('share_modal.submit_failed');
            this._submitFailedMessage = message;
        });
        this.useEvent(this._grantRevokeOp.op.events.SUCCEEDED, () => this._reloadGrants());

        this._entities.get(this.entityId);
        this._reloadGrants();
    }

    _reloadGrants() {
        this._grantsListOp.run({ entity_id: this.entityId });
    }

    _resetForm() {
        this._subject = SUBJECT_USER;
        this._role = ROLE_VIEWER;
        this._expiresAt = '';
        this._userQuery = '';
        this._selectedUser = null;
        this._companyId = '';
        this._submitFailedMessage = '';
    }

    _entity() {
        const item = this._entities.byId[this.entityId];
        return item === undefined ? null : item;
    }

    _grants() {
        const result = this._grantsListOp.lastResult;
        if (!result || !Array.isArray(result.items)) return [];
        return result.items;
    }

    _hasPublicGrant() {
        return this._grants().some((g) => g.grant_type === SUBJECT_PUBLIC);
    }

    _onPickSubject(subject) {
        this._subject = subject;
        this._submitFailedMessage = '';
    }

    _onPickRole(role) {
        this._role = role;
    }

    _onExpiresAtInput(e) {
        this._expiresAt = e.target.value;
    }

    _onUserQueryInput(e) {
        const value = e.target.value;
        this._userQuery = value;
        this._teamSearch.search('users', value);
    }

    _onUserPick(user) {
        this._selectedUser = {
            user_id: user.user_id,
            label: user.email ? `${user.name} <${user.email}>` : user.name,
        };
        this._userQuery = '';
    }

    _onUserClear() {
        this._selectedUser = null;
    }

    _onCompanyIdInput(e) {
        this._companyId = e.target.value;
    }

    _validateBeforeSubmit() {
        if (this._subject === SUBJECT_USER) {
            if (!this._selectedUser || typeof this._selectedUser.user_id !== 'string' || this._selectedUser.user_id.length === 0) {
                return this.t('share_modal.err_pick_user');
            }
        }
        if (this._subject === SUBJECT_COMPANY) {
            if (typeof this._companyId !== 'string' || this._companyId.trim().length === 0) {
                return this.t('share_modal.err_company_id_required');
            }
        }
        if (this._subject === SUBJECT_PUBLIC && this._hasPublicGrant()) {
            return this.t('share_modal.err_public_exists');
        }
        return null;
    }

    _onSubmit() {
        const error = this._validateBeforeSubmit();
        if (typeof error === 'string') {
            this._submitFailedMessage = error;
            return;
        }
        this._submitFailedMessage = '';

        const expiresAtIso = _toIsoOrNull(this._expiresAt);

        if (this._subject === SUBJECT_PUBLIC) {
            this._grantCreateOp.run({
                entity_id: this.entityId,
                subject: SUBJECT_PUBLIC,
            });
            return;
        }
        if (this._subject === SUBJECT_USER) {
            const body = { user_id: this._selectedUser.user_id, role: this._role };
            if (expiresAtIso !== null) body.expires_at = expiresAtIso;
            this._grantCreateOp.run({
                entity_id: this.entityId,
                subject: SUBJECT_USER,
                body,
            });
            return;
        }
        const body = { company_id: this._companyId.trim(), role: this._role };
        if (expiresAtIso !== null) body.expires_at = expiresAtIso;
        this._grantCreateOp.run({
            entity_id: this.entityId,
            subject: SUBJECT_COMPANY,
            body,
        });
    }

    _onRevoke(grantId) {
        this._grantRevokeOp.run({ grant_id: grantId });
    }

    renderHeader() {
        return this.t('share_modal.header');
    }

    renderBody() {
        const entity = this._entity();
        const grants = this._grants();
        const grantsLoading = this._grantsListOp.busy && grants.length === 0;

        return html`
            <div class="body">
                ${this._renderEntityHead(entity)}
                ${this._renderGrantsSection(grants, grantsLoading)}
                ${this._renderForm()}
            </div>
        `;
    }

    _renderEntityHead(entity) {
        if (entity === null) {
            return html`
                <div class="entity-head">
                    <div class="icon">
                        <platform-icon name="link" size="18"></platform-icon>
                    </div>
                    <div class="meta">
                        <div class="name">${this.entityId}</div>
                        <div class="sub">${this.t('share_modal.loading_entity')}</div>
                    </div>
                </div>
            `;
        }
        return html`
            <div class="entity-head">
                <div class="icon">
                    <platform-icon name="link" size="18"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${entity.name}</div>
                    <div class="sub">
                        ${entity.namespace} · ${entity.entity_type}
                    </div>
                </div>
            </div>
        `;
    }

    _renderGrantsSection(grants, loading) {
        return html`
            <div class="section-title">${this.t('share_modal.current_grants')}</div>
            ${loading
                ? html`<div class="empty-block"><glass-spinner></glass-spinner></div>`
                : grants.length === 0
                    ? html`<div class="empty-block">${this.t('share_modal.empty_grants')}</div>`
                    : html`
                        <div class="grants-list">
                            ${grants.map((g) => this._renderGrantItem(g))}
                        </div>
                    `}
        `;
    }

    _renderGrantItem(grant) {
        const target = this._formatGrantTarget(grant);
        const expires = grant.expires_at
            ? this.t('share_modal.expires_on', { date: new Date(grant.expires_at).toLocaleDateString() })
            : this.t('share_modal.expires_never');
        return html`
            <div class="grant-item">
                <div class="grant-icon">
                    <platform-icon name=${this._iconForSubject(grant.grant_type)} size="16"></platform-icon>
                </div>
                <div class="grant-content">
                    <div class="grant-target">${target}</div>
                    <div class="grant-meta">${expires}</div>
                </div>
                <span class="grant-role">${this.t(`share_modal.role_${grant.role}`)}</span>
                <button
                    type="button"
                    class="revoke-btn"
                    ?disabled=${this._grantRevokeOp.busy}
                    @click=${() => this._onRevoke(grant.grant_id)}
                >
                    ${this.t('share_modal.revoke')}
                </button>
            </div>
        `;
    }

    _formatGrantTarget(grant) {
        if (grant.grant_type === SUBJECT_PUBLIC) return this.t('share_modal.target_public');
        if (grant.grant_type === SUBJECT_USER) return grant.target_user_id || this.t('share_modal.target_user_unknown');
        if (grant.grant_type === SUBJECT_COMPANY) return grant.target_company_id || this.t('share_modal.target_company_unknown');
        return grant.grant_type;
    }

    _iconForSubject(subject) {
        if (subject === SUBJECT_PUBLIC) return 'globe';
        if (subject === SUBJECT_USER) return 'user';
        if (subject === SUBJECT_COMPANY) return 'building';
        return 'lock';
    }

    _renderForm() {
        return html`
            <div class="section-title">${this.t('share_modal.add_grant')}</div>
            <div class="form-grid">
                <div>
                    <div class="field-label">${this.t('share_modal.subject_label')}</div>
                    <div class="subject-chips">
                        ${this._renderSubjectChip(SUBJECT_PUBLIC, 'globe', this._hasPublicGrant())}
                        ${this._renderSubjectChip(SUBJECT_USER, 'user', false)}
                        ${this._renderSubjectChip(SUBJECT_COMPANY, 'building', false)}
                    </div>
                </div>
                ${this._subject === SUBJECT_USER ? this._renderUserPicker() : nothing}
                ${this._subject === SUBJECT_COMPANY ? this._renderCompanyInput() : nothing}
                ${this._subject === SUBJECT_PUBLIC ? nothing : this._renderRolePicker()}
                ${this._subject === SUBJECT_PUBLIC ? nothing : this._renderExpiresInput()}
            </div>
        `;
    }

    _renderSubjectChip(subject, icon, disabled) {
        const picked = this._subject === subject;
        return html`
            <button
                type="button"
                class="subject-chip ${picked ? 'picked' : ''}"
                ?disabled=${disabled && !picked}
                @click=${() => this._onPickSubject(subject)}
            >
                <span class="chip-title">
                    <platform-icon name=${icon} size="14"></platform-icon>
                    ${this.t(`share_modal.subject_${subject}`)}
                </span>
                <span class="chip-desc">${this.t(`share_modal.subject_${subject}_desc`)}</span>
            </button>
        `;
    }

    _renderRolePicker() {
        return html`
            <div>
                <div class="field-label">${this.t('share_modal.role_label')}</div>
                <div class="role-chips">
                    ${ROLES.map((role) => html`
                        <button
                            type="button"
                            class="role-chip ${this._role === role ? 'picked' : ''}"
                            @click=${() => this._onPickRole(role)}
                        >${this.t(`share_modal.role_${role}`)}</button>
                    `)}
                </div>
            </div>
        `;
    }

    _renderUserPicker() {
        const items = this._teamSearch.items('users');
        const loading = this._teamSearch.loading('users');
        return html`
            <div>
                <div class="field-label">${this.t('share_modal.user_label')}</div>
                <div class="typeahead">
                    ${this._selectedUser !== null
                        ? html`
                            <span class="selected">
                                <platform-icon name="user" size="12"></platform-icon>
                                ${this._selectedUser.label}
                                <button
                                    type="button"
                                    class="clear-btn"
                                    title=${this.t('share_modal.user_clear')}
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
                                placeholder=${this.t('share_modal.user_placeholder')}
                                .value=${this._userQuery}
                                @input=${this._onUserQueryInput}
                            />
                            ${this._userQuery.length >= 2
                                ? html`
                                    <div class="results">
                                        ${loading
                                            ? html`<div class="hint" style="padding: var(--space-2);">${this.t('share_modal.user_searching')}</div>`
                                            : items.length === 0
                                                ? html`<div class="hint" style="padding: var(--space-2);">${this.t('share_modal.user_no_results')}</div>`
                                                : items.map((u) => html`
                                                    <button type="button" class="result-row" @click=${() => this._onUserPick(u)}>
                                                        <platform-icon name="user" size="14"></platform-icon>
                                                        <span>${u.name}</span>
                                                        ${u.email ? html`<span class="email">${u.email}</span>` : nothing}
                                                    </button>
                                                `)}
                                    </div>
                                `
                                : html`<div class="hint">${this.t('share_modal.user_min_query')}</div>`}
                        `}
                </div>
            </div>
        `;
    }

    _renderCompanyInput() {
        return html`
            <div>
                <div class="field-label">${this.t('share_modal.company_id_label')}</div>
                <input
                    type="text"
                    class="text-input"
                    placeholder=${this.t('share_modal.company_id_placeholder')}
                    .value=${this._companyId}
                    @input=${this._onCompanyIdInput}
                />
            </div>
        `;
    }

    _renderExpiresInput() {
        return html`
            <div>
                <div class="field-label">${this.t('share_modal.expires_label')}</div>
                <input
                    type="date"
                    class="date-input"
                    .value=${this._expiresAt}
                    @change=${this._onExpiresAtInput}
                />
            </div>
        `;
    }

    renderFooter() {
        const busy = this._grantCreateOp.busy;
        return html`
            <div class="footer-actions">
                ${this._submitFailedMessage.length > 0
                    ? html`<span class="submit-error">${this._submitFailedMessage}</span>`
                    : nothing}
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('share_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${busy}
                    @click=${() => this._onSubmit()}
                >
                    ${busy ? this.t('share_modal.submitting') : this.t('share_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-share-modal', CRMShareModal);
registerModalKind(CRMShareModal.modalKind, 'crm-share-modal');
