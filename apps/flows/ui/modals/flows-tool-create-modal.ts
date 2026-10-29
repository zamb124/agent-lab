/**
 * flows-tool-create-modal — создание inline tool.
 */

import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/schema/platform-schema-editor.js';
import '../components/editors/flows-code-editor.js';
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import {
    FLOW_CODE_LANGUAGES,
    isKnownStarterCode,
    normalizeFlowCodeLanguage,
    starterCodeForLanguage,
} from '../_helpers/flows-code-languages.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

const TOOL_ID_PATTERN = /^[a-z][a-z0-9_]*$/;
const EMPTY_PARAMETERS_SCHEMA = Object.freeze({ type: 'object', properties: {} });

export class FlowsToolCreateModal extends PlatformFormModal {
    static modalKind = 'flows.tool_create';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        _toolId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _code: { state: true },
        _language: { state: true },
        _parametersSchema: { state: true },
        _schemaValid: { state: true },
        _codeValidationStatus: { state: true },
        _codeValidationMessage: { state: true },
    }
    declare _toolId: string;
    declare _name: string;
    declare _description: string;
    declare _code: string;
    declare _language: string;
    declare _parametersSchema: Record<string, unknown>;
    declare _schemaValid: boolean;
    declare _codeValidationStatus: string;
    declare _codeValidationMessage: string;
;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        glassStyles,
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
            .code-validation-status {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                max-width: 220px;
                height: 28px;
                padding: 0 9px;
                box-sizing: border-box;
                border-radius: var(--radius-full, 999px);
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
    private _tools: ResourceController;
    private _codeValidateOp: OpController;
    private _codeValidationTimer: number;
    private _codeValidationSeq: number;

    constructor() {
        super();
        this._toolId = '';
        this._name = '';
        this._description = '';
        this._language = 'python';
        this._code = starterCodeForLanguage(this._language);
        this._parametersSchema = { ...EMPTY_PARAMETERS_SCHEMA, properties: {} };
        this._schemaValid = true;
        this._codeValidationStatus = 'idle';
        this._codeValidationMessage = '';
        this._codeValidationTimer = 0;
        this._codeValidationSeq = 0;
        this._tools = this.useResource('flows/tools');
        this._codeValidateOp = this.useOp('flows/code_validate');
    }

    override renderHeader() { return html`<h3>${this.t('tool_create_modal.title')}</h3>`; }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('_code') || changed.has('_language')) {
            this._scheduleCodeValidation();
        }
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
    }

    _setLanguage(language: unknown) {
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
        if (!isPlainObject(result) || result.valid !== true) {
            let message = this.t('code_workbench.validation_invalid');
            if (isPlainObject(result)) {
                const error = result.error;
                if (typeof error === 'string') {
                    message = error;
                }
            }
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
            <span class="code-validation-status glass-subtle" data-state=${status} title=${label}>
                <platform-icon name=${iconName} size="14"></platform-icon>
                <span class="code-validation-text">${label}</span>
            </span>
        `;
    }

    _renderLanguageSegment() {
        return html`
            <platform-segmented-control
                density="compact"
                .value=${this._language}
                .items=${FLOW_CODE_LANGUAGES.map((lang) => ({
                    value: lang.value,
                    label: lang.label,
                    title: lang.label,
                }))}
                aria-label=${this.t('code_workbench.language_aria')}
                @change=${(e: CustomEvent) => this._setLanguage(e.detail.value)}
            ></platform-segmented-control>
        `;
    }

    override renderBody() {
        return html`
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_id')}
                    .value=${this._toolId}
                    @change=${(e: CustomEvent) => { this._toolId = asString(e.detail.value); this.isDirty = true; }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_name')}
                    .value=${this._name}
                    @change=${(e: CustomEvent) => { this._name = asString(e.detail.value); this.isDirty = true; }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tool_create_modal.field_description')}
                    .value=${this._description}
                    @change=${(e: CustomEvent) => { this._description = asString(e.detail.value); this.isDirty = true; }}
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
                    @change=${(e: CustomEvent) => { this._code = asString(e.detail?.value); this.isDirty = true; }}
                ></flows-code-editor>
            </div>
            <div class="field">
                <label>${this.t('tool_create_modal.field_schema')}</label>
                <platform-schema-editor
                    .value=${this._parametersSchema}
                    @schema-change=${(e: CustomEvent) => {
                        const detail = e.detail;
                        if (!isPlainObject(detail) || !('valid' in detail)) {
                            throw new Error('flows-tool-create-modal: schema-change detail');
                        }
                        this._schemaValid = detail.valid === true;
                        if (detail.valid === true) {
                            const value = detail.value;
                            this._parametersSchema = isPlainObject(value)
                                ? value
                                : { ...EMPTY_PARAMETERS_SCHEMA, properties: {} };
                        }
                        this.isDirty = true;
                    }}
                ></platform-schema-editor>
            </div>
        `;
    }

    override renderFooter() {
        const valid = TOOL_ID_PATTERN.test(this._toolId)
            && this._name.trim().length > 0
            && this._schemaValid
            && this._codeValidationStatus !== 'pending'
            && this._codeValidationStatus !== 'invalid';
        return html`
            <platform-button @click=${() => this.close()}>${this.t('common.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._save}>
                ${this.t('tool_create_modal.action_create')}
            </platform-button>
        `;
    }

    _save() {
        if (!this._schemaValid) {
            this.toast('flows:tool_create_modal.toast_schema_invalid', { type: 'error' });
            return;
        }
        const parameters_schema = this._parametersSchema;
        const properties = parameters_schema.properties;
        if (parameters_schema.type !== 'object' || !isPlainObject(properties)) {
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
