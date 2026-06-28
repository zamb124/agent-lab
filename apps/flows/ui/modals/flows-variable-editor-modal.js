/**
 * flows-variable-editor-modal — создание/редактирование flow-level VariableEntry.
 *
 * Company variables редактируются через platform.company_variable_editor
 * (core/frontend platform-company-variable-editor-modal).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';

export class FlowsVariableEditorModal extends PlatformFormModal {
    static modalKind = 'flows.variable_editor';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        variableKey: { type: String },
        variableValue: { type: String },
        variableSecret: { type: Boolean },
        variablePublic: { type: Boolean },
        variableTitle: { type: String },
        variableDescription: { type: String },
        variableOrder: { type: String },
        _key: { state: true },
        _value: { state: true },
        _secret: { state: true },
        _public: { state: true },
        _title: { state: true },
        _description: { state: true },
        _order: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .hint {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-3);
                line-height: 1.4;
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.variableKey = '';
        this.variableValue = '';
        this.variableSecret = false;
        this.variablePublic = false;
        this.variableTitle = '';
        this.variableDescription = '';
        this.variableOrder = '';
        this._key = '';
        this._value = '';
        this._secret = false;
        this._public = false;
        this._title = '';
        this._description = '';
        this._order = '';
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this.flowId) {
            throw new Error('flows-variable-editor-modal: flowId required');
        }
        if (changed.has('variableKey')) this._key = this.variableKey;
        if (changed.has('variableValue')) this._value = this.variableValue;
        if (changed.has('variableSecret')) this._secret = Boolean(this.variableSecret);
        if (changed.has('variablePublic')) this._public = Boolean(this.variablePublic);
        if (changed.has('variableTitle')) this._title = this.variableTitle;
        if (changed.has('variableDescription')) this._description = this.variableDescription;
        if (changed.has('variableOrder')) this._order = this.variableOrder;
    }

    renderHeader() {
        return html`<h3>${this.t(this.variableKey ? 'variable_editor_modal.title_edit' : 'variable_editor_modal.title_create')}</h3>`;
    }

    renderBody() {
        const editing = this.variableKey.length > 0;
        return html`
            <p class="hint">${this.t('variables_modal.hint_flow_overrides_company')}</p>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('variable_editor_modal.field_key')}
                    .value=${this._key}
                    ?disabled=${editing}
                    @change=${(e) => {
                        if (!editing) {
                            this._key = typeof e.detail.value === 'string' ? e.detail.value : '';
                            this.isDirty = true;
                        }
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('variable_editor_modal.field_value')}
                    .value=${this._value}
                    @change=${(e) => {
                        this._value = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="boolean"
                    mode="edit"
                    .label=${this.t('variable_editor_modal.field_secret')}
                    .value=${this._secret}
                    @change=${(e) => {
                        this._secret = Boolean(e.detail.value);
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="boolean"
                    mode="edit"
                    .label=${this.t('api_console.var_field_public')}
                    .value=${this._public}
                    @change=${(e) => {
                        this._public = Boolean(e.detail.value);
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('api_console.var_field_title')}
                    .value=${this._title}
                    @change=${(e) => {
                        this._title = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('api_console.var_field_description')}
                    .value=${this._description}
                    @change=${(e) => {
                        this._description = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('api_console.var_field_order')}
                    .value=${this._order}
                    @change=${(e) => {
                        this._order = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    renderFooter() {
        const valid = this._key.trim().length > 0;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('variable_editor_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._onSubmit}>
                ${this.t('variable_editor_modal.action_save')}
            </platform-button>
        `;
    }

    _onSubmit() {
        const key = this._key.trim();
        if (key.length === 0) {
            return;
        }
        this._submitFlow(key);
        this.closeAfterSave();
    }

    _submitFlow(key) {
        const state = this._editor.state;
        const skillsData = state.branchData;
        const prevVars = isPlainObject(skillsData.variables) ? skillsData.variables : {};
        const prevRaw = prevVars[key];
        const prevConfig = isPlainObject(prevRaw) ? prevRaw : null;
        const orderRaw = this._order.trim();
        let order = null;
        if (orderRaw !== '') {
            order = Number(orderRaw);
            if (Number.isNaN(order)) {
                throw new Error('flows-variable-editor-modal: order must be number');
            }
        }
        const merged = {
            ...(prevConfig !== null ? prevConfig : {}),
            value: this._value,
            secret: this._secret,
            public: this._public,
            title: this._title.trim() === '' ? null : this._title.trim(),
            description: this._description.trim() === '' ? null : this._description.trim(),
            order,
        };
        const nextVars = { ...prevVars, [key]: merged };
        this._editor.updateBranchData({ data: { ...skillsData, variables: nextVars } });
        this._editor.setDirty({ dirty: true });
        this.toast('flows:toast.variable_applied', { type: 'success' });
    }
}

customElements.define('flows-variable-editor-modal', FlowsVariableEditorModal);
registerModalKind(FlowsVariableEditorModal.modalKind, 'flows-variable-editor-modal');
