/**
 * flows-flow-edit-modal — редактирование метаданных flow (name, description).
 *
 * Источник — useResource('flows/flows'). Update идёт через ResourceCollection.update,
 * REST handler — `PUT /flows/api/v1/flows/{flow_id}` ([flows.py](apps/flows/src/api/v1/flows.py)).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import { asArray } from '../_helpers/flows-resolvers.js';

export class FlowsFlowEditModal extends PlatformFormModal {
    static modalKind = 'flows.flow_edit';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        _name: { state: true },
        _description: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field input, .field textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .field textarea { min-height: 96px; resize: vertical; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .flow-id { font-family: var(--font-mono); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._name = '';
        this._description = '';
        this._hydrated = false;
        this._flows = this.useResource('flows/flows');
        this._update = this.useOp('flows/flow_update');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.flowId) {
            const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
            if (item) {
                this._name = typeof item.name === 'string' ? item.name : '';
                this._description = typeof item.description === 'string' ? item.description : '';
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
        return html`
            <div class="field">
                <label>${this.t('flow_edit_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.isDirty = true; }} />
            </div>
            <div class="field">
                <label>${this.t('flow_edit_modal.field_description')}</label>
                <textarea .value=${this._description} @input=${(e) => { this._description = e.target.value; this.isDirty = true; }}></textarea>
            </div>
        `;
    }

    renderFooter() {
        const valid = this._name.trim().length > 0;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('flow_edit_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._onSubmit}>
                ${this.t('flow_edit_modal.action_save')}
            </platform-button>
        `;
    }

    _onSubmit() {
        if (!this.flowId) return;
        const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        if (!item) return;
        const body = {
            ...item,
            name: this._name.trim(),
            description: this._description,
        };
        this._update.run({ flow_id: this.flowId, body });
        this.closeAfterSave();
    }
}

customElements.define('flows-flow-edit-modal', FlowsFlowEditModal);
registerModalKind(FlowsFlowEditModal.modalKind, 'flows-flow-edit-modal');
