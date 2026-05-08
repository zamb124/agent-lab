/**
 * flows-flow-edit-modal — редактирование метаданных flow (name, description, обложка).
 *
 * Update — `PUT /flows/api/v1/flows/{flow_id}`. Загрузка файла — `flows/file_upload` (POST `/flows/api/v1/files/`).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import { asArray } from '../_helpers/flows-resolvers.js';

export class FlowsFlowEditModal extends PlatformFormModal {
    static modalKind = 'flows.flow_edit';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        _name: { state: true },
        _description: { state: true },
        _cardImageUrl: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .flow-id { font-family: var(--font-mono); color: var(--text-tertiary); }
            .card-preview {
                max-width: 100%;
                max-height: 160px;
                border-radius: var(--radius-md);
                object-fit: contain;
                margin-top: var(--space-2);
            }
            .card-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); align-items: center; }
            .field-card-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .visually-hidden {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0, 0, 0, 0);
                border: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._name = '';
        this._description = '';
        this._cardImageUrl = '';
        this._hydrated = false;
        this._flows = this.useResource('flows/flows');
        this._update = this.useOp('flows/flow_update');
        this._fileUpload = this.useOp('flows/file_upload');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            this._hydrated = false;
            this._name = '';
            this._description = '';
            this._cardImageUrl = '';
        }
        if (!this._hydrated && this.flowId) {
            const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
            if (item) {
                this._name = typeof item.name === 'string' ? item.name : '';
                this._description = typeof item.description === 'string' ? item.description : '';
                const c = item.store_card_image_url;
                this._cardImageUrl = typeof c === 'string' ? c : '';
                this._hydrated = true;
            } else {
                this._flows.get(this.flowId);
            }
        }
    }

    renderHeader() {
        return html`<h3>${this.t('flow_edit_modal.title')} <span class="flow-id">${this.flowId}</span></h3>`;
    }

    renderBody() {
        const cardUrl = this._cardImageUrl.trim();
        return html`
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('flow_edit_modal.field_name')}
                    .value=${this._name}
                    @change=${(e) => {
                        this._name = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('flow_edit_modal.field_description')}
                    .value=${this._description}
                    @change=${(e) => {
                        this._description = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <span class="field-card-label">${this.t('flow_edit_modal.field_card_image')}</span>
                ${cardUrl.length > 0
        ? html`<img class="card-preview" src=${cardUrl} alt="" />`
        : null}
                <div class="card-actions">
                    <input
                        type="file"
                        class="visually-hidden"
                        accept="image/*"
                        id="flows-flow-edit-card-input"
                        ?disabled=${this._fileUpload.busy}
                        @change=${(e) => { void this._onCardFile(e); }}
                    />
                    <platform-button
                        variant="secondary"
                        ?disabled=${this._fileUpload.busy}
                        @click=${() => {
            const el = this.renderRoot.querySelector('#flows-flow-edit-card-input');
            if (el) el.click();
        }}
                    >${this.t('flow_edit_modal.action_upload_image')}</platform-button>
                    ${cardUrl.length > 0
        ? html`<platform-button
                            variant="secondary"
                            ?disabled=${this._fileUpload.busy}
                            @click=${() => {
            this._cardImageUrl = '';
            this.isDirty = true;
        }}
                        >${this.t('flow_edit_modal.action_clear_image')}</platform-button>`
        : null}
                </div>
            </div>
        `;
    }

    renderFooter() {
        const valid = this._name.trim().length > 0;
        const busy = this._fileUpload.busy;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('flow_edit_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid || busy} @click=${this._onSubmit}>
                ${this.t('flow_edit_modal.action_save')}
            </platform-button>
        `;
    }

    async _onCardFile(e) {
        const input = e.target;
        const files = input.files;
        const file = files && files.length > 0 ? files[0] : null;
        if (!file) {
            return;
        }
        if (typeof file.type !== 'string' || !file.type.startsWith('image/')) {
            this.toast('flow_edit_modal.toast_image_type', { type: 'error' });
            input.value = '';
            return;
        }
        const result = await this._fileUpload.run({ file });
        if (!result || typeof result !== 'object' || typeof result.url !== 'string' || result.url.length === 0) {
            throw new Error('flows-flow-edit-modal: file upload missing result.url');
        }
        this._cardImageUrl = result.url;
        this.isDirty = true;
        input.value = '';
    }

    _onSubmit() {
        if (!this.flowId) return;
        const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        if (!item) return;
        const trimmedCard = this._cardImageUrl.trim();
        const body = {
            ...item,
            name: this._name.trim(),
            description: this._description,
            store_card_image_url: trimmedCard.length > 0 ? trimmedCard : null,
        };
        this._update.run({ flow_id: this.flowId, body });
        this.closeAfterSave();
    }
}

customElements.define('flows-flow-edit-modal', FlowsFlowEditModal);
registerModalKind(FlowsFlowEditModal.modalKind, 'flows-flow-edit-modal');
