/**
 * Модалка редактирования API-ключа — переименование существующего ключа.
 *
 * Принимает `item: { key_id, name }` через props при `openModal(...)`.
 * Отправка диспатчит `update(key_id, { name })` в ресурс `frontend/api_keys`,
 * что соответствует `PATCH /frontend/api/api-keys/{key_id}` на бэке.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-spinner.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { ResourceController } from '@platform/lib/base/use-resource.js';

export class FrontendEditApiKeyModal extends PlatformFormModal {
    static modalKind = 'frontend.api_key_edit';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        item: { type: Object },
        _name: { state: true },
    }
    declare item: Record<string, unknown> | null;
    declare _name: string;
;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
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
    private _keys: ResourceController;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('api_key_edit_modal.header');
        if (changed.has('item') && this.item) {
            const name = this.item.name;
            if (typeof name !== 'string') {
                throw new Error('api key edit: name required');
            }
            this._name = name;
        }
    }

    override validateForm() {
        const errors: Record<string, any> = {};
        if (!this._name.trim()) errors.name = this.t('api_key_modal.err_name');
        return errors;
    }

    override async handleSubmit() {
        if (!this.item) return;
        const next = this._name.trim();
        const currentName = this.item.name;
        if (typeof currentName !== 'string') {
            throw new Error('api key edit: name required');
        }
        if (!next || next === currentName) {
            this.closeAfterSave();
            return;
        }
        const keyId = this.item.key_id;
        if (typeof keyId !== 'string' || keyId.length === 0) {
            throw new Error('api key edit: key_id required');
        }
        this._keys.update(keyId, { name: next });
        this.closeAfterSave();
    }

    override renderBody() {
        if (!this.item) return html`<platform-spinner></platform-spinner>`;
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
                    .error=${this.fieldError('name')}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('api-key-edit: name expects detail.value string');
                        }
                        this._name = e.detail.value;
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    override renderFooter() {
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
