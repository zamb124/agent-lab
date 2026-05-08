/**
 * Edit API key modal — переименование существующего ключа.
 *
 * Принимает `item: { key_id, name }` через props при `openModal(...)`.
 * Submit диспатчит `update(key_id, { name })` в ресурс `frontend/api_keys`,
 * что соответствует `PATCH /frontend/api/api-keys/{key_id}` на бэке.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendEditApiKeyModal extends PlatformFormModal {
    static modalKind = 'frontend.api_key_edit';

    static properties = {
        ...PlatformFormModal.properties,
        item: { type: Object },
        _name: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .key-info {
                margin-bottom: var(--space-4);
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.item = null;
        this._name = '';
        this.size = 'sm';
        this._keys = this.useResource('frontend/api_keys');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('api_key_edit_modal.header');
        if (changed.has('item') && this.item) {
            this._name = this.item.name;
        }
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('api_key_modal.err_name');
        return errors;
    }

    async handleSubmit() {
        if (!this.item) return;
        const next = this._name.trim();
        if (!next || next === this.item.name) {
            this.closeAfterSave();
            return;
        }
        this._keys.update(this.item.key_id, { name: next });
        this.closeAfterSave();
    }

    renderBody() {
        if (!this.item) return html`<p>${this.t('team_modal.loading')}</p>`;
        const prefix = this.item.key_prefix || this.item.key_id;
        return html`
            <div class="key-info">${prefix}</div>
            <div class="form-group">
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('api_key_modal.label_name')}
                    placeholder=${this.t('api_key_modal.placeholder_name')}
                    .value=${this._name}
                    @change=${(e) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('api-key-edit: name expects detail.value string');
                        }
                        this._name = e.detail.value;
                        this.isDirty = true;
                    }}
                ></platform-field>
                ${this.renderFieldError('name')}
            </div>
        `;
    }

    renderFooter() {
        const canSubmit = this._name.trim().length > 0 && !this.loading;
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
                    ${this.loading ? this.t('api_key_edit_modal.saving') : this.t('api_key_edit_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-edit-api-key-modal', FrontendEditApiKeyModal);
registerModalKind(FrontendEditApiKeyModal.modalKind, 'frontend-edit-api-key-modal');
