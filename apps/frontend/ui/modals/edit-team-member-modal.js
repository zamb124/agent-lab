/**
 * Модальное окно редактирования ролей участника команды
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/glass-modal.js';

const ALL_ROLES = ['owner', 'admin', 'developer', 'viewer'];

const ROLE_LABELS = {
    owner: 'Владелец',
    admin: 'Администратор',
    developer: 'Разработчик',
    viewer: 'Наблюдатель',
};

export class EditTeamMemberModal extends PlatformElement {
    static styles = [
        PlatformElement.styles,
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
        this._open = false;
        this._member = null;
        this._selectedRoles = [];
        this._ownerUserId = null;
        this._loadingSettings = false;
        this._saving = false;
    }

    /**
     * @param {{ user_id: string, name: string, roles: string[] }} member
     */
    async show(member) {
        this._member = member;
        this._selectedRoles = [...member.roles];
        this._ownerUserId = null;
        this._open = true;
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

    _toggleRole(role) {
        if (this._loadingSettings || this._saving || !this._member) {
            return;
        }
        const isCompanyOwner = this._ownerUserId && this._member.user_id === this._ownerUserId;
        if (isCompanyOwner && role === 'owner') {
            return;
        }

        const has = this._selectedRoles.includes(role);
        if (has) {
            if (this._selectedRoles.length <= 1) {
                this.error('Нужна хотя бы одна роль');
                return;
            }
            this._selectedRoles = this._selectedRoles.filter((r) => r !== role);
        } else {
            this._selectedRoles = [...this._selectedRoles, role];
        }
        this.requestUpdate();
    }

    async _handleSave() {
        const roles = this._orderedRoles();
        if (roles.length === 0) {
            this.error('Нужна хотя бы одна роль');
            return;
        }

        this._saving = true;
        this.requestUpdate();

        try {
            await this.services.get('team').updateMemberRole(this._member.user_id, roles);
            this.success('Роли обновлены');
            this.dispatchEvent(new CustomEvent('saved', { bubbles: true, composed: true }));
            this._handleClose();
        } catch (e) {
            this.error(e instanceof Error ? e.message : String(e));
        } finally {
            this._saving = false;
            this.requestUpdate();
        }
    }

    _handleClose() {
        this._open = false;
        this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
    }

    render() {
        const name = this._member?.name ?? '';
        const isCompanyOwner =
            this._ownerUserId && this._member && this._member.user_id === this._ownerUserId;

        return html`
            <glass-modal ?open=${this._open} @close=${this._handleClose} size="md">
                <span slot="title">Участник: ${name}</span>
                <div slot="content">
                    ${this._loadingSettings
                        ? html`<div class="loading-inline">Загрузка...</div>`
                        : this._renderRoles(isCompanyOwner)}
                </div>
                <div slot="actions">
                    ${this._loadingSettings
                        ? ''
                        : html`
                              <div class="actions-row">
                                  <button
                                      class="btn btn-secondary"
                                      @click=${this._handleClose}
                                      ?disabled=${this._saving}
                                  >
                                      Отмена
                                  </button>
                                  <button
                                      class="btn btn-primary"
                                      @click=${this._handleSave}
                                      ?disabled=${this._saving}
                                  >
                                      ${this._saving ? 'Сохранение...' : 'Сохранить'}
                                  </button>
                              </div>
                          `}
                </div>
            </glass-modal>
        `;
    }

    _renderRoles(isCompanyOwner) {
        return html`
            ${this._member?.user_id
                ? html`<p class="member-meta">ID: ${this._member.user_id}</p>`
                : ''}
            <div class="form-group">
                <label class="form-label">Роли в компании</label>
                <div class="roles-list">
                    ${ALL_ROLES.map((role) => {
                        const checked = this._selectedRoles.includes(role);
                        const disabled =
                            this._saving ||
                            (isCompanyOwner && role === 'owner' && checked);
                        return html`
                            <div
                                class="form-item ${checked ? 'selected' : ''}"
                                @click=${() => !disabled && this._toggleRole(role)}
                            >
                                <div class="form-checkbox">${checked ? '✓' : ''}</div>
                                <div class="form-item-content">
                                    <div class="form-item-title">${ROLE_LABELS[role]}</div>
                                    ${isCompanyOwner && role === 'owner'
                                        ? html`<div class="owner-hint">
                                              Роль владельца нельзя снять с владельца компании
                                          </div>`
                                        : ''}
                                </div>
                            </div>
                        `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('edit-team-member-modal', EditTeamMemberModal);
