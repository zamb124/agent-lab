/**
 * Share Modal - Модальное окно для шаринга сущности
 * Использует PlatformModal с fullscreen и drag поддержкой.
 * При shareType='user' предоставляет autocomplete по участникам команды
 * и поиск по email/имени по всей платформе.
 */
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-date-picker.js';

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

export class ShareModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        namespaceId: { type: String },
        shareType: { type: String },
        _targetId: { state: true },
        _role: { state: true },
        _expiresAt: { state: true },
        _saving: { state: true },
        _query: { state: true },
        _suggestions: { state: true },
        _searching: { state: true },
        _selectedUser: { state: true },
        _showDropdown: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }

            .role-chips {
                display: flex;
                gap: var(--space-2);
            }

            .role-chip {
                flex: 1;
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .role-chip:hover {
                background: var(--crm-surface);
                color: var(--text-primary);
            }

            .role-chip.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .role-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }

            .role-title {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
            }

            .user-search-wrapper {
                position: relative;
            }

            .user-dropdown {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                z-index: 10;
                max-height: 240px;
                overflow-y: auto;
                background: var(--crm-surface);
                border: 1px solid var(--crm-stroke);
                border-top: none;
                border-radius: 0 0 var(--radius-lg) var(--radius-lg);
                box-shadow: var(--shadow-md);
            }

            .user-option {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                transition: background var(--duration-fast);
            }

            .user-option:hover {
                background: var(--crm-selected-bg);
            }

            .user-option-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                background: var(--crm-surface-muted);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                flex-shrink: 0;
                overflow: hidden;
            }

            .user-option-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .user-option-info {
                flex: 1;
                min-width: 0;
            }

            .user-option-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-option-email {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .user-dropdown-status {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-align: center;
            }

            .selected-user-chip {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .selected-user-chip .remove-btn {
                cursor: pointer;
                color: var(--text-tertiary);
                display: flex;
                align-items: center;
                margin-left: auto;
                background: none;
                border: none;
                padding: 0;
            }

            .selected-user-chip .remove-btn:hover {
                color: var(--text-primary);
            }
        `
    ];

    constructor() {
        super();
        this.size = 'md';
        this.entityId = null;
        this.namespaceId = null;
        this.shareType = 'user';
        this._targetId = '';
        this._role = 'viewer';
        this._expiresAt = '';
        this._saving = false;
        this._query = '';
        this._suggestions = [];
        this._searching = false;
        this._selectedUser = null;
        this._showDropdown = false;
        this._searchTimer = null;
        this._teamMembers = [];
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.shareType === 'user') {
            this._loadTeamMembers();
        }
    }

    async _loadTeamMembers() {
        const team = this.services.get('team');
        this._teamMembers = await team.getMembers();
    }

    _onRoleSelect(role) {
        this._role = role;
    }

    _onExpiresAtChange(e) {
        this._expiresAt = e.target.value;
    }

    _onTargetIdInput(e) {
        this._targetId = e.target.value;
    }

    _onUserQueryInput(e) {
        const query = e.target.value;
        this._query = query;
        this._selectedUser = null;
        this._targetId = query.trim();

        if (this._searchTimer) clearTimeout(this._searchTimer);

        if (query.length < MIN_QUERY_LENGTH) {
            this._suggestions = [];
            this._showDropdown = false;
            return;
        }

        this._showDropdown = true;
        this._filterLocal(query);

        this._searchTimer = setTimeout(() => this._searchRemote(query), SEARCH_DEBOUNCE_MS);
    }

    _filterLocal(query) {
        const q = query.toLowerCase();
        const localMatches = this._teamMembers.filter(m =>
            m.name?.toLowerCase().includes(q) ||
            m.email?.toLowerCase().includes(q)
        );
        this._suggestions = localMatches;
    }

    async _searchRemote(query) {
        this._searching = true;
        try {
            const team = this.services.get('team');
            const results = await team.searchUsers(query);
            const existingIds = new Set(this._suggestions.map(s => s.user_id));
            const merged = [...this._suggestions];
            for (const r of results) {
                if (!existingIds.has(r.user_id)) {
                    merged.push(r);
                }
            }
            this._suggestions = merged;
        } finally {
            this._searching = false;
        }
    }

    _selectUser(user) {
        this._selectedUser = user;
        this._targetId = user.user_id;
        this._query = '';
        this._showDropdown = false;
        this._suggestions = [];
    }

    _clearSelectedUser() {
        this._selectedUser = null;
        this._targetId = '';
        this._query = '';
    }

    _onInputBlur() {
        setTimeout(() => { this._showDropdown = false; }, 200);
    }

    _onInputFocus() {
        if (this._query.length >= MIN_QUERY_LENGTH && this._suggestions.length > 0) {
            this._showDropdown = true;
        }
    }

    async _resolveUserId(input) {
        if (this._selectedUser) return this._selectedUser.user_id;

        if (input.includes('@')) {
            const team = this.services.get('team');
            const results = await team.searchUsers(input);
            const exact = results.find(u => u.email === input);
            if (exact) return exact.user_id;
            if (results.length > 0) return results[0].user_id;
            return null;
        }

        return input;
    }

    async _onShare() {
        if (!this._targetId.trim()) {
            this.error(this.shareType === 'user'
                ? this.i18n.t('share_modal.err_enter_user_id')
                : this.i18n.t('share_modal.err_enter_company_id')
            );
            return;
        }

        this._saving = true;
        try {
            const crmApi = this.services.get('crmApi');
            let target = this._targetId.trim();

            if (this.shareType === 'user') {
                const resolvedId = await this._resolveUserId(target);
                if (!resolvedId) {
                    this.error(this.i18n.t('share_modal.err_user_not_found'));
                    return;
                }
                target = resolvedId;
            }

            if (this.namespaceId) {
                if (this.shareType === 'user') {
                    await CRMStore.grantNamespaceToUser(crmApi, this.namespaceId, target, this._role);
                } else {
                    await CRMStore.grantNamespaceToCompany(crmApi, this.namespaceId, target, this._role);
                }
            } else {
                if (this.shareType === 'user') {
                    await CRMStore.grantToUser(crmApi, this.entityId, target, this._role);
                } else {
                    await CRMStore.grantToCompany(crmApi, this.entityId, target, this._role);
                }
            }

            this.success(this.shareType === 'user'
                ? this.i18n.t('share_modal.success_user')
                : this.i18n.t('share_modal.success_company')
            );
            this.dispatchEvent(new CustomEvent('shared'));
            this.close();
        } catch (error) {
            const message = error instanceof Error
                ? error.message
                : this.i18n.t('share_modal.err_share');
            this.error(message);
            throw error;
        } finally {
            this._saving = false;
        }
    }

    renderHeader() {
        return this.shareType === 'user'
            ? this.i18n.t('grants.share_user')
            : this.i18n.t('grants.share_company');
    }

    _renderUserInput() {
        if (this._selectedUser) {
            return html`
                <div class="selected-user-chip">
                    <span>${this._selectedUser.name}</span>
                    ${this._selectedUser.email
                        ? html`<span class="user-option-email">${this._selectedUser.email}</span>`
                        : nothing}
                    <button type="button" class="remove-btn" @click=${this._clearSelectedUser}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            `;
        }

        return html`
            <div class="user-search-wrapper">
                <input
                    type="text"
                    class="form-input"
                    placeholder="${this.i18n.t('share_modal.placeholder_user_id')}"
                    .value=${this._query}
                    @input=${this._onUserQueryInput}
                    @blur=${this._onInputBlur}
                    @focus=${this._onInputFocus}
                />
                ${this._showDropdown ? this._renderDropdown() : nothing}
            </div>
        `;
    }

    _renderDropdown() {
        if (this._suggestions.length === 0 && !this._searching) {
            if (this._query.length >= MIN_QUERY_LENGTH) {
                return html`
                    <div class="user-dropdown">
                        <div class="user-dropdown-status">
                            ${this.i18n.t('share_modal.no_results')}
                        </div>
                    </div>
                `;
            }
            return nothing;
        }

        return html`
            <div class="user-dropdown">
                ${this._suggestions.map(user => html`
                    <div class="user-option" @mousedown=${() => this._selectUser(user)}>
                        <div class="user-option-avatar">
                            ${user.avatar_url
                                ? html`<img src="${user.avatar_url}" alt="" />`
                                : html`${(user.name || '?')[0].toUpperCase()}`}
                        </div>
                        <div class="user-option-info">
                            <div class="user-option-name">${user.name}</div>
                            ${user.email
                                ? html`<div class="user-option-email">${user.email}</div>`
                                : nothing}
                        </div>
                    </div>
                `)}
                ${this._searching ? html`
                    <div class="user-dropdown-status">
                        ${this.i18n.t('share_modal.searching')}
                    </div>
                ` : nothing}
            </div>
        `;
    }

    renderBody() {
        const isUser = this.shareType === 'user';
        const targetLabel = isUser
            ? this.i18n.t('share_modal.label_user_id')
            : this.i18n.t('share_modal.label_company_id');

        return html`
            <div class="form-grid">
                <div class="form-group">
                    <label class="form-label">${targetLabel}</label>
                    ${isUser
                        ? this._renderUserInput()
                        : html`
                            <input
                                type="text"
                                class="form-input"
                                placeholder="${this.i18n.t('share_modal.placeholder_company_id')}"
                                .value=${this._targetId}
                                @input=${this._onTargetIdInput}
                            />
                        `}
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('share_modal.label_access_level')}</label>
                    <div class="role-chips">
                        <button
                            type="button"
                            class="role-chip ${this._role === 'viewer' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('viewer')}
                        >
                            <div class="role-title">
                                <platform-icon name="eye" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_viewer')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_viewer_desc')}</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'editor' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('editor')}
                        >
                            <div class="role-title">
                                <platform-icon name="edit" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_editor')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_editor_desc')}</div>
                        </button>
                        <button
                            type="button"
                            class="role-chip ${this._role === 'admin' ? 'active' : ''}"
                            @click=${() => this._onRoleSelect('admin')}
                        >
                            <div class="role-title">
                                <platform-icon name="settings" size="14"></platform-icon>
                                <span>${this.i18n.t('grants.role_admin')}</span>
                            </div>
                            <div class="role-description">${this.i18n.t('share_modal.role_admin_desc')}</div>
                        </button>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('share_modal.label_expires_optional')}</label>
                    <platform-date-picker
                        class="form-input"
                        mode="date"
                        value-format="iso"
                        .value=${this._expiresAt || null}
                        @change=${this._onExpiresAtChange}
                    ></platform-date-picker>
                </div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title = this._saving
            ? this.i18n.t('share_modal.saving')
            : this.i18n.t('share_modal.submit_grant');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onShare(),
            disabled: this._saving || !this._targetId.trim(),
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.i18n.t('cancel', {}, 'common')}
                </button>
            </div>
        `;
    }
}

customElements.define('share-modal', ShareModal);
