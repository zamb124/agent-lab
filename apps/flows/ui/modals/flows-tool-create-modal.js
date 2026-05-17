/**
 * flows-tool-create-modal — создание inline tool.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/common/flows-code-language-icon.js';
import '../components/editors/flows-code-editor.js';
import { asString } from '../_helpers/flows-resolvers.js';
import {
    FLOW_CODE_LANGUAGES,
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
        _codeValidationStatus: { state: true },
        _codeValidationMessage: { state: true },
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
            .field-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
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
            .language-button flows-code-language-icon {
                pointer-events: none;
            }
            .code-validation-status {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                max-width: 220px;
                height: 28px;
                padding: 0 9px;
                box-sizing: border-box;
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1;
                white-space: nowrap;
            }
            .code-validation-status[data-state='valid'] {
                color: var(--success);
                background: var(--success-bg);
                border-color: var(--success-border);
            }
            .code-validation-status[data-state='invalid'] {
                color: var(--error);
                background: var(--error-bg);
                border-color: var(--error-border);
            }
            .code-validation-text {
                overflow: hidden;
                text-overflow: ellipsis;
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
        this._codeValidationStatus = 'idle';
        this._codeValidationMessage = '';
        this._codeValidationTimer = 0;
        this._codeValidationSeq = 0;
        this._tools = this.useResource('flows/tools');
        this._codeValidateOp = this.useOp('flows/code_validate');
    }

    renderHeader() { return html`<h3>${this.t('tool_create_modal.title')}</h3>`; }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('_code') || changed.has('_language')) {
            this._scheduleCodeValidation();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
    }

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

    _validationPayload() {
        return {
            code: this._code,
            language: this._language,
            kind: 'tool',
            node_type: 'tool',
        };
    }

    _scheduleCodeValidation() {
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
        if (this._code.trim().length === 0) {
            this._codeValidationSeq += 1;
            this._codeValidationStatus = 'idle';
            this._codeValidationMessage = '';
            return;
        }
        this._codeValidationStatus = 'pending';
        this._codeValidationMessage = this.t('code_workbench.validation_checking');
        this._codeValidationTimer = window.setTimeout(() => {
            this._codeValidationTimer = 0;
            void this._runCodeValidation();
        }, 650);
    }

    async _runCodeValidation() {
        const seq = this._codeValidationSeq + 1;
        this._codeValidationSeq = seq;
        let result;
        try {
            result = await this._codeValidateOp.run(this._validationPayload());
        } catch (err) {
            if (seq !== this._codeValidationSeq) {
                return;
            }
            this._codeValidationStatus = 'invalid';
            this._codeValidationMessage = err instanceof Error ? err.message : String(err);
            return;
        }
        if (seq !== this._codeValidationSeq) {
            return;
        }
        if (!result || typeof result !== 'object' || result.valid !== true) {
            const message = result && typeof result === 'object' && typeof result.error === 'string'
                ? result.error
                : this.t('code_workbench.validation_invalid');
            this._codeValidationStatus = 'invalid';
            this._codeValidationMessage = message;
            return;
        }
        this._codeValidationStatus = 'valid';
        this._codeValidationMessage = this.t('code_workbench.validation_valid');
    }

    _renderValidationStatus() {
        const status = this._codeValidationStatus;
        if (status === 'idle') {
            return '';
        }
        let iconName = 'circle';
        let label = this._codeValidationMessage;
        if (status === 'pending') {
            label = this.t('code_workbench.validation_checking');
        } else if (status === 'valid') {
            iconName = 'check';
            label = this.t('code_workbench.validation_valid');
        } else if (status === 'invalid') {
            iconName = 'alert-triangle';
            if (typeof label !== 'string' || label.length === 0) {
                label = this.t('code_workbench.validation_invalid');
            }
        }
        return html`
            <span class="code-validation-status" data-state=${status} title=${label}>
                <platform-icon name=${iconName} size="14"></platform-icon>
                <span class="code-validation-text">${label}</span>
            </span>
        `;
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
                    >
                        <flows-code-language-icon language=${lang.value} size="18"></flows-code-language-icon>
                    </button>
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
                    <div class="field-actions">
                        ${this._renderValidationStatus()}
                        ${this._renderLanguageSegment()}
                    </div>
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
        const valid = TOOL_ID_PATTERN.test(this._toolId)
            && this._name.trim()
            && this._codeValidationStatus !== 'pending'
            && this._codeValidationStatus !== 'invalid';
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
