/**
 * flows-tool-create-modal — создание inline tool.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/editors/flows-code-editor.js';
import { asString } from '../_helpers/flows-resolvers.js';
import {
    FLOW_CODE_LANGUAGES,
    flowCodeLanguageShortLabel,
    isKnownStarterCode,
    normalizeFlowCodeLanguage,
    starterCodeForLanguage,
} from '../_helpers/flows-code-languages.js';

const TOOL_ID_PATTERN = /^[a-z][a-z0-9_]*$/;
const EMPTY_PARAMETERS_SCHEMA = Object.freeze({ type: 'object', properties: {} });

export class FlowsToolCreateModal extends PlatformFormModal {
    static modalKind = 'flows.tool_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        _toolId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _code: { state: true },
        _language: { state: true },
        _schemaJson: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                margin-bottom: var(--space-3);
            }
            .field-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .language-segment {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 2px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .language-button {
                width: 36px;
                height: 24px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 0;
                border-radius: calc(var(--radius-md) - 2px);
                background: transparent;
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: var(--font-semibold);
                line-height: 1;
                cursor: pointer;
            }
            .language-button:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }
            .language-button[active] {
                color: var(--accent);
                background: var(--accent-subtle);
            }
            .language-button:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }
        `,
    ];

    constructor() {
        super();
        this._toolId = '';
        this._name = '';
        this._description = '';
        this._language = 'python';
        this._code = starterCodeForLanguage(this._language);
        this._schemaJson = JSON.stringify(EMPTY_PARAMETERS_SCHEMA, null, 2);
        this._tools = this.useResource('flows/tools');
    }

    renderHeader() { return html`<h3>${this.t('tool_create_modal.title')}</h3>`; }

    _setLanguage(language) {
        const normalized = normalizeFlowCodeLanguage(language);
        if (this._language === normalized) {
            return;
        }
        const currentCode = typeof this._code === 'string' ? this._code : '';
        this._language = normalized;
        if (currentCode.trim().length === 0 || isKnownStarterCode(currentCode)) {
            this._code = starterCodeForLanguage(normalized);
        }
        this.isDirty = true;
    }

    _renderLanguageSegment() {
        return html`
            <div class="language-segment" role="group" aria-label=${this.t('code_workbench.language_aria')}>
                ${FLOW_CODE_LANGUAGES.map((lang) => html`
                    <button
                        type="button"
                        class="language-button"
                        ?active=${this._language === lang.value}
                        title=${lang.label}
                        aria-label=${lang.label}
                        @click=${() => this._setLanguage(lang.value)}
                    >${flowCodeLanguageShortLabel(lang.value)}</button>
                `)}
            </div>
        `;
    }

    renderBody() {
        return html`
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_id')}
                    .value=${this._toolId}
                    @change=${(e) => { this._toolId = asString(e.detail.value); this.isDirty = true; }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_name')}
                    .value=${this._name}
                    @change=${(e) => { this._name = asString(e.detail.value); this.isDirty = true; }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_description')}
                    .value=${this._description}
                    @change=${(e) => { this._description = asString(e.detail.value); this.isDirty = true; }}
                ></platform-field>
            </div>
            <div class="field">
                <div class="field-head">
                    <label>${this.t('tool_create_modal.field_code')}</label>
                    ${this._renderLanguageSegment()}
                </div>
                <flows-code-editor
                    .language=${this._language}
                    .value=${this._code}
                    @change=${(e) => { this._code = asString(e.detail?.value); this.isDirty = true; }}
                ></flows-code-editor>
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_schema')}</label>
                <flows-code-editor
                    language="json"
                    .value=${this._schemaJson}
                    @change=${(e) => {
                        const v = asString(e.detail?.value);
                        this._schemaJson = v.length > 0 ? v : JSON.stringify(EMPTY_PARAMETERS_SCHEMA, null, 2);
                        this.isDirty = true;
                    }}
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
        if (
            parameters_schema.type !== 'object'
            || !parameters_schema.properties
            || typeof parameters_schema.properties !== 'object'
            || Array.isArray(parameters_schema.properties)
        ) {
            this.toast('flows:tool_create_modal.toast_schema_invalid', { type: 'error' });
            return;
        }
        this._tools.create({
            tool_id: this._toolId.trim(),
            name: this._name.trim(),
            title: this._name.trim(),
            description: this._description,
            code: this._code,
            language: this._language,
            parameters_schema,
        });
        this.closeAfterSave();
    }
}

customElements.define('flows-tool-create-modal', FlowsToolCreateModal);
registerModalKind(FlowsToolCreateModal.modalKind, 'flows-tool-create-modal');
