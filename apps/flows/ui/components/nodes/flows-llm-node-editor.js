/**
 * flows-llm-node-editor — редактор llm_node.
 *
 * Секции стеком:
 *   1. Промпт (core `<prompt-editor>` с подсветкой `{var}`, `{?opt}`,
 *      `{var|default}`, `{for ... endfor}`, `@var:`, `@state:`, hover-tooltip
 *      со значением переменной из `flowVariables`, автокомплитом по `{` и
 *      `@var:`, режимами Preview / Split / Fullscreen).
 *   2. LLM конфигурация (`flows-llm-config-editor` поверх `cfg.llm_override`).
 *   3. Фильтр сообщений (`cfg.messages_filter`: 'all' | 'own' | string[]).
 *   4. Режим вывода — toggle Tools / Structured Output (`cfg.structured_output`).
 *   5a. Tools-режим (`structured_output=false`):
 *       - ReAct loop (`cfg.react`: loop_mode, max_iterations, exit_tool, strict,
 *         reminder_message);
 *       - Инструменты (`cfg.tools: ToolReference[]`): chips + picker + create.
 *   5b. Structured-режим (`structured_output=true`):
 *       - Output JSON Schema (`cfg.output_schema`).
 *
 * Tools и Structured Output взаимоисключающи: если включён Structured Output,
 * tools и react-секция не отображаются.
 *
 * Все поля — top-level свойства NodeConfig. Никаких parameters_schema/mocks
 * (их нет в модели — это поля ToolReference / get_mock_for_node).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import '../editors/flows-llm-config-editor.js';
import '../editors/flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';

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
        expanded: { type: Boolean, reflect: true },
        _addToolMenuOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block; height: 100%; min-height: 0;
            }
            .stack {
                display: flex; flex-direction: column;
                gap: var(--space-5);
            }
            .block { display: flex; flex-direction: column; gap: var(--space-2); }
            .block-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin: 0;
            }
            .block-card {
                display: flex; flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .block-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
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
            .toggle { display: inline-flex; gap: var(--space-1); }
            .toggle button {
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);
            }
            .toggle button[active] {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent);
            }
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
        this.expanded = false;
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

    _onOutputModeToggle(mode) {
        const next = mode === 'structured';
        const current = Boolean(this.nodeConfig?.structured_output);
        if (next === current) return;
        this._emitPatch({ structured_output: next });
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
        if (typeof t.name === 'string' && t.name.length > 0) return t.name;
        if (typeof t.title === 'string' && t.title.length > 0) return t.title;
        return t.tool_id;
    }

    _renderPromptSection() {
        const prompt = typeof this.nodeConfig?.prompt === 'string' ? this.nodeConfig.prompt : '';
        const variables = this.flowVariables && typeof this.flowVariables === 'object' ? this.flowVariables : {};
        return html`
            <prompt-editor
                .value=${prompt}
                .variables=${variables}
                label=${this.t('llm_node_editor.section_prompt')}
                @change=${this._onPromptChange}
            ></prompt-editor>
        `;
    }

    _renderLlmSection() {
        const cfg = asObject(this.nodeConfig);
        const override = isPlainObject(cfg.llm_override) ? cfg.llm_override : null;
        const fallback = isPlainObject(cfg.llm) ? cfg.llm : null;
        const llm = override !== null ? override : (fallback !== null ? fallback : {});
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_llm')}</h4>
                <flows-llm-config-editor
                    .config=${llm}
                    @change=${this._onLlmConfigChange}
                ></flows-llm-config-editor>
            </section>
        `;
    }

    _renderMessagesFilterSection() {
        const mode = this._filterMode();
        const customList = Array.isArray(this.nodeConfig?.messages_filter) ? this.nodeConfig.messages_filter : [];
        const nodes = Array.isArray(this.graphNodes) ? this.graphNodes : [];
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_messages_filter')}</h4>
                <div class="block-card">
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
            </section>
        `;
    }

    _renderOutputModeSection() {
        const structured = Boolean(this.nodeConfig?.structured_output);
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_output_mode')}</h4>
                <div class="block-card">
                    <div class="toggle">
                        <button type="button" ?active=${!structured}
                            @click=${() => this._onOutputModeToggle('tools')}>
                            ${this.t('llm_node_editor.output_mode_tools')}
                        </button>
                        <button type="button" ?active=${structured}
                            @click=${() => this._onOutputModeToggle('structured')}>
                            ${this.t('llm_node_editor.output_mode_structured')}
                        </button>
                    </div>
                    <div class="block-hint">${this.t('llm_node_editor.output_mode_hint')}</div>
                </div>
            </section>
        `;
    }

    _renderOutputSchemaSection() {
        if (!this.nodeConfig?.structured_output) return '';
        const schema = this.nodeConfig?.output_schema && typeof this.nodeConfig.output_schema === 'object'
            ? JSON.stringify(this.nodeConfig.output_schema, null, 2)
            : '{}';
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_output_schema')}</h4>
                <div class="block-card">
                    <flows-json-field-editor
                        .value=${schema}
                        @change=${this._onOutputSchemaChange}
                    ></flows-json-field-editor>
                </div>
            </section>
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
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_react')}</h4>
                <div class="block-card">
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
            </section>
        `;
    }

    _renderToolsSection() {
        if (this.nodeConfig?.structured_output) return '';
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_tools')}</h4>
                <div class="block-card">
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
            </section>
        `;
    }

    render() {
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'llm_node'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
            >
                <div slot="settings" class="stack">
                    ${this._renderPromptSection()}
                    ${this._renderLlmSection()}
                    ${this._renderMessagesFilterSection()}
                    ${this._renderOutputModeSection()}
                    ${this._renderReactSection()}
                    ${this._renderToolsSection()}
                    ${this._renderOutputSchemaSection()}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-llm-node-editor', FlowsLlmNodeEditor);
