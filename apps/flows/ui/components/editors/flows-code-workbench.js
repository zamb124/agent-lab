/**
 * flows-code-workbench — общий UI редактирования inline-кода для code-ноды и code-ресурса.
 *
 * variant `node`: вкладки Код / Схема (parameters_schema JSON), перспектива документации `node`.
 * variant `resource`: вкладки Код / Параметры (язык), перспектива `editor`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-code-editor.js';
import '../common/flows-code-language-icon.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    FLOW_CODE_LANGUAGES,
    flowCodeLanguageOptions,
    flowCodeMirrorLanguage,
    isKnownStarterCode,
    normalizeFlowCodeLanguage,
    starterCodeForLanguage,
} from '../../_helpers/flows-code-languages.js';

export class FlowsCodeWorkbench extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        /** @type {'node'|'resource'} */
        variant: { type: String },
        code: { type: String },
        language: { type: String },
        /** Только variant=node; объект parameters_schema из конфига ноды */
        parametersSchema: { type: Object },
        /** flows.code_docs: node | editor */
        documentationPerspective: { type: String },
        /** Ключи flow variables для автодополнения `variables.` / `state.variables.` */
        completionVariableKeys: { type: Array },
        /** Подгрузка `GET /code/editor-state` для ключей variables при наличии flow */
        completionFlowId: { type: String },
        completionBranchId: { type: String },
        /** Смена ключа сбрасывает вкладку и ошибку схемы */
        scopeKey: { type: String },
        _mainTab: { state: true },
        _schemaInvalid: { state: true },
        _schemaError: { state: true },
        _editorStateVarKeys: { state: true },
        _codeValidationStatus: { state: true },
        _codeValidationMessage: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-height: 0;
            }
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: 0;
            }
            .toolbar-start-wrap {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1 1 auto;
                box-sizing: border-box;
            }
            .toolbar-start-actions {
                display: inline-flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .toolbar-icon-button {
                width: 28px;
                height: 28px;
                padding: 0;
                margin: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
                border-radius: var(--radius-full, 999px);
                cursor: pointer;
                transition:
                    color var(--duration-fast, 0.2s) ease,
                    background var(--duration-fast, 0.2s) ease,
                    border-color var(--duration-fast, 0.2s) ease;
            }
            .toolbar-icon-button:hover,
            .toolbar-icon-button:focus-visible {
                color: var(--text-primary);
                background: rgba(255, 255, 255, 0.1);
                border-color: var(--border-default, rgba(255, 255, 255, 0.14));
                outline: none;
            }
            .language-segment {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 2px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                flex: 0 0 auto;
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
                white-space: nowrap;
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
            .execute-tool-hint-trigger {
                cursor: help;
            }
            .code-validation-status {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                min-width: 28px;
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
            .code-validation-status[data-state='pending'] {
                color: var(--text-secondary);
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
            .main-tabs {
                display: flex;
                gap: var(--space-1);
                flex-wrap: nowrap;
                flex-shrink: 0;
            }
            .main-tab {
                padding: 6px 14px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
            }
            .main-tab[active] {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent-subtle);
            }
            .schema-editor-wrap[data-invalid] flows-code-editor {
                border-color: var(--error);
            }
            .schema-error {
                color: var(--error);
                font-size: var(--text-xs);
                margin-top: var(--space-1);
            }
            .resource-secondary-wrap {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                background: var(--glass-solid-subtle);
            }
            .resource-secondary-wrap flows-code-editor {
                border: none;
                border-radius: 0;
            }
            .params-panel {
                padding: var(--space-3);
                box-sizing: border-box;
            }
            .params-panel platform-field {
                max-width: 28rem;
            }
        `,
    ];

    constructor() {
        super();
        this.variant = 'node';
        this.code = '';
        this.language = 'python';
        this.parametersSchema = { type: 'object', properties: {}, required: [] };
        this.documentationPerspective = 'node';
        this.completionVariableKeys = [];
        this.completionFlowId = '';
        this.completionBranchId = '';
        this.scopeKey = '';
        this._mainTab = 'code';
        this._schemaInvalid = false;
        this._schemaError = '';
        this._editorStateVarKeys = [];
        this._codeValidationStatus = 'idle';
        this._codeValidationMessage = '';
        /** @type {number} */
        this._editorStateFetchSeq = 0;
        /** @type {number} */
        this._codeValidationTimer = 0;
        /** @type {number} */
        this._codeValidationSeq = 0;
        this._codeEditorStateOp = this.useOp('flows/code_editor_state');
        this._codeValidateOp = this.useOp('flows/code_validate');
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('scopeKey')) {
            this._mainTab = 'code';
            this._schemaInvalid = false;
            this._schemaError = '';
            this._codeValidationStatus = 'idle';
            this._codeValidationMessage = '';
        }
        if (changed.has('completionFlowId') || changed.has('completionBranchId')) {
            this._editorStateVarKeys = [];
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('completionFlowId') || changed.has('completionBranchId')) {
            void this._syncEditorStateVariableKeys();
        }
        if (changed.has('code') || changed.has('language') || changed.has('variant') || changed.has('scopeKey')) {
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

    _documentationPerspectiveResolved() {
        if (typeof this.documentationPerspective === 'string' && this.documentationPerspective.length > 0) {
            return this.documentationPerspective;
        }
        return this.variant === 'resource' ? 'editor' : 'node';
    }

    _completionContextPayload() {
        const lang = this._normalizedLanguage();
        return {
            language: lang,
            perspective: this._documentationPerspectiveResolved(),
            include_runtime_namespace_extras: true,
        };
    }

    _validationKind() {
        return this.variant === 'resource' ? 'tool' : 'node';
    }

    _validationPayload() {
        const code = typeof this.code === 'string' ? this.code : '';
        const payload = {
            code,
            language: this._normalizedLanguage(),
            kind: this._validationKind(),
            node_type: this._validationKind() === 'tool' ? 'tool' : 'code',
        };
        if (typeof this.completionFlowId === 'string' && this.completionFlowId.trim().length > 0) {
            payload.flow_id = this.completionFlowId.trim();
        }
        if (typeof this.completionBranchId === 'string' && this.completionBranchId.trim().length > 0) {
            payload.branch_id = this.completionBranchId.trim();
        }
        return payload;
    }

    _scheduleCodeValidation() {
        const code = typeof this.code === 'string' ? this.code : '';
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
        if (code.trim().length === 0) {
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
        const payload = this._validationPayload();
        let result;
        try {
            result = await this._codeValidateOp.run(payload);
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

    _effectiveCompletionVariableKeys() {
        const manual = Array.isArray(this.completionVariableKeys)
            ? this.completionVariableKeys.filter((k) => typeof k === 'string')
            : [];
        const fromState = Array.isArray(this._editorStateVarKeys)
            ? this._editorStateVarKeys.filter((k) => typeof k === 'string')
            : [];
        const out = [];
        const seen = new Set();
        for (const k of [...manual, ...fromState]) {
            if (seen.has(k)) {
                continue;
            }
            seen.add(k);
            out.push(k);
        }
        return out;
    }

    async _syncEditorStateVariableKeys() {
        const seq = this._editorStateFetchSeq + 1;
        this._editorStateFetchSeq = seq;
        const fid = typeof this.completionFlowId === 'string' ? this.completionFlowId.trim() : '';
        if (fid.length === 0) {
            if (seq === this._editorStateFetchSeq) {
                this._editorStateVarKeys = [];
            }
            return;
        }
        const bid =
            typeof this.completionBranchId === 'string' && this.completionBranchId.length > 0
                ? this.completionBranchId
                : 'default';
        let raw;
        try {
            raw = await this._codeEditorStateOp.run({ flow_id: fid, branch_id: bid });
        } catch {
            if (seq !== this._editorStateFetchSeq) {
                return;
            }
            this._editorStateVarKeys = [];
            return;
        }
        if (seq !== this._editorStateFetchSeq) {
            return;
        }
        const varsRaw =
            raw &&
            typeof raw === 'object' &&
            raw !== null &&
            'variables' in raw &&
            raw.variables &&
            typeof raw.variables === 'object' &&
            !Array.isArray(raw.variables)
                ? raw.variables
                : {};
        this._editorStateVarKeys = Object.keys(varsRaw);
    }

    _normalizedLanguage() {
        const raw = typeof this.language === 'string' ? this.language : 'python';
        return normalizeFlowCodeLanguage(raw);
    }

    _cmLanguageForCodeTab() {
        return flowCodeMirrorLanguage(this._normalizedLanguage());
    }

    _secondTabLabel() {
        if (this.variant === 'resource') {
            return this.t('code_workbench.tab_params');
        }
        return this.t('code_node_editor.tab_schema');
    }

    _openDocs() {
        const lang = this._normalizedLanguage();
        const perspective = typeof this.documentationPerspective === 'string' && this.documentationPerspective.length > 0
            ? this.documentationPerspective
            : this.variant === 'resource'
              ? 'editor'
              : 'node';
        this.openModal('flows.code_docs', { language: lang, documentationPerspective: perspective });
    }

    _emitWorkbench(detail) {
        if (!detail || typeof detail !== 'object' || !('type' in detail)) {
            throw new Error('flows-code-workbench: code-workbench-change detail');
        }
        this.emit('code-workbench-change', detail);
    }

    _onCodeEditorChange(e) {
        const value = asString(e.detail?.value);
        this._emitWorkbench({ type: 'code', value });
    }

    _onSchemaEditorChange(e) {
        const value = asString(e.detail?.value);
        try {
            const parsed = value.trim().length === 0 ? null : JSON.parse(value);
            this._schemaInvalid = false;
            this._schemaError = '';
            this._emitWorkbench({ type: 'parameters_schema', parameters_schema: parsed });
        } catch (err) {
            this._schemaInvalid = true;
            this._schemaError = err instanceof Error ? err.message : String(err);
        }
    }

    _emitLanguageChange(language) {
        const normalized = normalizeFlowCodeLanguage(language);
        const currentCode = typeof this.code === 'string' ? this.code : '';
        const detail = { type: 'language', language: normalized };
        if (currentCode.trim().length === 0 || isKnownStarterCode(currentCode)) {
            detail.code = starterCodeForLanguage(normalized);
        }
        this._emitWorkbench(detail);
    }

    _onLanguageFieldChange(e) {
        const d = e.detail;
        if (!isPlainObject(d)) {
            throw new Error('flows-code-workbench: language change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-code-workbench: language detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-code-workbench: language string required');
        }
        if (!FLOW_CODE_LANGUAGES.some((lang) => lang.value === v)) {
            throw new Error('flows-code-workbench: language unknown');
        }
        this._emitLanguageChange(v);
    }

    _renderLanguageSegment() {
        const current = this._normalizedLanguage();
        return html`
            <div class="language-segment" role="group" aria-label=${this.t('code_workbench.language_aria')}>
                ${FLOW_CODE_LANGUAGES.map((lang) => html`
                    <button
                        type="button"
                        class="language-button"
                        ?active=${current === lang.value}
                        title=${lang.label}
                        aria-label=${lang.label}
                        @click=${() => this._emitLanguageChange(lang.value)}
                    >
                        <flows-code-language-icon language=${lang.value} size="18"></flows-code-language-icon>
                    </button>
                `)}
            </div>
        `;
    }

    _renderValidationStatus() {
        const status = this._codeValidationStatus;
        if (status === 'idle') {
            return '';
        }
        let iconName = 'circle';
        let label = this._codeValidationMessage;
        if (status === 'pending') {
            iconName = 'circle';
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

    _renderToolbarStart() {
        const hintLabel = this.t('code_node_editor.execute_tool_hint_aria');
        const secondaryLabel = this._secondTabLabel();
        return html`
            <div class="toolbar-start-wrap">
                <div class="main-tabs" role="tablist">
                    <button
                        type="button"
                        class="main-tab"
                        role="tab"
                        ?active=${this._mainTab === 'code'}
                        @click=${() => { this._mainTab = 'code'; }}
                    >
                        ${this.t('code_node_editor.tab_code')}
                    </button>
                    <button
                        type="button"
                        class="main-tab"
                        role="tab"
                        ?active=${this._mainTab === 'secondary'}
                        @click=${() => { this._mainTab = 'secondary'; }}
                    >
                        ${secondaryLabel}
                    </button>
                </div>
                ${this._renderLanguageSegment()}
                ${this._renderValidationStatus()}
                <div class="toolbar-start-actions">
                    <button
                        type="button"
                        class="toolbar-icon-button"
                        title=${this.t('code_node_editor.docs')}
                        aria-label=${this.t('code_node_editor.docs')}
                        @click=${this._openDocs}
                    >
                        <platform-icon name="book-open" size="16"></platform-icon>
                    </button>
                    <platform-help-hint
                        .text=${this.t('code_node_editor.execute_tool_hint')}
                        .label=${hintLabel}
                        placement="bottom"
                    >
                        <button
                            type="button"
                            class="toolbar-icon-button execute-tool-hint-trigger"
                            aria-label=${hintLabel}
                            title=${hintLabel}
                        >
                            <platform-icon name="info" size="16"></platform-icon>
                        </button>
                    </platform-help-hint>
                </div>
            </div>
        `;
    }

    _parametersSchemaObject() {
        const a = this.parametersSchema;
        if (a !== null && typeof a === 'object' && !Array.isArray(a)) {
            return a;
        }
        return { type: 'object', properties: {}, required: [] };
    }

    render() {
        const code = typeof this.code === 'string' ? this.code : '';
        const parametersSchema = this._parametersSchemaObject();
        const schemaText = JSON.stringify(parametersSchema, null, 2);
        const cmLang = this._cmLanguageForCodeTab();
        const completionCtx = this._completionContextPayload();
        const varKeysEff = this._effectiveCompletionVariableKeys();

        if (this.variant === 'resource') {
            const lang = this._normalizedLanguage();
            const langValues = flowCodeLanguageOptions();
            return html`
                <div class="settings-wrap">
                    ${this._mainTab === 'code'
                        ? html`
                            <flows-code-editor
                                language=${cmLang}
                                .value=${code}
                                .completionContext=${completionCtx}
                                .completionVariableKeys=${varKeysEff}
                                @change=${this._onCodeEditorChange}
                            >
                                <div slot="toolbar-start">${this._renderToolbarStart()}</div>
                            </flows-code-editor>
                        `
                        : html`
                            <div class="resource-secondary-wrap">
                                <flows-code-editor
                                    .headerOnly=${true}
                                    language="text"
                                    .value=${''}
                                >
                                    <div slot="toolbar-start">${this._renderToolbarStart()}</div>
                                </flows-code-editor>
                                <div class="params-panel">
                                    <platform-field
                                        mode="edit"
                                        type="enum"
                                        .label=${this.t('code_resource_editor.language')}
                                        .value=${lang}
                                        .config=${{ values: langValues }}
                                        @change=${this._onLanguageFieldChange}
                                    ></platform-field>
                                </div>
                            </div>
                        `}
                </div>
            `;
        }

        return html`
            <div class="settings-wrap">
                ${this._mainTab === 'code'
                    ? html`
                        <flows-code-editor
                            language=${cmLang}
                            .value=${code}
                            .completionContext=${completionCtx}
                            .completionVariableKeys=${varKeysEff}
                            @change=${this._onCodeEditorChange}
                        >
                            <div slot="toolbar-start">${this._renderToolbarStart()}</div>
                        </flows-code-editor>
                    `
                    : html`
                        <div class="schema-editor-wrap" ?data-invalid=${this._schemaInvalid}>
                            <flows-code-editor
                                language="json"
                                .value=${schemaText}
                                @change=${this._onSchemaEditorChange}
                            >
                                <div slot="toolbar-start">${this._renderToolbarStart()}</div>
                            </flows-code-editor>
                            ${this._schemaInvalid ? html`<div class="schema-error">${this._schemaError}</div>` : ''}
                        </div>
                    `}
            </div>
        `;
    }
}

customElements.define('flows-code-workbench', FlowsCodeWorkbench);
