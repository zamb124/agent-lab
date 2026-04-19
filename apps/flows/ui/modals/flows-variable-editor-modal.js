/**
 * flows-variable-editor-modal — создание/редактирование значения company-переменной.
 *
 * Источник: useResource('flows/variables') (фабрика с операциями create/remove).
 * Создание/обновление выполняется через `create({ key, value, secret })` —
 * REST handler `POST /flows/api/v1/variables/` идемпотентен по `key`.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class FlowsVariableEditorModal extends PlatformFormModal {
    static modalKind = 'flows.variable_editor';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
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
            .field input[type='text'],
            .field textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .field textarea { min-height: 80px; resize: vertical; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .checkbox-row { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.variableKey = '';
        this.variableValue = '';
        this.variableSecret = false;
        this._key = '';
        this._value = '';
        this._secret = false;
        this._variables = this.useResource('flows/variables');
    }

    updated(changed) {
        super.updated?.(changed);
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
                <label>${this.t('variable_editor_modal.field_key')}</label>
                <input
                    type="text"
                    .value=${this._key}
                    ?disabled=${editing}
                    @input=${(e) => { this._key = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('variable_editor_modal.field_value')}</label>
                <textarea
                    .value=${this._value}
                    @input=${(e) => { this._value = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
            <div class="checkbox-row">
                <input
                    type="checkbox"
                    id="flows-var-secret"
                    .checked=${this._secret}
                    @change=${(e) => { this._secret = e.target.checked; this.isDirty = true; }}
                />
                <label for="flows-var-secret">${this.t('variable_editor_modal.field_secret')}</label>
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
        this._variables.create({ key, value: this._value, secret: this._secret });
        this.closeAfterSave();
    }
}

customElements.define('flows-variable-editor-modal', FlowsVariableEditorModal);
registerModalKind(FlowsVariableEditorModal.modalKind, 'flows-variable-editor-modal');
