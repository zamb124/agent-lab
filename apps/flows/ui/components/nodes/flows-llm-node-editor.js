/**
 * flows-llm-node-editor — редактор llm_node.
 *
 * Содержит:
 *   - <flows-llm-config-editor> для provider/model/temperature/max_tokens;
 *   - prompt template (multi-line input);
 *   - <flows-llm-mocks-editor>;
 *   - список tools (chips) — открытие picker через openModal('flows.tool_picker');
 *   - parameters_schema через <flows-code-editor language='json'>.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-llm-config-editor.js';
import '../editors/flows-llm-mocks-editor.js';
import '../editors/flows-code-editor.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsLlmNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        _hydrated: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field textarea {
                padding: var(--space-2);
                min-height: 96px; resize: vertical;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .tools-row {
                display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center;
            }
            .tool-chip {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px 6px; font-size: var(--text-xs);
                background: var(--accent-subtle); color: var(--accent);
                border-radius: var(--radius-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this._hydrated = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onConfigChange(field, value) {
        const nextConfig = { ...(this.nodeConfig?.config || {}), [field]: value };
        this._emitPatch({ config: nextConfig });
    }

    _onPickTool() {
        this.openModal('flows.tool_picker', {
            onPick: (toolId) => {
                const tools = Array.isArray(this.nodeConfig?.config?.tools)
                    ? [...this.nodeConfig.config.tools]
                    : [];
                if (!tools.includes(toolId)) tools.push(toolId);
                this._onConfigChange('tools', tools);
            },
        });
    }

    _removeTool(toolId) {
        const tools = (this.nodeConfig?.config?.tools || []).filter((t) => t !== toolId);
        this._onConfigChange('tools', tools);
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        const tools = Array.isArray(cfg.tools) ? cfg.tools : [];
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'llm_node'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <flows-llm-config-editor
                        .config=${cfg}
                        @change=${(e) => {
                            const c = e.detail?.config || {};
                            this._emitPatch({ config: { ...cfg, ...c } });
                        }}
                    ></flows-llm-config-editor>
                    <div class="field">
                        <label>${this.t('llm_node_editor.field_prompt')}</label>
                        <textarea
                            .value=${cfg.prompt || ''}
                            @input=${(e) => this._onConfigChange('prompt', e.target.value)}
                        ></textarea>
                    </div>
                    <div class="field">
                        <label>${this.t('llm_node_editor.field_tools')}</label>
                        <div class="tools-row">
                            ${tools.map((tid) => html`
                                <span class="tool-chip">
                                    ${tid}
                                    <button type="button" @click=${() => this._removeTool(tid)}>×</button>
                                </span>
                            `)}
                            <platform-button @click=${this._onPickTool}>
                                <platform-icon name="plus" size="14"></platform-icon>
                                ${this.t('llm_node_editor.action_add_tool')}
                            </platform-button>
                        </div>
                    </div>
                    <div class="field">
                        <label>${this.t('llm_node_editor.field_parameters_schema')}</label>
                        <flows-code-editor
                            language="json"
                            .value=${JSON.stringify(cfg.parameters_schema || {}, null, 2)}
                            @change=${(e) => {
                                const v = e.detail?.value || '{}';
                                try {
                                    const parsed = JSON.parse(v);
                                    this._onConfigChange('parameters_schema', parsed);
                                } catch {
                                    // невалидный JSON — игнорируем (юзер дописывает)
                                }
                            }}
                        ></flows-code-editor>
                    </div>
                    <div class="field">
                        <label>${this.t('llm_node_editor.field_mocks')}</label>
                        <flows-llm-mocks-editor
                            .mocks=${cfg.mocks || []}
                            @change=${(e) => this._onConfigChange('mocks', e.detail?.mocks || [])}
                        ></flows-llm-mocks-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-llm-node-editor', FlowsLlmNodeEditor);
