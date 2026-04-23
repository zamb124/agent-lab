/**
 * flows-code-node-editor — редактор code-ноды.
 *
 * Поля: `code`, `args_schema` (NodeConfig / CodeNode).
 * Вкладки «Код» / «Схема» — одинаковая шапка `flows-code-editor` (slot toolbar-start + Save / Fullscreen).
 * Если в данных был только `tool_id` без `code`, при открытии подставляется исходник из реестра, `tool_id` сбрасывается.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asString } from '../../_helpers/flows-resolvers.js';

export class FlowsCodeNodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
        _mainTab: { state: true },
        _schemaInvalid: { state: true },
        _schemaError: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
                min-height: 0;
            }
            .settings-wrap {
                display: flex;
                flex-direction: column;
                gap: 0;
            }
            .toolbar-start-wrap {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
                box-sizing: border-box;
            }
            .main-tabs {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
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
        this.expanded = false;
        this.embedded = false;
        this._mainTab = 'code';
        this._schemaInvalid = false;
        this._schemaError = '';
        this._toolSource = this.useOp('flows/code_tool_source');
        this._hydrateKey = '';
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('nodeId')) {
            this._mainTab = 'code';
            this._hydrateKey = '';
            this._schemaInvalid = false;
            this._schemaError = '';
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('nodeConfig') || changed.has('nodeId')) {
            void this._maybeHydrateCodeFromTool();
        }
    }

    async _maybeHydrateCodeFromTool() {
        const cfg = this.nodeConfig;
        if (!cfg || typeof cfg !== 'object') {
            return;
        }
        const tid = cfg.tool_id;
        const c = typeof cfg.code === 'string' ? cfg.code : '';
        if (typeof tid !== 'string' || tid.length === 0) {
            return;
        }
        if (c.trim().length > 0) {
            return;
        }
        const key = `${asString(this.nodeId)}:${tid}`;
        if (this._hydrateKey === key) {
            return;
        }
        this._hydrateKey = key;
        const result = await this._toolSource.run({ tool_path: tid });
        const source = result && typeof result === 'object' && result !== null && 'source' in result
            ? asString(result.source)
            : '';
        if (source.length > 0) {
            this._emitPatch({ code: source, tool_id: null });
        }
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onCodeChange(e) {
        this._emitPatch({ code: asString(e.detail?.value), tool_id: null });
    }

    _onSchemaEditorChange(e) {
        const value = asString(e.detail?.value);
        try {
            const parsed = value.trim().length === 0 ? null : JSON.parse(value);
            this._schemaInvalid = false;
            this._schemaError = '';
            this._emitPatch({ args_schema: parsed });
        } catch (err) {
            this._schemaInvalid = true;
            this._schemaError = err.message;
        }
    }

    _openDocs() {
        this.openModal('flows.code_docs', { language: 'python' });
    }

    _renderToolbarStart() {
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
                        ?active=${this._mainTab === 'schema'}
                        @click=${() => { this._mainTab = 'schema'; }}
                    >
                        ${this.t('code_node_editor.tab_schema')}
                    </button>
                </div>
                <glass-button size="sm" variant="ghost" @click=${this._openDocs}>
                    <platform-icon name="info"></platform-icon>
                    ${this.t('code_node_editor.docs')}
                </glass-button>
            </div>
        `;
    }

    render() {
        const code = typeof this.nodeConfig?.code === 'string' ? this.nodeConfig.code : '';
        const argsSchema = this.nodeConfig?.args_schema && typeof this.nodeConfig.args_schema === 'object'
            ? this.nodeConfig.args_schema
            : {};
        const schemaText = JSON.stringify(argsSchema, null, 2);
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'code'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="settings-wrap">
                    ${this._mainTab === 'code' ? html`
                        <flows-code-editor
                            language="python"
                            .value=${code}
                            @change=${this._onCodeChange}
                        >
                            <div slot="toolbar-start">${this._renderToolbarStart()}</div>
                        </flows-code-editor>
                    ` : html`
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
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-code-node-editor', FlowsCodeNodeEditor);
