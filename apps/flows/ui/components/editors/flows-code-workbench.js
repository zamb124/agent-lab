/**
 * flows-code-workbench — общий UI редактирования inline-кода для code-ноды и code-ресурса.
 *
 * variant `node`: вкладки Код / Схема (args_schema JSON), перспектива документации `node`.
 * variant `resource`: вкладки Код / Параметры (язык), перспектива `editor`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-code-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';

const RESOURCE_LANGUAGES = Object.freeze(['python', 'javascript']);

export class FlowsCodeWorkbench extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        /** @type {'node'|'resource'} */
        variant: { type: String },
        code: { type: String },
        language: { type: String },
        /** Только variant=node; объект args_schema из конфига ноды */
        argsSchema: { type: Object },
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
            .execute-tool-hint-trigger {
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
                cursor: help;
                transition:
                    color var(--duration-fast, 0.2s) ease,
                    background var(--duration-fast, 0.2s) ease,
                    border-color var(--duration-fast, 0.2s) ease;
            }
            .execute-tool-hint-trigger:hover,
            .execute-tool-hint-trigger:focus-visible {
                color: var(--text-primary);
                background: rgba(255, 255, 255, 0.1);
                border-color: var(--border-default, rgba(255, 255, 255, 0.14));
                outline: none;
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
        this.argsSchema = {};
        this.documentationPerspective = 'node';
        this.completionVariableKeys = [];
        this.completionFlowId = '';
        this.completionBranchId = '';
        this.scopeKey = '';
        this._mainTab = 'code';
        this._schemaInvalid = false;
        this._schemaError = '';
        this._editorStateVarKeys = [];
        /** @type {number} */
        this._editorStateFetchSeq = 0;
        this._codeEditorStateOp = this.useOp('flows/code_editor_state');
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('scopeKey')) {
            this._mainTab = 'code';
            this._schemaInvalid = false;
            this._schemaError = '';
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
            language: lang === 'javascript' ? 'javascript' : 'python',
            perspective: this._documentationPerspectiveResolved(),
            include_runtime_namespace_extras: true,
        };
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
        const v = typeof this.variant === 'string' ? this.variant : 'node';
        const raw = typeof this.language === 'string' ? this.language : 'python';
        if (v === 'resource') {
            if (RESOURCE_LANGUAGES.includes(raw)) {
                return raw;
            }
            return 'python';
        }
        if (raw === 'javascript') {
            return 'javascript';
        }
        if (raw === 'python') {
            return 'python';
        }
        return raw.length > 0 ? raw : 'python';
    }

    _cmLanguageForCodeTab() {
        const lang = this._normalizedLanguage();
        if (lang === 'python') {
            return 'python';
        }
        return 'text';
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
            this._emitWorkbench({ type: 'args_schema', args_schema: parsed });
        } catch (err) {
            this._schemaInvalid = true;
            this._schemaError = err instanceof Error ? err.message : String(err);
        }
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
        if (!RESOURCE_LANGUAGES.includes(v)) {
            throw new Error('flows-code-workbench: language unknown');
        }
        this._emitWorkbench({ type: 'language', language: v });
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
                <div class="toolbar-start-actions">
                    <glass-button size="sm" variant="ghost" @click=${this._openDocs}>
                        ${this.t('code_node_editor.docs')}
                    </glass-button>
                    <platform-help-hint
                        .text=${this.t('code_node_editor.execute_tool_hint')}
                        .label=${hintLabel}
                        placement="bottom"
                    >
                        <button type="button" class="execute-tool-hint-trigger" aria-label=${hintLabel}>
                            <platform-icon name="info" size="16"></platform-icon>
                        </button>
                    </platform-help-hint>
                </div>
            </div>
        `;
    }

    _argsSchemaObject() {
        const a = this.argsSchema;
        if (a !== null && typeof a === 'object' && !Array.isArray(a)) {
            return a;
        }
        return {};
    }

    render() {
        const code = typeof this.code === 'string' ? this.code : '';
        const argsSchema = this._argsSchemaObject();
        const schemaText = JSON.stringify(argsSchema, null, 2);
        const cmLang = this._cmLanguageForCodeTab();
        const completionCtx = this._completionContextPayload();
        const varKeysEff = this._effectiveCompletionVariableKeys();

        if (this.variant === 'resource') {
            const lang = this._normalizedLanguage();
            const langValues = RESOURCE_LANGUAGES.map((l) => ({ value: l, label: l }));
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
