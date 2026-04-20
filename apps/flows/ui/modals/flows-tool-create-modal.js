/**
 * flows-tool-create-modal — создание inline tool.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '../components/editors/flows-code-editor.js';
import { asString } from '../_helpers/flows-resolvers.js';

const TOOL_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

export class FlowsToolCreateModal extends PlatformFormModal {
    static modalKind = 'flows.tool_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        _toolId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _code: { state: true },
        _schemaJson: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this._toolId = '';
        this._name = '';
        this._description = '';
        this._code = '';
        this._schemaJson = '{}';
        this._tools = this.useResource('flows/tools');
    }

    renderHeader() { return html`<h3>${this.t('tool_create_modal.title')}</h3>`; }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('tool_create_modal.field_id')}</label>
                <input type="text" .value=${this._toolId} @input=${(e) => { this._toolId = e.target.value; this.isDirty = true; }} />
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.isDirty = true; }} />
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_description')}</label>
                <input type="text" .value=${this._description} @input=${(e) => { this._description = e.target.value; this.isDirty = true; }} />
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_code')}</label>
                <flows-code-editor
                    language="python"
                    .value=${this._code}
                    @change=${(e) => { this._code = asString(e.detail?.value); this.isDirty = true; }}
                ></flows-code-editor>
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_schema')}</label>
                <flows-code-editor
                    language="json"
                    .value=${this._schemaJson}
                    @change=${(e) => { const v = asString(e.detail?.value); this._schemaJson = v.length > 0 ? v : '{}'; this.isDirty = true; }}
                ></flows-code-editor>
            </div>
        `;
    }

    renderFooter() {
        const valid = TOOL_ID_PATTERN.test(this._toolId) && this._name.trim();
        return html`
            <platform-button @click=${() => this.close()}>${this.t('tool_create_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._save}>
                ${this.t('tool_create_modal.action_create')}
            </platform-button>
        `;
    }

    _save() {
        let parameters_schema;
        try {
            parameters_schema = JSON.parse(this._schemaJson);
        } catch (err) {
            this.toast('flows:tool_create_modal.toast_schema_invalid', { type: 'error' });
            return;
        }
        if (!parameters_schema || typeof parameters_schema !== 'object' || Array.isArray(parameters_schema)) {
            this.toast('flows:tool_create_modal.toast_schema_invalid', { type: 'error' });
            return;
        }
        this._tools.create({
            tool_id: this._toolId.trim(),
            name: this._name.trim(),
            description: this._description,
            code: this._code,
            parameters_schema,
        });
        this.closeAfterSave();
    }
}

customElements.define('flows-tool-create-modal', FlowsToolCreateModal);
registerModalKind(FlowsToolCreateModal.modalKind, 'flows-tool-create-modal');
