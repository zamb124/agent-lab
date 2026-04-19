/**
 * flows-llm-node-editor — редактор llm_node.
 *
 * Шесть секций (свёрнутые `<details>`):
 *   1. Промпт (`flows-prompt-editor` с автодополнением `@var:` по
 *      `flowVariables`).
 *   2. LLM конфигурация (`flows-llm-config-editor` поверх `cfg.llm_override`).
 *   3. Фильтр сообщений (`cfg.messages_filter`: 'all' | 'own' | string[]).
 *   4. Структурированный вывод (`cfg.structured_output` + `cfg.output_schema`).
 *   5. ReAct loop (`cfg.react`: loop_mode, max_iterations, exit_tool, strict,
 *      reminder_message); видна, только если structured_output=false.
 *   6. Инструменты (`cfg.tools: ToolReference[]`): chips + picker + create.
 *
 * Все поля — top-level свойства NodeConfig. Никаких parameters_schema/mocks
 * (их нет в модели — это поля ToolReference / get_mock_for_node).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-prompt-editor.js';
import '../editors/flows-llm-config-editor.js';
import '../editors/flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';

const REACT_LOOP_MODES = Object.freeze(['auto', 'explicit']);

export class FlowsLlmNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        _addToolMenuOpen: { state: true },
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
            summary {
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                user-select: none;
                padding: var(--space-1) 0;
            }
            .section-body {
                display: flex; flex-direction: column;
                gap: var(--space-2);
                padding-top: var(--space-2);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            select, input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            input[type="checkbox"] { width: auto; }
            .chip {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px var(--space-2);
                font-size: var(--text-sm);
                background: var(--accent-subtle); color: var(--accent);
                border-radius: var(--radius-full);
                cursor: pointer;
            }
            .chip button {
                background: none; border: none; padding: 0; margin: 0;
                color: var(--accent); cursor: pointer;
                font-size: var(--text-base); line-height: 1;
            }
            .add-tools { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .menu {
                position: relative; display: inline-block;
            }
            .menu-list {
                position: absolute; top: 100%; left: 0; margin-top: 4px;
                z-index: var(--z-dropdown);
                min-width: 180px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-medium);
                padding: var(--space-1);
            }
            .menu-item {
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
                border-radius: var(--radius-sm);
            }
            .menu-item:hover { background: var(--glass-solid-medium); }
            .filter-list {
                display: flex; flex-direction: column; gap: var(--space-1);
                max-height: 180px; overflow-y: auto;
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .filter-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'llm_node';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this._addToolMenuOpen = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onPromptChange(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
        this._emitPatch({ prompt: value });
    }

    _onLlmConfigChange(e) {
        const cfg = e.detail?.config && typeof e.detail.config === 'object' ? e.detail.config : null;
        if (cfg === null) return;
        const isEmpty = Object.keys(cfg).length === 0;
        this._emitPatch({ llm_override: isEmpty ? null : cfg });
    }

    _filterMode() {
        const f = this.nodeConfig?.messages_filter;
        if (Array.isArray(f)) return 'custom';
        if (f === 'own') return 'own';
        return 'all';
    }

    _onFilterMode(mode) {
        if (mode === 'all' || mode === 'own') {
            this._emitPatch({ messages_filter: mode });
            return;
        }
        const current = Array.isArray(this.nodeConfig?.messages_filter) ? this.nodeConfig.messages_filter : [];
        this._emitPatch({ messages_filter: current.length > 0 ? current : [this.nodeId] });
    }

    _onFilterToggle(nodeId) {
        const current = Array.isArray(this.nodeConfig?.messages_filter) ? this.nodeConfig.messages_filter : [];
        const next = current.includes(nodeId)
            ? current.filter((id) => id !== nodeId)
            : [...current, nodeId];
        if (next.length === 0) {
            this._emitPatch({ messages_filter: 'all' });
            return;
        }
        this._emitPatch({ messages_filter: next });
    }

    _onStructuredToggle(e) {
        this._emitPatch({ structured_output: Boolean(e.target.checked) });
    }

    _onOutputSchemaChange(e) {
        if (!e.detail || !('parsed' in e.detail)) return;
        this._emitPatch({ output_schema: e.detail.parsed });
    }

    _reactPatch(patch) {
        const current = this.nodeConfig?.react && typeof this.nodeConfig.react === 'object' ? this.nodeConfig.react : {};
        const next = { ...current, ...patch };
        this._emitPatch({ react: next });
    }

    _onReactLoopMode(e) {
        this._reactPatch({ loop_mode: e.target.value });
    }

    _onReactMaxIter(e) {
        const n = parseInt(e.target.value, 10);
        if (!Number.isFinite(n)) return;
        this._reactPatch({ max_iterations: n });
    }

    _onReactExitTool(e) {
        this._reactPatch({ exit_tool: e.target.value });
    }

    _onReactStrict(e) {
        this._reactPatch({ strict: Boolean(e.target.checked) });
    }

    _onReactReminder(e) {
        this._reactPatch({ reminder_message: e.target.value });
    }

    _onPickTool() {
        this.openModal('flows.tool_picker', {
            onPick: (toolId) => {
                const tools = Array.isArray(this.nodeConfig?.tools) ? [...this.nodeConfig.tools] : [];
                if (tools.some((t) => t && t.tool_id === toolId)) return;
                tools.push({ tool_id: toolId });
                this._emitPatch({ tools });
            },
        });
    }

    _openCreateTool(kind) {
        this._addToolMenuOpen = false;
        this.openModal('flows.tool_create', {
            kind,
            onCreated: (toolRef) => {
                if (!toolRef || typeof toolRef.tool_id !== 'string') return;
                const tools = Array.isArray(this.nodeConfig?.tools) ? [...this.nodeConfig.tools] : [];
                tools.push(toolRef);
                this._emitPatch({ tools });
            },
        });
    }

    _onEditTool(toolRef) {
        this.openModal('flows.tool_create', {
            mode: 'edit',
            tool: toolRef,
            onUpdated: (updated) => {
                if (!updated || typeof updated.tool_id !== 'string') return;
                const tools = Array.isArray(this.nodeConfig?.tools) ? [...this.nodeConfig.tools] : [];
                const next = tools.map((t) => (t && t.tool_id === updated.tool_id ? updated : t));
                this._emitPatch({ tools: next });
            },
        });
    }

    _onRemoveTool(toolId) {
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        const next = tools.filter((t) => t && t.tool_id !== toolId);
        this._emitPatch({ tools: next });
    }

    _toolLabel(t) {
        if (!t) return '';
        return t.name || t.title || t.tool_id;
    }

    _renderPromptSection() {
        const prompt = typeof this.nodeConfig?.prompt === 'string' ? this.nodeConfig.prompt : '';
        return html`
            <details open>
                <summary>${this.t('llm_node_editor.section_prompt')}</summary>
                <div class="section-body">
                    <flows-prompt-editor
                        .value=${prompt}
                        .flowVariables=${this.flowVariables}
                        @change=${this._onPromptChange}
                    ></flows-prompt-editor>
                </div>
            </details>
        `;
    }

    _renderLlmSection() {
        const llm = this.nodeConfig?.llm_override || this.nodeConfig?.llm || {};
        return html`
            <details>
                <summary>${this.t('llm_node_editor.section_llm')}</summary>
                <div class="section-body">
                    <flows-llm-config-editor
                        .config=${llm}
                        @change=${this._onLlmConfigChange}
                    ></flows-llm-config-editor>
                </div>
            </details>
        `;
    }

    _renderMessagesFilterSection() {
        const mode = this._filterMode();
        const customList = Array.isArray(this.nodeConfig?.messages_filter) ? this.nodeConfig.messages_filter : [];
        const nodes = Array.isArray(this.graphNodes) ? this.graphNodes : [];
        return html`
            <details>
                <summary>${this.t('llm_node_editor.section_messages_filter')}</summary>
                <div class="section-body">
                    <div class="row">
                        <label class="filter-row">
                            <input type="radio" name="filter-${this.nodeId}" ?checked=${mode === 'all'}
                                @change=${() => this._onFilterMode('all')} />
                            ${this.t('llm_node_editor.messages_filter_all')}
                        </label>
                        <label class="filter-row">
                            <input type="radio" name="filter-${this.nodeId}" ?checked=${mode === 'own'}
                                @change=${() => this._onFilterMode('own')} />
                            ${this.t('llm_node_editor.messages_filter_own')}
                        </label>
                        <label class="filter-row">
                            <input type="radio" name="filter-${this.nodeId}" ?checked=${mode === 'custom'}
                                @change=${() => this._onFilterMode('custom')} />
                            ${this.t('llm_node_editor.messages_filter_custom')}
                        </label>
                    </div>
                    ${mode === 'custom' ? html`
                        <div class="filter-list">
                            ${nodes.map((n) => html`
                                <label class="filter-row">
                                    <input type="checkbox"
                                        ?checked=${customList.includes(n.id)}
                                        @change=${() => this._onFilterToggle(n.id)} />
                                    <span>${n.name}</span>
                                    <span style="color:var(--text-tertiary);font-size:var(--text-xs)">${n.id}</span>
                                </label>
                            `)}
                        </div>
                    ` : ''}
                </div>
            </details>
        `;
    }

    _renderStructuredSection() {
        const enabled = Boolean(this.nodeConfig?.structured_output);
        const schema = this.nodeConfig?.output_schema && typeof this.nodeConfig.output_schema === 'object'
            ? JSON.stringify(this.nodeConfig.output_schema, null, 2)
            : '{}';
        return html`
            <details>
                <summary>${this.t('llm_node_editor.section_structured')}</summary>
                <div class="section-body">
                    <label class="filter-row">
                        <input type="checkbox" .checked=${enabled} @change=${this._onStructuredToggle} />
                        ${this.t('llm_node_editor.structured_output')}
                    </label>
                    ${enabled ? html`
                        <div class="field">
                            <label>${this.t('llm_node_editor.output_schema')}</label>
                            <flows-json-field-editor
                                .value=${schema}
                                @change=${this._onOutputSchemaChange}
                            ></flows-json-field-editor>
                        </div>
                    ` : ''}
                </div>
            </details>
        `;
    }

    _renderReactSection() {
        if (this.nodeConfig?.structured_output) return '';
        const react = this.nodeConfig?.react && typeof this.nodeConfig.react === 'object' ? this.nodeConfig.react : {};
        const loopMode = react.loop_mode === 'explicit' ? 'explicit' : 'auto';
        const maxIter = typeof react.max_iterations === 'number' ? react.max_iterations : 10;
        const exitTool = typeof react.exit_tool === 'string' ? react.exit_tool : 'finish';
        const strict = react.strict === undefined ? true : Boolean(react.strict);
        const reminder = typeof react.reminder_message === 'string' ? react.reminder_message : '';
        return html`
            <details>
                <summary>${this.t('llm_node_editor.section_react')}</summary>
                <div class="section-body">
                    <div class="field">
                        <label>${this.t('llm_node_editor.react_loop_mode')}</label>
                        <select .value=${loopMode} @change=${this._onReactLoopMode}>
                            ${REACT_LOOP_MODES.map((m) => html`<option value=${m} ?selected=${m === loopMode}>${m}</option>`)}
                        </select>
                    </div>
                    <div class="field">
                        <label>${this.t('llm_node_editor.react_max_iterations')}</label>
                        <input type="number" min="1" step="1" .value=${String(maxIter)} @input=${this._onReactMaxIter} />
                    </div>
                    ${loopMode === 'explicit' ? html`
                        <div class="field">
                            <label>${this.t('llm_node_editor.react_exit_tool')}</label>
                            <input type="text" .value=${exitTool} @input=${this._onReactExitTool} />
                        </div>
                        <label class="filter-row">
                            <input type="checkbox" .checked=${strict} @change=${this._onReactStrict} />
                            ${this.t('llm_node_editor.react_strict')}
                        </label>
                        <div class="field">
                            <label>${this.t('llm_node_editor.react_reminder')}</label>
                            <input type="text" .value=${reminder} @input=${this._onReactReminder} />
                        </div>
                    ` : ''}
                </div>
            </details>
        `;
    }

    _renderToolsSection() {
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        return html`
            <details>
                <summary>${this.t('llm_node_editor.section_tools')}</summary>
                <div class="section-body">
                    <div class="row">
                        ${tools.map((t) => html`
                            <span class="chip" @click=${() => this._onEditTool(t)}>
                                ${this._toolLabel(t)}
                                <button type="button" @click=${(e) => { e.stopPropagation(); this._onRemoveTool(t.tool_id); }}>×</button>
                            </span>
                        `)}
                    </div>
                    <div class="add-tools">
                        <glass-button size="sm" variant="secondary" @click=${this._onPickTool}>
                            <platform-icon name="plus"></platform-icon>
                            ${this.t('llm_node_editor.tools_add_library')}
                        </glass-button>
                        <div class="menu">
                            <glass-button size="sm" variant="secondary" @click=${() => { this._addToolMenuOpen = !this._addToolMenuOpen; }}>
                                <platform-icon name="plus"></platform-icon>
                                ${this.t('llm_node_editor.tools_add_create')}
                            </glass-button>
                            ${this._addToolMenuOpen ? html`
                                <div class="menu-list" @click=${(e) => e.stopPropagation()}>
                                    <div class="menu-item" @click=${() => this._openCreateTool('code')}>${this.t('llm_node_editor.tools_create_code')}</div>
                                    <div class="menu-item" @click=${() => this._openCreateTool('llm')}>${this.t('llm_node_editor.tools_create_llm')}</div>
                                    <div class="menu-item" @click=${() => this._openCreateTool('api')}>${this.t('llm_node_editor.tools_create_api')}</div>
                                    <div class="menu-item" @click=${() => this._openCreateTool('subflow')}>${this.t('llm_node_editor.tools_create_subflow')}</div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </details>
        `;
    }

    render() {
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${this.nodeType || 'llm_node'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                @change=${(e) => this.emit('change', e.detail)}
                @rename-node=${(e) => this.emit('rename-node', e.detail)}
                @delete-node=${(e) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e) => this.emit('duplicate-node', e.detail)}
            >
                <div slot="settings">
                    ${this._renderPromptSection()}
                    ${this._renderLlmSection()}
                    ${this._renderMessagesFilterSection()}
                    ${this._renderStructuredSection()}
                    ${this._renderReactSection()}
                    ${this._renderToolsSection()}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-llm-node-editor', FlowsLlmNodeEditor);
