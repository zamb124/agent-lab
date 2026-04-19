/**
 * flows-code-node-editor — редактор code-ноды.
 *
 * Поля точно по `NodeConfig` (apps/flows/src/models/node_config.py) и
 * `CodeNode` (apps/flows/src/runtime/nodes.py):
 *   - code (str): inline Python код
 *   - args_schema (object): схема аргументов
 *   - tool_id (str, опционально): ID code-tool из реестра (mode='function')
 *
 * Toggle inline ↔ function reference: в режиме function редактор
 * подгружает исходник через useOp('flows/code_tool_source') (read-only).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-editor.js';
import '../editors/flows-args-schema-form.js';
import '../editors/flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsCodeNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        _showSchemaJson: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            details {
                margin-bottom: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            summary { cursor: pointer; font-size: var(--text-sm); font-weight: var(--font-semibold); }
            .row { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .toggle button {
                padding: 4px 12px;
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .toggle button[active] {
                background: var(--accent-subtle); color: var(--accent);
                border-color: var(--accent-subtle);
            }
            .docs-btn { margin-left: auto; }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'code';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this._showSchemaJson = false;
        this._toolSource = this.useOp('flows/code_tool_source');
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _mode() {
        return typeof this.nodeConfig?.tool_id === 'string' && this.nodeConfig.tool_id.length > 0
            ? 'function'
            : 'inline';
    }

    _setMode(mode) {
        if (mode === 'function') {
            this._emitPatch({ tool_id: '' });
        } else {
            this._emitPatch({ tool_id: null });
        }
    }

    _onCodeChange(e) {
        this._emitPatch({ code: e.detail?.value || '' });
    }

    _onToolIdChange(e) {
        const v = e.target.value;
        this._emitPatch({ tool_id: v });
        if (v) {
            void this._toolSource.run({ tool_id: v });
        }
    }

    _onSchemaJsonChange(e) {
        if (!e.detail || !('parsed' in e.detail)) return;
        this._emitPatch({ args_schema: e.detail.parsed });
    }

    _onSchemaFormChange(e) {
        const values = e.detail?.values && typeof e.detail.values === 'object' ? e.detail.values : {};
        const merged = {};
        const current = this.nodeConfig?.args_schema && typeof this.nodeConfig.args_schema === 'object'
            ? this.nodeConfig.args_schema
            : {};
        for (const [key, def] of Object.entries(current)) {
            const defObj = def && typeof def === 'object' ? def : {};
            merged[key] = { ...defObj, default: values[key] };
        }
        this._emitPatch({ args_schema: merged });
    }

    _openDocs() {
        this.openModal('flows.code_docs', { language: 'python' });
    }

    render() {
        const mode = this._mode();
        const code = typeof this.nodeConfig?.code === 'string' ? this.nodeConfig.code : '';
        const toolId = typeof this.nodeConfig?.tool_id === 'string' ? this.nodeConfig.tool_id : '';
        const argsSchema = this.nodeConfig?.args_schema && typeof this.nodeConfig.args_schema === 'object'
            ? this.nodeConfig.args_schema
            : {};
        const argsValues = Object.fromEntries(
            Object.entries(argsSchema).map(([k, v]) => [k, v && typeof v === 'object' && 'default' in v ? v.default : undefined])
        );
        const toolSource = mode === 'function' && toolId
            ? (this._toolSource.lastResult?.code || '')
            : '';
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${this.nodeType || 'code'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                @change=${(e) => this.emit('change', e.detail)}
                @rename-node=${(e) => this.emit('rename-node', e.detail)}
                @delete-node=${(e) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings">
                    <details open>
                        <summary>${this.t('code_node_editor.section_code')}</summary>
                        <div class="row toggle">
                            <button ?active=${mode === 'inline'} @click=${() => this._setMode('inline')}>
                                ${this.t('code_node_editor.mode_inline')}
                            </button>
                            <button ?active=${mode === 'function'} @click=${() => this._setMode('function')}>
                                ${this.t('code_node_editor.mode_function')}
                            </button>
                            <glass-button class="docs-btn" size="sm" variant="ghost" @click=${this._openDocs}>
                                <platform-icon name="info"></platform-icon>
                                ${this.t('code_node_editor.docs')}
                            </glass-button>
                        </div>
                        ${mode === 'inline' ? html`
                            <flows-code-editor
                                language="python"
                                .value=${code}
                                @change=${this._onCodeChange}
                            ></flows-code-editor>
                        ` : html`
                            <div class="row">
                                <input
                                    type="text"
                                    placeholder="module.func"
                                    .value=${toolId}
                                    @input=${this._onToolIdChange}
                                />
                            </div>
                            ${toolSource ? html`
                                <flows-code-editor
                                    language="python"
                                    readonly
                                    .value=${toolSource}
                                ></flows-code-editor>
                            ` : ''}
                        `}
                    </details>
                    <details>
                        <summary>${this.t('code_node_editor.args_schema')}</summary>
                        <div class="row toggle">
                            <button ?active=${!this._showSchemaJson} @click=${() => { this._showSchemaJson = false; }}>
                                ${this.t('code_node_editor.schema_form')}
                            </button>
                            <button ?active=${this._showSchemaJson} @click=${() => { this._showSchemaJson = true; }}>
                                ${this.t('code_node_editor.schema_json')}
                            </button>
                        </div>
                        ${this._showSchemaJson ? html`
                            <flows-json-field-editor
                                .value=${JSON.stringify(argsSchema, null, 2)}
                                @change=${this._onSchemaJsonChange}
                            ></flows-json-field-editor>
                        ` : html`
                            <flows-args-schema-form
                                .schema=${argsSchema}
                                .values=${argsValues}
                                @change=${this._onSchemaFormChange}
                            ></flows-args-schema-form>
                        `}
                    </details>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-code-node-editor', FlowsCodeNodeEditor);
