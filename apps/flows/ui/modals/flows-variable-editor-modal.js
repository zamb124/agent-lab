/**
 * flows-variable-editor-modal — создание/редактирование одной переменной.
 *
 * Контракт переменной симметричен для обоих scope: { key, value, secret }.
 *
 * Отправка ветвится по `scope`:
 *   - 'company' — useResource('flows/variables').create({ key, value, secret })
 *                 (REST POST /flows/api/v1/variables идемпотентен по key).
 *   - 'flow'    — обновление черновика skillsData.variables через editor op
 *                 (`updateBranchData` + `setDirty`). A2A-поля
 *                 (public/title/description/order) сохраняются неизменными
 *                 при обновлении существующего ключа. Финальная фиксация —
 *                 общим Save в editor-header.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';

const SCOPE_COMPANY = 'company';
const SCOPE_FLOW = 'flow';

export class FlowsVariableEditorModal extends PlatformFormModal {
    static modalKind = 'flows.variable_editor';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        scope: { type: String },
        flowId: { type: String },
        variableKey: { type: String },
        variableValue: { type: String },
        variableSecret: { type: Boolean },
        _key: { state: true },
        _value: { state: true },
        _secret: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.scope = SCOPE_COMPANY;
        this.flowId = '';
        this.variableKey = '';
        this.variableValue = '';
        this.variableSecret = false;
        this._key = '';
        this._value = '';
        this._secret = false;
        this._variables = this.useResource('flows/variables');
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('scope') && this.scope !== SCOPE_COMPANY && this.scope !== SCOPE_FLOW) {
            throw new Error(`flows-variable-editor-modal: invalid scope "${this.scope}"`);
        }
        if (changed.has('scope') && this.scope === SCOPE_FLOW && !this.flowId) {
            throw new Error('flows-variable-editor-modal: flowId required for scope="flow"');
        }
        if (changed.has('variableKey')) this._key = this.variableKey;
        if (changed.has('variableValue')) this._value = this.variableValue;
        if (changed.has('variableSecret')) this._secret = Boolean(this.variableSecret);
    }

    renderHeader() {
        return html`<h3>${this.t(this.variableKey ? 'variable_editor_modal.title_edit' : 'variable_editor_modal.title_create')}</h3>`;
    }

    renderBody() {
        const editing = this.variableKey.length > 0;
        return html`
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
        if (key.length === 0) return;
        if (this.scope === SCOPE_FLOW) {
            this._submitFlow(key);
        } else {
            this._submitCompany(key);
        }
        this.closeAfterSave();
    }

    _submitCompany(key) {
        this._variables.create({ key, value: this._value, secret: this._secret });
    }

    _submitFlow(key) {
        const state = this._editor.state;
        const skillsData = state.branchData;
        const prevVars = isPlainObject(skillsData.variables) ? skillsData.variables : {};
        const prevRaw = prevVars[key];
        const prevConfig = isPlainObject(prevRaw) ? prevRaw : null;
        const merged = {
            ...(prevConfig !== null ? prevConfig : {}),
            value: this._value,
            secret: this._secret,
        };
        const nextVars = { ...prevVars, [key]: merged };
        this._editor.updateBranchData({ data: { ...skillsData, variables: nextVars } });
        this._editor.setDirty({ dirty: true });
        this.toast('flows:toast.variable_applied', { type: 'success' });
    }
}

customElements.define('flows-variable-editor-modal', FlowsVariableEditorModal);
registerModalKind(FlowsVariableEditorModal.modalKind, 'flows-variable-editor-modal');
