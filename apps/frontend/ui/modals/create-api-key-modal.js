/**
 * Create API key modal — открывается через `this.openModal(FrontendCreateApiKeyModal)`.
 *
 * Скоупы соответствуют backend whitelist VALID_SCOPES в apps/frontend/api/api_keys.py.
 * После create() модалка закрывается; секрет показывается на странице
 * (state.frontend.apiKeys.lastSecret) — это инвариант: поток данных идёт
 * через стейт, а не через локальные переменные модалки.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

const SCOPE_DEFS = Object.freeze([
    { id: 'agents:read',  name_key: 'api_key_modal.scope_agents_read_name',  desc_key: 'api_key_modal.scope_agents_read_desc' },
    { id: 'agents:write', name_key: 'api_key_modal.scope_agents_write_name', desc_key: 'api_key_modal.scope_agents_write_desc' },
    { id: 'crm:read',     name_key: 'api_key_modal.scope_crm_read_name',     desc_key: 'api_key_modal.scope_crm_read_desc' },
    { id: 'crm:write',    name_key: 'api_key_modal.scope_crm_write_name',    desc_key: 'api_key_modal.scope_crm_write_desc' },
    { id: 'rag:read',     name_key: 'api_key_modal.scope_rag_read_name',     desc_key: 'api_key_modal.scope_rag_read_desc' },
    { id: 'rag:write',    name_key: 'api_key_modal.scope_rag_write_name',    desc_key: 'api_key_modal.scope_rag_write_desc' },
    { id: 'billing:read', name_key: 'api_key_modal.scope_billing_read_name', desc_key: 'api_key_modal.scope_billing_read_desc' },
]);

export class FrontendCreateApiKeyModal extends PlatformFormModal {
    static modalKind = 'frontend.api_key_create';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .scopes-list { display: flex; flex-direction: column; gap: var(--space-2); }
            .scope-row {
                display: flex; align-items: flex-start; gap: var(--space-3);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
            }
            .scope-row:hover { border-color: var(--accent); }
            .scope-row.checked { border-color: var(--accent); background: var(--glass-solid-medium); }
            .scope-row input { margin-top: 4px; }
            .scope-text { display: flex; flex-direction: column; gap: 2px; }
            .scope-name { color: var(--text-primary); font-weight: var(--font-medium); font-size: var(--text-sm); }
            .scope-desc { color: var(--text-secondary); font-size: var(--text-xs); }
        `,
    ];

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
        _scopes: { state: true },
    };

    constructor() {
        super();
        this._name = '';
        this._scopes = new Set();
        this.size = 'md';
        this._keys = this.useResource('frontend/api_keys');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('api_key_modal.header_create');
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('api_key_modal.err_name');
        if (this._scopes.size === 0) errors.scopes = this.t('api_key_modal.err_scopes');
        return errors;
    }

    async handleSubmit() {
        this._keys.create({
            name: this._name.trim(),
            scopes: Array.from(this._scopes),
        });
        this.closeAfterSave();
    }

    _toggleScope(scopeId) {
        const next = new Set(this._scopes);
        if (next.has(scopeId)) next.delete(scopeId); else next.add(scopeId);
        this._scopes = next;
        this.isDirty = true;
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit}>
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('api_key_modal.label_name')}
                        placeholder=${this.t('api_key_modal.placeholder_name')}
                        .value=${this._name}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('api-key-create: name expects detail.value string');
                            }
                            this._name = e.detail.value;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    ${this.renderFieldError('name')}
                </div>
                <div class="form-group">
                    <label class="form-label">${this.t('api_key_modal.label_scopes')}</label>
                    <div class="scopes-list">
                        ${SCOPE_DEFS.map((s) => {
                            const checked = this._scopes.has(s.id);
                            return html`
                                <label class="scope-row ${checked ? 'checked' : ''}">
                                    <input
                                        type="checkbox"
                                        .checked=${checked}
                                        @change=${() => this._toggleScope(s.id)}
                                    />
                                    <span class="scope-text">
                                        <span class="scope-name">${this.t(s.name_key)}</span>
                                        <span class="scope-desc">${this.t(s.desc_key)}</span>
                                    </span>
                                </label>
                            `;
                        })}
                    </div>
                    ${this.renderFieldError('scopes')}
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit = this._name.trim().length > 0 && this._scopes.size > 0 && !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('api_key_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading ? this.t('api_key_modal.creating') : this.t('api_key_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-create-api-key-modal', FrontendCreateApiKeyModal);
registerModalKind(FrontendCreateApiKeyModal.modalKind, 'frontend-create-api-key-modal');
