/**
 * flows-branch-create-modal — создание ветки графа для flow.
 *
 * Использует useOp('flows/branch_create'). После успеха страница редактора
 * загружает обновлённый flow через push `flows/branch/created`.
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

const BRANCH_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

export class FlowsBranchCreateModal extends PlatformFormModal {
    static modalKind = 'flows.branch_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        _branchId: { state: true },
        _name: { state: true },
        _description: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .form-error { color: var(--error); font-size: var(--text-xs); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._branchId = '';
        this._name = '';
        this._description = '';
        this._createBranch = this.useOp('flows/branch_create');
        this._flows = this.useResource('flows/flows');
    }

    renderHeader() {
        return html`<h3>${this.t('branch_create_modal.title')}</h3>`;
    }

    renderSaveHeaderButton() {
        return html``;
    }

    renderBody() {
        const validId = BRANCH_ID_PATTERN.test(this._branchId);
        return html`
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('branch_create_modal.field_branch_id')}
                    .placeholder=${'my_branch'}
                    .value=${this._branchId}
                    @change=${(e) => {
                        this._branchId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
                ${this._branchId.length > 0 && !validId
                    ? html`<div class="form-error">${this.t('branch_create_modal.err_branch_id_pattern')}</div>`
                    : nothing}
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('branch_create_modal.field_name')}
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
                    .label=${this.t('branch_create_modal.field_description')}
                    .value=${this._description}
                    @change=${(e) => {
                        this._description = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    renderFooter() {
        const validId = BRANCH_ID_PATTERN.test(this._branchId);
        const validName = this._name.trim().length > 0;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('branch_create_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!(validId && validName)} @click=${this._onSubmit}>
                ${this.t('branch_create_modal.action_create')}
            </platform-button>
        `;
    }

    async _onSubmit() {
        if (!this.flowId) return;
        await this._createBranch.run({
            flow_id: this.flowId,
            body: {
                branch_id: this._branchId.trim(),
                name: this._name.trim(),
                description: this._description,
                nodes: {},
                edges: [],
            },
        });
        await this._flows.get(this.flowId);
        this.closeAfterSave();
    }
}

customElements.define('flows-branch-create-modal', FlowsBranchCreateModal);
registerModalKind(FlowsBranchCreateModal.modalKind, 'flows-branch-create-modal');
