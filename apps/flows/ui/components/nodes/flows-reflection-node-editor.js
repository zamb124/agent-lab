import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '../editors/flows-llm-config-editor.js';
import '../editors/flows-json-field-editor.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';

const REFLECTION_GATES = Object.freeze(['final_answer', 'transaction', 'quality']);
const REFLECTION_TARGET_KINDS = Object.freeze(['response', 'result', 'validation', 'state_path']);
const CRITIC_SEVERITIES = Object.freeze(['info', 'warning', 'error', 'critical']);

export class FlowsReflectionNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; container-type: inline-size; }
            .stack { display: flex; flex-direction: column; gap: var(--space-5); }
            .block { display: flex; flex-direction: column; gap: var(--space-2); }
            .block-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin: 0;
            }
            .block-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-3);
                min-width: 0;
            }
            @container (max-width: 560px) {
                .grid { grid-template-columns: minmax(0, 1fr); }
            }
            .full { grid-column: 1 / -1; }
            .field { min-width: 0; }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'reflection';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.expanded = false;
        this.embedded = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _llmForEditor() {
        const cfg = asObject(this.nodeConfig);
        if (!isPlainObject(cfg.llm)) {
            throw new Error('flows-reflection-node-editor: llm config is required');
        }
        return cfg.llm;
    }

    _policyForEditor() {
        const cfg = asObject(this.nodeConfig);
        if (!isPlainObject(cfg.critic_policy)) {
            throw new Error('flows-reflection-node-editor: critic_policy is required');
        }
        return cfg.critic_policy;
    }

    _enumValues(values, prefix) {
        return values.map((value) => ({
            value,
            label: this.t(`${prefix}.${value}`),
        }));
    }

    _emitPolicyPatch(patch) {
        const policy = this._policyForEditor();
        this._emitPatch({ critic_policy: { ...policy, ...patch } });
    }

    _requiredEnum(value, values, ctx) {
        if (typeof value === 'string' && values.includes(value)) {
            return value;
        }
        throw new Error(`flows-reflection-node-editor: ${ctx} is invalid`);
    }

    _requiredNumber(value, ctx) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value;
        }
        throw new Error(`flows-reflection-node-editor: ${ctx} is required`);
    }

    _requiredArray(value, ctx) {
        if (Array.isArray(value)) {
            return value;
        }
        throw new Error(`flows-reflection-node-editor: ${ctx} is required`);
    }

    _onLlmConfigChange(e) {
        const cfg = e.detail?.config;
        if (!isPlainObject(cfg)) {
            throw new Error('flows-reflection-node-editor: llm config object required');
        }
        const next = { ...cfg };
        delete next.fallback_models;
        delete next.llm_resource_key;
        this._emitPatch({ llm: Object.keys(next).length === 0 ? null : next });
    }

    _onPolicyId(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
        this._emitPolicyPatch({ policy_id: value });
    }

    _onGate(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
        if (!REFLECTION_GATES.includes(value)) {
            throw new Error('flows-reflection-node-editor: invalid gate');
        }
        this._emitPolicyPatch({ gate: value });
    }

    _onTargetKind(e) {
        const kind = typeof e.detail?.value === 'string' ? e.detail.value : '';
        if (!REFLECTION_TARGET_KINDS.includes(kind)) {
            throw new Error('flows-reflection-node-editor: invalid target kind');
        }
        const current = asObject(this._policyForEditor().target);
        const statePath = typeof current.state_path === 'string' ? current.state_path : '';
        const target = kind === 'state_path'
            ? { kind, state_path: statePath }
            : { kind };
        this._emitPolicyPatch({ target });
    }

    _onStatePath(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
        this._emitPolicyPatch({ target: { kind: 'state_path', state_path: value } });
    }

    _onInstruction(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
        this._emitPolicyPatch({ instruction: value });
    }

    _onMinConfidence(e) {
        const raw = e.detail?.value;
        const value = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(value) || value < 0 || value > 1) {
            throw new Error('flows-reflection-node-editor: min_confidence must be between 0 and 1');
        }
        this._emitPolicyPatch({ min_confidence: value });
    }

    _onBlockSeverities(e) {
        const value = e.detail?.value;
        if (!Array.isArray(value)) {
            throw new Error('flows-reflection-node-editor: block_on_severities array required');
        }
        for (const item of value) {
            if (!CRITIC_SEVERITIES.includes(item)) {
                throw new Error('flows-reflection-node-editor: invalid severity');
            }
        }
        this._emitPolicyPatch({ block_on_severities: value });
    }

    _onCriteriaJson(e) {
        const parsed = e.detail?.parsed;
        if (!Array.isArray(parsed)) {
            throw new Error('flows-reflection-node-editor: criteria must be an array');
        }
        for (const item of parsed) {
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: criterion object required');
            }
            if (typeof item.criterion_id !== 'string' || item.criterion_id.length === 0) {
                throw new Error('flows-reflection-node-editor: criterion_id required');
            }
            if (typeof item.description !== 'string' || item.description.length === 0) {
                throw new Error('flows-reflection-node-editor: criterion description required');
            }
            if (!CRITIC_SEVERITIES.includes(item.severity)) {
                throw new Error('flows-reflection-node-editor: criterion severity invalid');
            }
        }
        this._emitPolicyPatch({ criteria: parsed });
    }

    _renderLlmSection() {
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_llm')}</h4>
                <div class="block-card">
                    <flows-llm-config-editor
                        .config=${this._llmForEditor()}
                        .allowFallbacks=${false}
                        @change=${this._onLlmConfigChange}
                    ></flows-llm-config-editor>
                </div>
            </section>
        `;
    }

    _renderPolicySection() {
        const policy = this._policyForEditor();
        const target = asObject(policy.target);
        const targetKind = this._requiredEnum(target.kind, REFLECTION_TARGET_KINDS, 'target.kind');
        const statePath = typeof target.state_path === 'string' ? target.state_path : '';
        const gate = this._requiredEnum(policy.gate, REFLECTION_GATES, 'gate');
        const minConfidence = this._requiredNumber(policy.min_confidence, 'min_confidence');
        const criteria = this._requiredArray(policy.criteria, 'criteria');
        const blockOn = this._requiredArray(policy.block_on_severities, 'block_on_severities');
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_policy')}</h4>
                <div class="block-card">
                    <div class="grid">
                        <platform-field
                            class="field"
                            type="string"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.policy_id')}
                            .value=${typeof policy.policy_id === 'string' ? policy.policy_id : ''}
                            @change=${this._onPolicyId}
                        ></platform-field>
                        <platform-field
                            class="field"
                            type="enum"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.gate')}
                            .value=${gate}
                            .config=${{ values: this._enumValues(REFLECTION_GATES, 'reflection_node_editor.gates') }}
                            @change=${this._onGate}
                        ></platform-field>
                        <platform-field
                            class="field"
                            type="enum"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.target_kind')}
                            .value=${targetKind}
                            .config=${{ values: this._enumValues(REFLECTION_TARGET_KINDS, 'reflection_node_editor.targets') }}
                            @change=${this._onTargetKind}
                        ></platform-field>
                        <platform-field
                            class="field"
                            type="number"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.min_confidence')}
                            .value=${minConfidence}
                            @change=${this._onMinConfidence}
                        ></platform-field>
                        ${targetKind === 'state_path' ? html`
                            <platform-field
                                class="field full"
                                type="string"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.state_path')}
                                .value=${statePath}
                                @change=${this._onStatePath}
                            ></platform-field>
                        ` : ''}
                        <platform-field
                            class="field full"
                            type="array"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.block_on_severities')}
                            .value=${blockOn}
                            .config=${{ allowed_values: CRITIC_SEVERITIES }}
                            @change=${this._onBlockSeverities}
                        ></platform-field>
                        <platform-field
                            class="field full"
                            type="text"
                            mode="edit"
                            .label=${this.t('reflection_node_editor.instruction')}
                            .value=${typeof policy.instruction === 'string' ? policy.instruction : ''}
                            @change=${this._onInstruction}
                        ></platform-field>
                    </div>
                    <flows-json-field-editor
                        .value=${JSON.stringify(criteria, null, 2)}
                        @change=${this._onCriteriaJson}
                    >
                        <span slot="toolbar-start">${this.t('reflection_node_editor.criteria')}</span>
                    </flows-json-field-editor>
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
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'reflection'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="stack">
                    ${this._renderLlmSection()}
                    ${this._renderPolicySection()}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-reflection-node-editor', FlowsReflectionNodeEditor);
