/**
 * Модальное окно редактирования ролей участника команды
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

const ALL_ROLES = ['owner', 'admin', 'developer', 'viewer'];

export class EditTeamMemberModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .member-meta {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-4) 0;
            }

            .owner-hint {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin-top: var(--space-1);
            }

            .roles-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                position: relative;
                z-index: 2;
                pointer-events: auto;
            }

            label.form-item {
                margin: 0;
            }

            .role-input {
                width: 20px;
                height: 20px;
                flex-shrink: 0;
                margin: 0;
                cursor: pointer;
                accent-color: var(--accent, #10b981);
            }

            .role-input:disabled {
                cursor: not-allowed;
                opacity: 0.6;
            }

            .loading-inline {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-secondary);
            }

            .actions-row {
                display: flex;
                gap: 12px;
            }

            .actions-row .btn {
                flex: 1;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.open = false;
        this._member = null;
        this._selectedRoles = [];
        this._ownerUserId = null;
        this._loadingSettings = false;
        this._saving = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    /**
     * @param {{ user_id: string, name: string, roles: string[] }} member
     */
    async show(member) {
        this._member = member;
        const raw = member.roles;
        if (Array.isArray(raw)) {
            this._selectedRoles = [...raw];
        } else if (typeof raw === 'string') {
            this._selectedRoles = [raw];
        } else {
            this._selectedRoles = [];
        }
        this._ownerUserId = null;
        this.open = true;
        this._loadingSettings = true;
        this.requestUpdate();

        let settings;
        try {
            settings = await this.services.get('settings').getCompanySettings();
        } catch (e) {
            this.error(e instanceof Error ? e.message : String(e));
            this._loadingSettings = false;
            this._handleClose();
            return;
        }

        this._ownerUserId = settings.owner_user_id ?? null;
        if (this._ownerUserId && member.user_id === this._ownerUserId && !this._selectedRoles.includes('owner')) {
            this._selectedRoles = [...this._selectedRoles, 'owner'];
        }
        this._loadingSettings = false;
        this.requestUpdate();
    }

    _orderedRoles() {
        return ALL_ROLES.filter((role) => this._selectedRoles.includes(role));
    }

    _onRoleCheckbox(role, checked) {
        if (this._loadingSettings || this._saving || !this._member) {
            this.requestUpdate();
            return;
        }
        const isCompanyOwner = this._ownerUserId && this._member.user_id === this._ownerUserId;
        if (isCompanyOwner && role === 'owner' && !checked) {
            this.error(this.i18n.t('team_modal.err_owner_role', {}, 'dashboard'));
            this.requestUpdate();
            return;
        }
        if (!checked) {
            if (this._selectedRoles.length <= 1 && this._selectedRoles.includes(role)) {
                this.error(this.i18n.t('team_modal.err_one_role', {}, 'dashboard'));
                this.requestUpdate();
                return;
            }
            this._selectedRoles = this._selectedRoles.filter((r) => r !== role);
        } else if (!this._selectedRoles.includes(role)) {
            this._selectedRoles = [...this._selectedRoles, role];
        }
        this.requestUpdate();
    }

    async _handleSave() {
        const td = (k, p) => this.i18n.t(k, p ?? {}, 'dashboard');
        const roles = this._orderedRoles();
        if (roles.length === 0) {
            this.error(td('team_modal.err_one_role'));
            return;
        }

        this._saving = true;
        this.requestUpdate();

        try {
            await this.services.get('team').updateMemberRole(this._member.user_id, roles);
            this.success(td('team_modal.toast_saved'));
            this.dispatchEvent(new CustomEvent('saved', { bubbles: true, composed: true }));
            this._handleClose();
        } catch (e) {
            this.error(e instanceof Error ? e.message : String(e));
        } finally {
            this._saving = false;
            this.requestUpdate();
        }
    }

    close() {
        this.open = false;
        super.close();
        this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
    }

    _handleClose() {
        this.close();
    }

    renderHeader() {
        const name = this._member?.name ?? '';
        return this.i18n.t('team_modal.header', { name }, 'dashboard');
    }

    renderBody() {
        const td = (k) => this.i18n.t(k, {}, 'dashboard');
        const isCompanyOwner =
            this._ownerUserId && this._member && this._member.user_id === this._ownerUserId;
        return this._loadingSettings
            ? html`<div class="loading-inline">${td('team_modal.loading')}</div>`
            : this._renderRoles(isCompanyOwner);
    }

    renderFooter() {
        const td = (k) => this.i18n.t(k, {}, 'dashboard');
        return this._loadingSettings
            ? html``
            : html`
                <div class="actions-row">
                    <button
                        class="btn btn-secondary"
                        @click=${this._handleClose}
                        ?disabled=${this._saving}
                    >
                        ${td('team_modal.cancel')}
                    </button>
                    <button
                        class="btn btn-primary"
                        @click=${this._handleSave}
                        ?disabled=${this._saving}
                    >
                        ${this._saving ? td('team_modal.saving') : td('team_modal.save')}
                    </button>
                </div>
            `;
    }

    render() {
        if (!this.open) {
            return html``;
        }
        return super.render();
    }

    _renderRoles(isCompanyOwner) {
        const roleTitle = (r) => this.i18n.t(`team_roles.${r}`, {}, 'dashboard');
        const td = (k) => this.i18n.t(k, {}, 'dashboard');
        return html`
            ${this._member?.user_id
                ? html`<p class="member-meta">ID: ${this._member.user_id}</p>`
                : ''}
            <div class="form-group">
                <label class="form-label">${td('team_modal.roles_label')}</label>
                <div class="roles-list">
                    ${ALL_ROLES.map((role) => {
                        const checked = this._selectedRoles.includes(role);
                        const disabled =
                            this._saving ||
                            (isCompanyOwner && role === 'owner' && checked);
                        return html`
                            <label class="form-item ${checked ? 'selected' : ''}">
                                <input
                                    class="role-input"
                                    type="checkbox"
                                    .checked=${checked}
                                    ?disabled=${disabled}
                                    @change=${(e) =>
                                        this._onRoleCheckbox(role, e.target.checked)}
                                />
                                <div class="form-item-content">
                                    <div class="form-item-title">${roleTitle(role)}</div>
                                    ${isCompanyOwner && role === 'owner'
                                        ? html`<div class="owner-hint">
                                              ${td('team_modal.owner_hint')}
                                          </div>`
                                        : ''}
                                </div>
                            </label>
                        `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('edit-team-member-modal', EditTeamMemberModal);
