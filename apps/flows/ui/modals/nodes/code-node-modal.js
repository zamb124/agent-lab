/**
 * CodeNodeModal - модалка редактирования Code Node
 * Универсальная нода для выполнения кода (Python, JavaScript, Go)
 */
import { html, css } from 'lit';
import { BaseNodeModal } from './base-node-modal.js';
import '../../components/editors/json-field-editor.js';
import '@platform/lib/components/platform-icon.js';
import { isValidLlmParametersSchema } from '../../utils/flow-parameters-schema.js';

const DEFAULT_PARAMETERS_SCHEMA_STR = () =>
    JSON.stringify({ type: 'object', properties: {}, required: [] }, null, 2);

export class CodeNodeModal extends BaseNodeModal {
    static styles = [
        BaseNodeModal.styles,
        css`
            .code-section {
                flex: 1;
                display: flex;
                flex-direction: column;
            }

            .code-mode-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }

            .code-mode-row .form-select {
                width: auto;
            }

            .function-path-section {
                margin-bottom: var(--space-3);
            }

            .help-section {
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
            }

            .help-section h4 {
                margin: 0 0 var(--space-2);
                color: var(--text-secondary);
            }

            .help-section ul {
                margin: 0;
                padding-left: var(--space-4);
            }

            .help-section li {
                margin-bottom: var(--space-1);
                color: var(--text-tertiary);
            }

            .help-section code {
                color: var(--accent);
                background: var(--glass-tint-medium);
                padding: 1px 4px;
                border-radius: 3px;
            }

            .code-mode-toggle {
                display: flex;
                gap: 0;
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                padding: 2px;
                border: 1px solid var(--border-subtle);
            }

            .code-mode-btn {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: calc(var(--radius-md) - 2px);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                flex: 1;
                text-align: center;
            }

            .code-mode-btn:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }

            .code-mode-btn.active {
                background: var(--accent);
                color: white;
                box-shadow: var(--shadow-sm);
            }

            .code-schema-shell {
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--border-subtle);
            }

            .code-schema-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border-bottom: 1px solid var(--border-subtle);
            }

            .code-schema-header-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }

            .code-schema-header-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .editor-btn {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }

            .editor-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--glass-tint-medium);
            }

            .editor-btn.active {
                color: var(--accent);
                border-color: var(--accent);
            }
        `,
    ];

    static properties = {
        ...BaseNodeModal.properties,
        codeMode: { type: String },
        language: { type: String },
        _codeMainPane: { type: String, state: true },
    };

    constructor() {
        super();
        this.codeMode = 'INLINE_CODE';
        this.language = 'python';
        this._codeMainPane = 'code';
    }

    getNodeType() {
        return 'code';
    }

    getModalTitle() {
        return this.i18n.t('node_modal.titles.code');
    }

    showModal(nodeId = '', config = {}) {
        super.showModal(nodeId, config);

        this.language = config.language || 'python';

        if (config.tool_id) {
            this.codeMode = 'TOOL_ID';
        } else if (config.function) {
            this.codeMode = 'CODE_REFERENCE';
        } else {
            this.codeMode = 'INLINE_CODE';
        }
        this._codeMainPane = 'code';
    }

    _onCodeModeChange(mode) {
        this.codeMode = mode;
    }

    _parametersSchemaEditorValue() {
        const ps = this.nodeConfig.parameters_schema;
        if (ps && typeof ps === 'object') {
            return JSON.stringify(ps, null, 2);
        }
        return DEFAULT_PARAMETERS_SCHEMA_STR();
    }

    _buildConfig() {
        const name = this.shadowRoot.querySelector('[name="name"]')?.value?.trim() || '';
        const language = this.shadowRoot.querySelector('[name="language"]')?.value || 'python';

        const config = {
            type: 'code',
            language: language,
        };

        if (name) {
            config.name = name;
        }

        if (this.codeMode === 'TOOL_ID') {
            const toolId = this.shadowRoot.querySelector('[name="tool_id"]')?.value?.trim();
            if (!toolId) {
                throw new Error(this.i18n.t('node_modal.code.err_tool_id'));
            }
            config.tool_id = toolId;
        } else if (this.codeMode === 'CODE_REFERENCE') {
            const functionPath = this.shadowRoot.querySelector('[name="function_path"]')?.value?.trim();
            if (!functionPath) {
                throw new Error(this.i18n.t('node_modal.code.err_function_path'));
            }
            config.function = functionPath;
        } else {
            const codeEditor = this.shadowRoot.querySelector('python-code-editor');
            const code = codeEditor?.getValue()?.trim();
            if (!code) {
                throw new Error(this.i18n.t('node_modal.code.err_code'));
            }
            config.code = code;
        }

        if (this.codeMode === 'INLINE_CODE') {
            const psEditor = this.shadowRoot.querySelector('json-field-editor[name="parameters_schema"]');
            if (psEditor && psEditor.isValid()) {
                const ps = psEditor.getParsedValue();
                if (ps && typeof ps === 'object' && Object.keys(ps).length > 0) {
                    if (!isValidLlmParametersSchema(ps)) {
                        throw new Error(this.i18n.t('node_modal.code.err_parameters_schema_invalid'));
                    }
                    config.parameters_schema = ps;
                }
            }
        }

        return this._applyStateSettings(config);
    }

    _renderInlineCodeMain(config) {
        const pane = this._codeMainPane;
        return html`
            <div class="code-schema-shell">
                <div class="code-schema-header">
                    <span class="code-schema-header-title">
                        ${this.i18n.t('code_node_editor.editor_section_title')}
                    </span>
                    <div class="code-schema-header-actions">
                        <button
                            type="button"
                            class="editor-btn ${pane === 'code' ? 'active' : ''}"
                            @click=${() => {
                                this._codeMainPane = 'code';
                            }}
                        >
                            <platform-icon name="code" size="14"></platform-icon>
                            ${this.i18n.t('code_node_editor.pane_code')}
                        </button>
                        <button
                            type="button"
                            class="editor-btn ${pane === 'schema' ? 'active' : ''}"
                            @click=${() => {
                                this._codeMainPane = 'schema';
                            }}
                        >
                            <platform-icon name="schema" size="14"></platform-icon>
                            ${this.i18n.t('code_node_editor.pane_schema')}
                        </button>
                    </div>
                </div>
                <div style=${pane === 'code' ? '' : 'display:none'}>
                    <python-code-editor
                        .value=${config.code || ''}
                        min-height="300"
                    ></python-code-editor>
                </div>
                <div style=${pane === 'schema' ? '' : 'display:none'}>
                    <json-field-editor
                        name="parameters_schema"
                        .value=${this._parametersSchemaEditorValue()}
                        min-height="280"
                        hint=${this.i18n.t('code_node_editor.parameters_schema_hint')}
                    ></json-field-editor>
                </div>
            </div>
        `;
    }

    renderBody() {
        const config = this.nodeConfig;

        return html`
            <div class="form-layout">
                <div class="form-sidebar">
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.common.node_id_label')}</label>
                        <input
                            type="text"
                            name="node_id"
                            class="form-input ${this.isEdit ? 'readonly' : ''}"
                            .value=${this.nodeId || ''}
                            ?readonly=${this.isEdit}
                            placeholder="my_code_node"
                            required
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.common.field_name')}</label>
                        <input
                            type="text"
                            name="name"
                            class="form-input"
                            .value=${config.name || ''}
                            placeholder=${this.i18n.t('node_modal.code.placeholder_name')}
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.code.field_language')}</label>
                        <select name="language" class="form-input">
                            <option value="python" ?selected=${this.language === 'python'}>Python</option>
                            <option value="javascript" ?selected=${this.language === 'javascript'}>JavaScript</option>
                            <option value="go" ?selected=${this.language === 'go'}>Go</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('node_modal.code.field_mode')}</label>
                        <div class="code-mode-toggle">
                            <button
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'INLINE_CODE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('INLINE_CODE')}
                            >
                                ${this.i18n.t('node_modal.code.mode_inline')}
                            </button>
                            <button
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'CODE_REFERENCE' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('CODE_REFERENCE')}
                            >
                                ${this.i18n.t('node_modal.code.mode_path')}
                            </button>
                            <button
                                type="button"
                                class="code-mode-btn ${this.codeMode === 'TOOL_ID' ? 'active' : ''}"
                                @click=${() => this._onCodeModeChange('TOOL_ID')}
                            >
                                ${this.i18n.t('node_modal.code.mode_tool')}
                            </button>
                        </div>
                    </div>

                    ${this.codeMode === 'TOOL_ID'
                        ? html`
                              <div class="form-group">
                                  <label class="form-label">${this.i18n.t('node_modal.code.tool_id_label')}</label>
                                  <input
                                      type="text"
                                      name="tool_id"
                                      class="form-input"
                                      .value=${config.tool_id || ''}
                                      placeholder="calculator, weather_api"
                                  />
                                  <span class="form-hint">${this.i18n.t('node_modal.code.tool_id_hint')}</span>
                              </div>
                          `
                        : this.codeMode === 'CODE_REFERENCE'
                          ? html`
                                <div class="form-group function-path-section">
                                    <label class="form-label">${this.i18n.t(
                                        'node_modal.code.function_path_label',
                                    )}</label>
                                    <input
                                        type="text"
                                        name="function_path"
                                        class="form-input"
                                        .value=${config.function || ''}
                                        placeholder="apps.flows.bundles.example_react.functions.my_func"
                                    />
                                </div>
                            `
                          : ''}

                    <div class="help-section">
                        <h4>${this.i18n.t('node_modal.code.help_title')}</h4>
                        <ul>
                            <li>
                                <code>def execute(args, state):</code>
                                ${this.i18n.t('node_modal.code.help_after_execute')}
                            </li>
                            <li>
                                <code>def run(state):</code>
                                ${this.i18n.t('node_modal.code.help_after_run')}
                            </li>
                            <li>
                                <code>args["param"]</code>
                                ${this.i18n.t('node_modal.code.help_after_args')}
                            </li>
                            <li>
                                <code>state["response"] = "..."</code>
                                ${this.i18n.t('node_modal.code.help_after_state')}
                            </li>
                        </ul>
                    </div>

                    ${this.renderStateSettings()}
                </div>

                <div class="form-main">
                    <div class="code-section">
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label">
                                ${this.codeMode === 'TOOL_ID'
                                    ? this.i18n.t('node_modal.code.code_label_unused')
                                    : this.i18n.t('node_modal.code.code_label')}
                            </label>
                            ${this.codeMode === 'INLINE_CODE'
                                ? this._renderInlineCodeMain(config)
                                : html`
                                      <python-code-editor
                                          .value=${config.code || ''}
                                          ?readonly=${this.codeMode === 'TOOL_ID'}
                                          min-height="300"
                                      ></python-code-editor>
                                  `}
                        </div>
                    </div>

                    <test-panel
                        .inputState=${this._buildDefaultState()}
                        .defaultInputState=${this._buildDefaultState()}
                        @validate=${this._onValidate}
                        @execute=${this._onExecute}
                    ></test-panel>
                </div>
            </div>
        `;
    }
}

customElements.define('code-node-modal', CodeNodeModal);
