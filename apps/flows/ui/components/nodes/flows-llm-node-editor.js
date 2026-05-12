/**
 * flows-llm-node-editor — редактор llm_node.
 *
 * Секции стеком:
 *   1. Промпт (core `<prompt-editor>` с подсветкой `{var}`, `{?opt}`,
 *      `{var|default}`, `{for ... endfor}`, `@var:`, `@state:`, hover-tooltip
 *      со значением переменной из `flowVariables`, автокомплитом по `{` и
 *      `@var:`, режимами Preview / Split / Fullscreen).
 *   2. LLM (`flows-llm-config-editor`): база — `llm_resource_key` в сайдбаре «Закреплённые ресурсы»;
 *      при заданном ключе форма только для чтения и показывает слитый конфиг ресурса ветки/каталога.
 *   3. Фильтр сообщений (`cfg.messages_filter`: 'all' | 'own' | string[]).
 *   4. Режим вывода — toggle Tools / Structured Output (`cfg.structured_output`).
 *   5a. Tools-режим (`structured_output=false`):
 *       - ReAct loop (`cfg.react`: loop_mode + max_iterations в одной строке;
 *         при explicit — exit_tool как enum (`finish` + tools ноды, имена совпадают
 *         с LLM-calling именем `sanitize(tool_id)` как в backend) + strict; reminder_message);
 *       - Инструменты (`cfg.tools: ToolReference[]`): chips (иконка + имя) + выбор из библиотеки.
 *   5b. Structured-режим (`structured_output=true`):
 *       - Output JSON Schema (`cfg.output_schema`): при первом включении подставляется
 *         учебный strict-шаблон; пустой конфиг показывает тот же шаблон до сохранения.
 *
 * Tools и Structured Output взаимоисключающи: если включён Structured Output,
 * tools и react-секция не отображаются.
 *
 * Все поля — top-level свойства NodeConfig. Никаких parameters_schema/mocks
 * (их нет в модели — это поля ToolReference / get_mock_for_node).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import '../editors/flows-llm-config-editor.js';
import '../editors/flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { resolveResourceForPanel } from '../../_helpers/flows-branch-resource.js';
import { getNodeTypeMeta } from '../../constants/node-icons.js';
import { getToolRefVisualMeta, getToolLabel, normalizeToolRef as normalizeVisualToolRef } from '../../_helpers/flows-tool-visual.js';
import { normalizeToolRef } from '../../_helpers/flows-tool-ref.js';
import { sanitizeToolName } from '@platform/lib/utils/sanitize-tool-name.js';

const REACT_LOOP_MODES = Object.freeze(['auto', 'explicit']);

const DEFAULT_STRUCTURED_OUTPUT_SCHEMA = Object.freeze({
    type: 'object',
    properties: {
        answer: {
            type: 'string',
            description: 'Final reply text for the user.',
        },
        tags: {
            type: 'array',
            items: { type: 'string' },
            description: 'Short labels classifying the reply.',
        },
        score: {
            type: 'number',
            description: 'Numeric score (e.g. confidence 0–1).',
        },
    },
    required: ['answer', 'tags', 'score'],
    additionalProperties: false,
});

function _isUnsetOutputSchema(schema) {
    if (schema == null || typeof schema !== 'object') {
        return true;
    }
    return Object.keys(schema).length === 0;
}

function _cloneDefaultStructuredOutputSchema() {
    return JSON.parse(JSON.stringify(DEFAULT_STRUCTURED_OUTPUT_SCHEMA));
}

function _toolListEntryKey(t) {
    if (typeof t === 'string') {
        return `tool:${t}`;
    }
    if (!t || typeof t !== 'object') {
        return '';
    }
    const id = t.tool_id;
    if (typeof id !== 'string' || id.length === 0) {
        return '';
    }
    if (t.type === 'flow') {
        return `flow:${id}`;
    }
    return `tool:${id}`;
}

export class FlowsLlmNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
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
            .chip .chip-label { min-width: 0; }
            .chip button {
                background: none; border: none; padding: 0; margin: 0;
                color: var(--accent); cursor: pointer;
                font-size: var(--text-base); line-height: 1;
            }
            .add-tools { display: flex; gap: var(--space-2); flex-wrap: wrap; }
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
            .react-composite-row {
                display: flex;
                flex-wrap: wrap;
                align-items: stretch;
                gap: var(--space-3);
            }
            .react-composite-row > platform-field {
                min-width: 0;
            }
            .react-field-grow {
                flex: 1 1 160px;
            }
            .react-field-tight {
                flex: 0 1 112px;
            }
            .react-exit-strict-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) auto;
                gap: var(--space-3);
                align-items: center;
            }
            .react-exit-strict-row platform-field {
                min-width: 0;
            }
            .react-exit-strict-row platform-switch {
                max-width: min(100%, 320px);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'llm_node';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._editor = this.useOp('flows/editor');
        this._resources = this.useResource('flows/resources');
        this._branchResourcesSlice = this.select((s) => {
            const bd = s.flowsEditor?.branchData;
            if (!bd || typeof bd.resources !== 'object') {
                return null;
            }
            return bd.resources;
        });
        this._pendingFromCanvas = this.select((s) => {
            const ed = s.flowsEditor;
            if (!ed || typeof ed !== 'object') {
                return { pendingNodeToolId: null, selectedNodeId: null };
            }
            const p = ed.pendingNodeToolId;
            const pendingNodeToolId = typeof p === 'string' && p.length > 0 ? p : null;
            const sid = ed.selectedNodeId;
            const selectedNodeId = typeof sid === 'string' && sid.length > 0 ? sid : null;
            return { pendingNodeToolId, selectedNodeId };
        });
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        this._consumePendingCanvasTool();
    }

    _consumePendingCanvasTool() {
        const { pendingNodeToolId, selectedNodeId } = this._pendingFromCanvas.value;
        if (pendingNodeToolId === null) return;
        if (selectedNodeId !== this.nodeId) return;
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) return;
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        let toolRef = null;
        for (const t of tools) {
            if (typeof t === 'string') {
                if (t === pendingNodeToolId) {
                    toolRef = { tool_id: t };
                    break;
                }
            } else if (t && typeof t === 'object' && t.tool_id === pendingNodeToolId) {
                toolRef = t;
                break;
            }
        }
        this._editor.clearPendingNodeTool({});
        if (toolRef !== null) {
            this._onEditTool(toolRef);
        }
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
        const key = this._currentLlmResourceKey();
        const stripped = { ...cfg };
        delete stripped.llm_resource_key;
        const merged = key.length > 0 ? { ...stripped, llm_resource_key: key } : stripped;
        const isEmpty = Object.keys(merged).length === 0;
        this._emitPatch({ llm_override: isEmpty ? null : merged });
    }

    _flowBranchResources() {
        const st = asObject(this._editor.state);
        const bd = st.branchData;
        if (!isPlainObject(bd) || !isPlainObject(bd.resources)) {
            return {};
        }
        return bd.resources;
    }

    /**
     * @param {object | null} refRaw
     * @param {{ resource_id?: string, name?: string, type?: string }[]} catalog
     */
    _branchRefIsLlm(refRaw, catalog) {
        if (!isPlainObject(refRaw)) {
            return false;
        }
        const inlineType = typeof refRaw.type === 'string' ? refRaw.type.trim() : '';
        if (inlineType === 'llm') {
            return true;
        }
        const rid = typeof refRaw.resource_id === 'string' ? refRaw.resource_id.trim() : '';
        if (rid.length === 0) {
            return false;
        }
        const def = catalog.find((r) => r && r.resource_id === rid);
        return Boolean(def && def.type === 'llm');
    }

    _currentLlmResourceKey() {
        const ov = this.nodeConfig?.llm_override;
        const lm = this.nodeConfig?.llm;
        const bag = isPlainObject(ov) ? ov : (isPlainObject(lm) ? lm : null);
        if (!isPlainObject(bag)) {
            return '';
        }
        const raw = bag.llm_resource_key;
        return typeof raw === 'string' ? raw.trim() : '';
    }

    _applyLlmResourceKeyToNode(nextKey) {
        const k = typeof nextKey === 'string' ? nextKey.trim() : '';
        if (k.length === 0) {
            throw new Error('flows-llm-node-editor: bind base resource requires non-empty resource id');
        }
        const catalog = Array.isArray(this._resources.items) ? this._resources.items : [];
        const flowRes = this._flowBranchResources();
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? { ...this.nodeConfig.resources }
            : {};
        const rawOv = this.nodeConfig?.llm_override;
        const rawLlm = this.nodeConfig?.llm;
        const ov = isPlainObject(rawOv)
            ? { ...rawOv }
            : (isPlainObject(rawLlm) ? { ...rawLlm } : {});

        if (
            Object.prototype.hasOwnProperty.call(flowRes, k)
            && this._branchRefIsLlm(flowRes[k], catalog)
        ) {
            const next = { ...resources };
            for (const [key, ref] of Object.entries(next)) {
                const rid = ref && typeof ref.resource_id === 'string' ? ref.resource_id : key;
                const d = catalog.find((r) => r && r.resource_id === rid);
                if (d && d.type === 'llm') {
                    delete next[key];
                }
            }
            ov.llm_resource_key = k;
            this._emitPatch({
                resources: next,
                llm_override: ov,
            });
            return;
        }

        const def = catalog.find((r) => r && r.resource_id === k);
        if (def && def.type === 'llm') {
            const next = { ...resources };
            for (const [key, ref] of Object.entries(next)) {
                const rid = ref && typeof ref.resource_id === 'string' ? ref.resource_id : key;
                const d = catalog.find((r) => r && r.resource_id === rid);
                if (d && d.type === 'llm') {
                    delete next[key];
                }
            }
            next[k] = { resource_id: k };
            ov.llm_resource_key = k;
            this._emitPatch({
                resources: next,
                llm_override: ov,
            });
            return;
        }

        ov.llm_resource_key = k;
        this._emitPatch({ llm_override: ov });
    }

    _legacySingleUnboundLlmResourceId() {
        const existing = this._currentLlmResourceKey();
        if (existing.length > 0) {
            return null;
        }
        const catalog = Array.isArray(this._resources.items) ? this._resources.items : [];
        const resources = this.nodeConfig?.resources && typeof this.nodeConfig.resources === 'object'
            ? this.nodeConfig.resources
            : {};
        const flowRes = this._flowBranchResources();
        /** @type {string[]} */
        const found = [];
        const seen = new Set();
        for (const [key, ref] of Object.entries(resources)) {
            const rid = ref && typeof ref.resource_id === 'string' && ref.resource_id.length > 0
                ? ref.resource_id
                : key;
            if (typeof rid !== 'string' || rid.length === 0 || seen.has(rid)) {
                continue;
            }
            let isLlm = false;
            if (Object.prototype.hasOwnProperty.call(flowRes, rid) && this._branchRefIsLlm(flowRes[rid], catalog)) {
                isLlm = true;
            } else {
                const def = catalog.find((r) => r && r.resource_id === rid);
                if (def && def.type === 'llm') {
                    isLlm = true;
                }
            }
            if (isLlm) {
                seen.add(rid);
                found.push(rid);
            }
        }
        if (found.length !== 1) {
            return null;
        }
        return found[0];
    }

    _llmConfigForEditor() {
        const cfg = asObject(this.nodeConfig);
        const override = isPlainObject(cfg.llm_override) ? cfg.llm_override : null;
        const fallback = isPlainObject(cfg.llm) ? cfg.llm : null;
        const llm = override !== null ? override : (fallback !== null ? fallback : {});
        const { llm_resource_key: _drop, ...rest } = llm;
        return rest;
    }

    _resolvedLlmConfigForPinnedResource(resourceKey) {
        if (typeof resourceKey !== 'string' || resourceKey.length === 0) {
            return {};
        }
        const state = this._editor.state;
        if (!isPlainObject(state)) {
            return {};
        }
        const items = Array.isArray(this._resources.items) ? this._resources.items : [];
        const resolved = resolveResourceForPanel(resourceKey, state, items);
        if (resolved === null) {
            return {};
        }
        const rcfg = resolved.resource?.config;
        return isPlainObject(rcfg) ? rcfg : {};
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
        if (next && _isUnsetOutputSchema(this.nodeConfig?.output_schema)) {
            this._emitPatch({
                structured_output: true,
                output_schema: _cloneDefaultStructuredOutputSchema(),
            });
            return;
        }
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
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-llm-node-editor: react.loop_mode change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-llm-node-editor: react.loop_mode detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-llm-node-editor: react.loop_mode string required');
        }
        this._reactPatch({ loop_mode: v });
    }

    _onReactMaxIter(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-llm-node-editor: react.max_iterations change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-llm-node-editor: react.max_iterations detail.value');
        }
        const v = d.value;
        if (v === null) {
            return;
        }
        if (typeof v !== 'number' || !Number.isFinite(v)) {
            throw new Error('flows-llm-node-editor: react.max_iterations number required');
        }
        this._reactPatch({ max_iterations: Math.floor(v) });
    }

    _onReactExitTool(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-llm-node-editor: react.exit_tool change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-llm-node-editor: react.exit_tool detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-llm-node-editor: react.exit_tool string required');
        }
        this._reactPatch({ exit_tool: v });
    }

    _onReactStrict(e) {
        const v = e.detail && typeof e.detail === 'object' && 'value' in e.detail ? e.detail.value : undefined;
        if (typeof v !== 'boolean') {
            throw new Error('react strict: expected platform-switch change detail.value boolean');
        }
        this._reactPatch({ strict: v });
    }

    _onReactReminder(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-llm-node-editor: react.reminder change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-llm-node-editor: react.reminder detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-llm-node-editor: react.reminder string required');
        }
        this._reactPatch({ reminder_message: v });
    }

    _onPickTool() {
        this.openModal('flows.tool_picker', {
            pickMode: 'all',
            onPick: (detail) => {
                if (!detail || typeof detail !== 'object' || typeof detail.tool_id !== 'string') {
                    return;
                }
                const toolId = detail.tool_id;
                const kind = detail.kind === 'flow' ? 'flow' : 'tool';
                const tools = Array.isArray(this.nodeConfig?.tools) ? [...this.nodeConfig.tools] : [];
                const newKey = kind === 'flow' ? `flow:${toolId}` : `tool:${toolId}`;
                if (tools.some((t) => _toolListEntryKey(t) === newKey)) {
                    return;
                }
                if (kind === 'flow') {
                    tools.push({ type: 'flow', tool_id: toolId });
                } else {
                    tools.push({ tool_id: toolId });
                }
                this._emitPatch({ tools });
            },
        });
    }

    _onEditTool(toolRef) {
        const { tool_id: toolId, raw } = normalizeToolRef(toolRef);
        const st = asObject(this._editor.state);
        const skillsData = isPlainObject(st.branchData) ? st.branchData : {};
        const graphNodes = isPlainObject(skillsData.nodes) ? skillsData.nodes : {};
        if (graphNodes[toolId] !== undefined) {
            this._editor.selectNode({ nodeId: toolId });
            return;
        }
        this.openModal('flows.embedded_tool_config', {
            toolRef: raw,
            flowId: this.flowId,
            branchId: this.branchId,
            onSave: (updated) => {
                if (updated === null || updated === undefined || typeof updated !== 'object') {
                    return;
                }
                if (typeof updated.tool_id !== 'string' || updated.tool_id.length === 0) {
                    return;
                }
                const tools = Array.isArray(this.nodeConfig?.tools) ? [...this.nodeConfig.tools] : [];
                const next = tools.map((t) => {
                    const id = typeof t === 'string' ? t : t.tool_id;
                    return id === updated.tool_id ? updated : t;
                });
                this._emitPatch({ tools: next });
            },
        });
    }

    _toolEntryId(t) {
        if (typeof t === 'string' && t.length > 0) {
            return t;
        }
        if (t && typeof t === 'object' && typeof t.tool_id === 'string' && t.tool_id.length > 0) {
            return t.tool_id;
        }
        return '';
    }

    _toolChipVisualMeta(t) {
        const ref = normalizeVisualToolRef(t);
        if (ref === null) {
            return getNodeTypeMeta('code');
        }
        return getToolRefVisualMeta(ref);
    }

    _onRemoveTool(toolId) {
        if (typeof toolId !== 'string' || toolId.length === 0) {
            throw new Error('flows-llm-node-editor: remove tool requires tool_id');
        }
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        const next = tools.filter((entry) => {
            if (typeof entry === 'string') {
                return entry !== toolId;
            }
            return entry && entry.tool_id !== toolId;
        });
        this._emitPatch({ tools: next });
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
        void this._branchResourcesSlice.value;
        const resourceKey = this._currentLlmResourceKey();
        const legacyRid = this._legacySingleUnboundLlmResourceId();
        const pinned = resourceKey.length > 0;
        const llmForEditor = pinned
            ? this._resolvedLlmConfigForPinnedResource(resourceKey)
            : this._llmConfigForEditor();
        return html`
            <section class="block">
                <h4 class="block-title">${pinned
                    ? this.t('llm_node_editor.section_llm_from_branch', { id: resourceKey })
                    : this.t('llm_node_editor.section_llm')}</h4>
                <div class="block-card">
                    ${legacyRid !== null ? html`
                        <div class="row" style="align-items:center;gap:var(--space-2);flex-wrap:wrap;">
                            <span class="block-hint">${this.t('llm_node_editor.llm_resource_legacy_hint')}</span>
                            <glass-button size="sm" variant="secondary" type="button"
                                @click=${() => this._applyLlmResourceKeyToNode(legacyRid)}>
                                ${this.t('llm_node_editor.llm_resource_legacy_bind')}
                            </glass-button>
                        </div>
                    ` : ''}
                    <flows-llm-config-editor
                        .config=${llmForEditor}
                        ?readOnly=${pinned}
                        @change=${pinned ? nothing : this._onLlmConfigChange}
                    ></flows-llm-config-editor>
                </div>
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
        const raw = this.nodeConfig?.output_schema;
        const schemaObj =
            !_isUnsetOutputSchema(raw) && typeof raw === 'object' ? raw : DEFAULT_STRUCTURED_OUTPUT_SCHEMA;
        const schema = JSON.stringify(schemaObj, null, 2);
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_output_schema')}</h4>
                <div class="block-card">
                    <div class="block-hint">${this.t('llm_node_editor.output_schema_strict_hint')}</div>
                    <flows-json-field-editor
                        .value=${schema}
                        @change=${this._onOutputSchemaChange}
                    ></flows-json-field-editor>
                </div>
            </section>
        `;
    }

    _exitToolEnumConfig(exitTool) {
        if (typeof exitTool !== 'string' || exitTool.length === 0) {
            throw new Error('flows-llm-node-editor: exit_tool string required');
        }
        const finishValue = 'finish';
        const byValue = new Map();
        byValue.set(finishValue, {
            value: finishValue,
            label: this.t('llm_node_editor.react_exit_tool_option_finish'),
        });
        const tools = Array.isArray(this.nodeConfig?.tools) ? this.nodeConfig.tools : [];
        for (const entry of tools) {
            const tid = this._toolEntryId(entry);
            if (tid.length === 0) {
                continue;
            }
            const callName = sanitizeToolName(tid);
            if (byValue.has(callName)) {
                continue;
            }
            const baseLabel = getToolLabel(entry);
            const label =
                baseLabel !== callName
                    ? `${baseLabel} (${callName})`
                    : baseLabel;
            byValue.set(callName, { value: callName, label });
        }
        if (!byValue.has(exitTool)) {
            byValue.set(exitTool, { value: exitTool, label: exitTool });
        }
        return { values: Array.from(byValue.values()) };
    }

    _renderReactSection() {
        if (this.nodeConfig?.structured_output) return '';
        const react = this.nodeConfig?.react && typeof this.nodeConfig.react === 'object' ? this.nodeConfig.react : {};
        const loopMode = react.loop_mode === 'explicit' ? 'explicit' : 'auto';
        const maxIter = typeof react.max_iterations === 'number' ? react.max_iterations : 10;
        const exitTool =
            typeof react.exit_tool === 'string' && react.exit_tool.length > 0 ? react.exit_tool : 'finish';
        const strict = react.strict === undefined ? true : Boolean(react.strict);
        const reminder = typeof react.reminder_message === 'string' ? react.reminder_message : '';
        const loopModeValues = REACT_LOOP_MODES.map((m) => ({
            value: m,
            label: m === 'explicit'
                ? this.t('llm_node_editor.react_loop_explicit')
                : this.t('llm_node_editor.react_loop_auto'),
        }));
        const exitToolEnum = loopMode === 'explicit' ? this._exitToolEnumConfig(exitTool) : null;
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('llm_node_editor.section_react')}</h4>
                <div class="block-card">
                    <div class="react-composite-row">
                        <platform-field
                            class="react-field-grow"
                            mode="edit"
                            type="enum"
                            .label=${this.t('llm_node_editor.react_loop_mode')}
                            .value=${loopMode}
                            .config=${{ values: loopModeValues }}
                            @change=${this._onReactLoopMode}
                        ></platform-field>
                        <platform-field
                            class="react-field-tight"
                            mode="edit"
                            type="integer"
                            .label=${this.t('llm_node_editor.react_max_iterations')}
                            .value=${maxIter}
                            @change=${this._onReactMaxIter}
                        ></platform-field>
                    </div>
                    ${loopMode === 'explicit' ? html`
                        <div class="react-exit-strict-row">
                            <platform-field
                                class="react-field-grow"
                                mode="edit"
                                type="enum"
                                .label=${this.t('llm_node_editor.react_exit_tool')}
                                .value=${exitTool}
                                .config=${exitToolEnum}
                                @change=${this._onReactExitTool}
                            ></platform-field>
                            <platform-switch
                                size="sm"
                                ?checked=${strict}
                                .label=${this.t('llm_node_editor.react_strict')}
                                @change=${this._onReactStrict}
                            ></platform-switch>
                        </div>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('llm_node_editor.react_reminder')}
                            .value=${reminder}
                            @change=${this._onReactReminder}
                        ></platform-field>
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
                        ${tools.map((t) => {
                            const vm = this._toolChipVisualMeta(t);
                            const tid = this._toolEntryId(t);
                            return html`
                            <span class="chip" @click=${() => this._onEditTool(t)}>
                                <platform-icon name=${vm.icon} size="14"></platform-icon>
                                <span class="chip-label">${getToolLabel(t)}</span>
                                <button type="button" @click=${(e) => { e.stopPropagation(); this._onRemoveTool(tid); }}>×</button>
                            </span>
                        `;
                        })}
                    </div>
                    <div class="add-tools">
                        <glass-button size="sm" variant="secondary" @click=${this._onPickTool}>
                            <platform-icon name="plus"></platform-icon>
                            ${this.t('llm_node_editor.tools_add_library')}
                        </glass-button>
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
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'llm_node'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
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
