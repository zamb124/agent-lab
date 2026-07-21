import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-picker-card.js';
import './flows-base-node-editor.js';
import '../editors/flows-llm-config-editor.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import {
    REFLECTION_GATES,
    REFLECTION_TARGET_KINDS,
    CRITIC_SEVERITIES,
    CRITIC_DECISIONS,
    REFLECTION_EXIT_WHEN_KINDS,
    REFLECTION_POLICY_PRESET_IDS,
    getReflectionPolicyPreset,
    getDefaultPassFailExits,
    newBlankCriterion,
    newBlankExit,
} from '../../_helpers/flows-reflection-defaults.js';

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
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        panelShellStyles,
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
            .block-hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.45;
            }
            .block-card {
                gap: var(--space-3);
                padding: var(--space-3);
            }
            .intro-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .intro-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .intro-body {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
            }
            .exits-editor {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .exit-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .exit-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .exit-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .exits-preview {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                margin: 0;
                padding: 0;
                list-style: none;
            }
            .exits-preview li {
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .presets {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-2);
            }
            @container (max-width: 560px) {
                .presets { grid-template-columns: minmax(0, 1fr); }
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
            .field-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }
            .severity-toggles {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
                gap: var(--space-2) var(--space-3);
                min-width: 0;
            }
            .severity-toggles .field {
                min-width: 0;
            }
            .criteria-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .criterion-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .criterion-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .criterion-index {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
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

    _onApplyPreset(presetId) {
        if (!REFLECTION_POLICY_PRESET_IDS.includes(presetId)) {
            throw new Error(`flows-reflection-node-editor: unknown preset ${presetId}`);
        }
        this._emitPatch({ critic_policy: getReflectionPolicyPreset(presetId) });
    }

    _activePresetId(policy) {
        for (const presetId of REFLECTION_POLICY_PRESET_IDS) {
            const preset = getReflectionPolicyPreset(presetId);
            if (
                policy.policy_id === preset.policy_id
                && policy.gate === preset.gate
                && isPlainObject(policy.target)
                && policy.target.kind === preset.target.kind
            ) {
                return presetId;
            }
        }
        return null;
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

    _onToggleSeverity(severity, checked) {
        if (!CRITIC_SEVERITIES.includes(severity)) {
            throw new Error('flows-reflection-node-editor: invalid severity');
        }
        const policy = this._policyForEditor();
        const current = this._requiredArray(policy.block_on_severities, 'block_on_severities');
        const next = checked
            ? [...new Set([...current, severity])]
            : current.filter((item) => item !== severity);
        if (next.length === 0) {
            throw new Error('flows-reflection-node-editor: at least one block severity required');
        }
        this._emitPolicyPatch({ block_on_severities: next });
    }

    _criteriaList() {
        return this._requiredArray(this._policyForEditor().criteria, 'criteria');
    }

    _emitCriteria(next) {
        const ids = next.map((item) => item.criterion_id);
        if (new Set(ids).size !== ids.length) {
            throw new Error('flows-reflection-node-editor: criterion_id values must be unique');
        }
        if (next.length === 0) {
            throw new Error('flows-reflection-node-editor: at least one criterion required');
        }
        this._emitPolicyPatch({ criteria: next });
    }

    _onAddCriterion() {
        this._emitCriteria([...this._criteriaList(), newBlankCriterion()]);
    }

    _onRemoveCriterion(index) {
        const criteria = this._criteriaList();
        if (criteria.length <= 1) {
            throw new Error('flows-reflection-node-editor: at least one criterion required');
        }
        this._emitCriteria(criteria.filter((_, i) => i !== index));
    }

    _onCriterionField(index, field, value) {
        const criteria = this._criteriaList().map((item, i) => {
            if (i !== index) {
                return item;
            }
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: criterion object required');
            }
            return { ...item, [field]: value };
        });
        this._emitCriteria(criteria);
    }

    _exitsList() {
        const policy = this._policyForEditor();
        if (Array.isArray(policy.exits) && policy.exits.length > 0) {
            return policy.exits;
        }
        return getDefaultPassFailExits();
    }

    _emitExits(next) {
        const ids = next.map((item) => {
            if (!isPlainObject(item) || typeof item.exit_id !== 'string') {
                throw new Error('flows-reflection-node-editor: exit object with exit_id required');
            }
            return item.exit_id;
        });
        if (new Set(ids).size !== ids.length) {
            throw new Error('flows-reflection-node-editor: exit_id values must be unique');
        }
        if (next.length === 0) {
            throw new Error('flows-reflection-node-editor: at least one exit required');
        }
        const alwaysIndexes = next
            .map((item, index) => (isPlainObject(item.when) && item.when.kind === 'always' ? index : -1))
            .filter((index) => index >= 0);
        if (alwaysIndexes.length > 1) {
            throw new Error('flows-reflection-node-editor: at most one always exit');
        }
        if (alwaysIndexes.length === 1 && alwaysIndexes[0] !== next.length - 1) {
            throw new Error('flows-reflection-node-editor: always exit must be last');
        }
        this._emitPolicyPatch({ exits: next });
    }

    _onAddExit() {
        this._emitExits([...this._exitsList(), newBlankExit()]);
    }

    _onRemoveExit(index) {
        const exits = this._exitsList();
        if (exits.length <= 1) {
            throw new Error('flows-reflection-node-editor: at least one exit required');
        }
        this._emitExits(exits.filter((_, i) => i !== index));
    }

    _onMoveExit(index, delta) {
        const exits = [...this._exitsList()];
        const target = index + delta;
        if (target < 0 || target >= exits.length) {
            return;
        }
        const tmp = exits[index];
        exits[index] = exits[target];
        exits[target] = tmp;
        this._emitExits(exits);
    }

    _onExitField(index, field, value) {
        const exits = this._exitsList().map((item, i) => {
            if (i !== index) {
                return item;
            }
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: exit object required');
            }
            return { ...item, [field]: value };
        });
        this._emitExits(exits);
    }

    _onExitWhenKind(index, kind) {
        if (!REFLECTION_EXIT_WHEN_KINDS.includes(kind)) {
            throw new Error('flows-reflection-node-editor: invalid exit when kind');
        }
        const exits = this._exitsList().map((item, i) => {
            if (i !== index) {
                return item;
            }
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: exit object required');
            }
            if (kind === 'decision_eq') {
                return { ...item, when: { kind, decision: 'needs_revision' } };
            }
            if (kind === 'blocked_reason_prefix') {
                return { ...item, when: { kind, reason_prefix: 'decision:' } };
            }
            return { ...item, when: { kind } };
        });
        this._emitExits(exits);
    }

    _onExitWhenDecision(index, decision) {
        if (!CRITIC_DECISIONS.includes(decision)) {
            throw new Error('flows-reflection-node-editor: invalid decision');
        }
        const exits = this._exitsList().map((item, i) => {
            if (i !== index) {
                return item;
            }
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: exit object required');
            }
            return { ...item, when: { kind: 'decision_eq', decision } };
        });
        this._emitExits(exits);
    }

    _onExitWhenReasonPrefix(index, reasonPrefix) {
        const exits = this._exitsList().map((item, i) => {
            if (i !== index) {
                return item;
            }
            if (!isPlainObject(item)) {
                throw new Error('flows-reflection-node-editor: exit object required');
            }
            return { ...item, when: { kind: 'blocked_reason_prefix', reason_prefix: reasonPrefix } };
        });
        this._emitExits(exits);
    }

    _renderIntro() {
        const exits = this._exitsList();
        return html`
            <section class="intro-card">
                <h4 class="intro-title">${this.t('reflection_node_editor.intro_title')}</h4>
                <p class="intro-body">${this.t('reflection_node_editor.intro_body')}</p>
                <p class="block-hint">${this.t('reflection_node_editor.exits_title')}</p>
                <ul class="exits-preview">
                    ${exits.map((item) => {
                        if (!isPlainObject(item)) {
                            throw new Error('flows-reflection-node-editor: exit object required');
                        }
                        const exitId = typeof item.exit_id === 'string' ? item.exit_id : '';
                        const label = typeof item.label === 'string' && item.label.length > 0
                            ? item.label
                            : exitId;
                        return html`<li>${label} → validation.exit_id == ${exitId}</li>`;
                    })}
                </ul>
            </section>
        `;
    }

    _renderExitsSection() {
        const exits = this._exitsList();
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_exits')}</h4>
                <p class="block-hint">${this.t('reflection_node_editor.section_exits_hint')}</p>
                <div class="block-card content-panel exits-editor">
                    ${exits.map((item, index) => {
                        if (!isPlainObject(item)) {
                            throw new Error('flows-reflection-node-editor: exit object required');
                        }
                        const exitId = typeof item.exit_id === 'string' ? item.exit_id : '';
                        const label = typeof item.label === 'string' ? item.label : '';
                        const when = asObject(item.when);
                        const whenKind = this._requiredEnum(
                            when.kind,
                            REFLECTION_EXIT_WHEN_KINDS,
                            'exit.when.kind',
                        );
                        return html`
                            <div class="exit-card">
                                <div class="exit-head">
                                    <span class="criterion-index">${this.t('reflection_node_editor.exit_item')} ${index + 1}</span>
                                    <div class="exit-actions">
                                        <platform-button
                                            size="sm"
                                            variant="ghost"
                                            ?disabled=${index === 0}
                                            @click=${() => this._onMoveExit(index, -1)}
                                        >${this.t('reflection_node_editor.exit_move_up')}</platform-button>
                                        <platform-button
                                            size="sm"
                                            variant="ghost"
                                            ?disabled=${index >= exits.length - 1}
                                            @click=${() => this._onMoveExit(index, 1)}
                                        >${this.t('reflection_node_editor.exit_move_down')}</platform-button>
                                        <platform-button
                                            size="sm"
                                            variant="ghost"
                                            ?disabled=${exits.length <= 1}
                                            @click=${() => this._onRemoveExit(index)}
                                        >${this.t('reflection_node_editor.exit_remove')}</platform-button>
                                    </div>
                                </div>
                                <div class="grid">
                                    <platform-field
                                        class="field"
                                        type="string"
                                        mode="edit"
                                        .label=${this.t('reflection_node_editor.exit_id')}
                                        .value=${exitId}
                                        @change=${(e) => {
                                            const value = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
                                            this._onExitField(index, 'exit_id', value);
                                        }}
                                    ></platform-field>
                                    <platform-field
                                        class="field"
                                        type="string"
                                        mode="edit"
                                        .label=${this.t('reflection_node_editor.exit_label')}
                                        .value=${label}
                                        @change=${(e) => {
                                            const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                                            this._onExitField(index, 'label', value);
                                        }}
                                    ></platform-field>
                                    <platform-field
                                        class="field full"
                                        type="enum"
                                        mode="edit"
                                        .label=${this.t('reflection_node_editor.exit_when_kind')}
                                        .value=${whenKind}
                                        .config=${{ values: this._enumValues(REFLECTION_EXIT_WHEN_KINDS, 'reflection_node_editor.when_kinds') }}
                                        @change=${(e) => {
                                            const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                                            this._onExitWhenKind(index, value);
                                        }}
                                    ></platform-field>
                                    ${whenKind === 'decision_eq' ? html`
                                        <platform-field
                                            class="field full"
                                            type="enum"
                                            mode="edit"
                                            .label=${this.t('reflection_node_editor.exit_when_decision')}
                                            .value=${this._requiredEnum(
                                                when.decision,
                                                CRITIC_DECISIONS,
                                                'exit.when.decision',
                                            )}
                                            .config=${{ values: this._enumValues(CRITIC_DECISIONS, 'reflection_node_editor.decisions') }}
                                            @change=${(e) => {
                                                const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                                                this._onExitWhenDecision(index, value);
                                            }}
                                        ></platform-field>
                                    ` : nothing}
                                    ${whenKind === 'blocked_reason_prefix' ? html`
                                        <platform-field
                                            class="field full"
                                            type="string"
                                            mode="edit"
                                            .label=${this.t('reflection_node_editor.exit_when_reason_prefix')}
                                            .value=${typeof when.reason_prefix === 'string' ? when.reason_prefix : ''}
                                            @change=${(e) => {
                                                const value = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
                                                this._onExitWhenReasonPrefix(index, value);
                                            }}
                                        ></platform-field>
                                    ` : nothing}
                                </div>
                                <p class="block-hint">${this.t(`reflection_node_editor.when_descriptions.${whenKind}`)}</p>
                            </div>
                        `;
                    })}
                    <platform-button size="sm" variant="secondary" @click=${this._onAddExit}>
                        ${this.t('reflection_node_editor.exit_add')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderPresets(policy) {
        const active = this._activePresetId(policy);
        const cards = [
            {
                id: 'final_answer',
                titleKey: 'reflection_node_editor.preset_final_answer_title',
                subtitleKey: 'reflection_node_editor.preset_final_answer_subtitle',
                icon: 'check',
            },
            {
                id: 'transaction',
                titleKey: 'reflection_node_editor.preset_transaction_title',
                subtitleKey: 'reflection_node_editor.preset_transaction_subtitle',
                icon: 'lock',
            },
            {
                id: 'quality',
                titleKey: 'reflection_node_editor.preset_quality_title',
                subtitleKey: 'reflection_node_editor.preset_quality_subtitle',
                icon: 'sparkles',
            },
        ];
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_presets')}</h4>
                <div class="presets">
                    ${cards.map((card) => html`
                        <platform-picker-card
                            .title=${this.t(card.titleKey)}
                            .subtitle=${this.t(card.subtitleKey)}
                            .value=${card.id}
                            .icon=${card.icon}
                            ?selected=${active === card.id}
                            @select=${(e) => {
                                const presetId = e.detail?.value;
                                if (typeof presetId !== 'string') {
                                    throw new TypeError('flows-reflection-node-editor: preset value must be string');
                                }
                                this._onApplyPreset(presetId);
                            }}
                        ></platform-picker-card>
                    `)}
                </div>
            </section>
        `;
    }

    _renderCheckSection(policy) {
        const target = asObject(policy.target);
        const targetKind = this._requiredEnum(target.kind, REFLECTION_TARGET_KINDS, 'target.kind');
        const statePath = typeof target.state_path === 'string' ? target.state_path : '';
        const gate = this._requiredEnum(policy.gate, REFLECTION_GATES, 'gate');
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_check')}</h4>
                <div class="block-card content-panel">
                    <div class="grid">
                        <div class="field-stack">
                            <platform-field
                                class="field"
                                type="enum"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.target_kind')}
                                .value=${targetKind}
                                .config=${{ values: this._enumValues(REFLECTION_TARGET_KINDS, 'reflection_node_editor.targets') }}
                                @change=${this._onTargetKind}
                            ></platform-field>
                            <p class="block-hint">${this.t(`reflection_node_editor.target_descriptions.${targetKind}`)}</p>
                        </div>
                        <div class="field-stack">
                            <platform-field
                                class="field"
                                type="enum"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.gate')}
                                .value=${gate}
                                .config=${{ values: this._enumValues(REFLECTION_GATES, 'reflection_node_editor.gates') }}
                                @change=${this._onGate}
                            ></platform-field>
                            <p class="block-hint">${this.t('reflection_node_editor.gate_hint')}</p>
                            <p class="block-hint">${this.t(`reflection_node_editor.gate_descriptions.${gate}`)}</p>
                        </div>
                        ${targetKind === 'state_path' ? html`
                            <div class="field-stack full">
                                <platform-field
                                    class="field"
                                    type="string"
                                    mode="edit"
                                    .label=${this.t('reflection_node_editor.state_path')}
                                    .value=${statePath}
                                    @change=${this._onStatePath}
                                ></platform-field>
                                <p class="block-hint">${this.t('reflection_node_editor.state_path_hint')}</p>
                            </div>
                        ` : nothing}
                        <div class="field-stack full">
                            <platform-field
                                class="field"
                                type="string"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.policy_id')}
                                .value=${typeof policy.policy_id === 'string' ? policy.policy_id : ''}
                                @change=${this._onPolicyId}
                            ></platform-field>
                            <p class="block-hint">${this.t('reflection_node_editor.policy_id_hint')}</p>
                        </div>
                        <div class="field-stack full">
                            <platform-field
                                class="field"
                                type="text"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.instruction')}
                                .value=${typeof policy.instruction === 'string' ? policy.instruction : ''}
                                @change=${this._onInstruction}
                            ></platform-field>
                            <p class="block-hint">${this.t('reflection_node_editor.instruction_hint')}</p>
                        </div>
                    </div>
                </div>
            </section>
        `;
    }

    _renderBlockRules(policy) {
        const minConfidence = this._requiredNumber(policy.min_confidence, 'min_confidence');
        const blockOn = this._requiredArray(policy.block_on_severities, 'block_on_severities');
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_block_rules')}</h4>
                <div class="block-card content-panel">
                    <div class="grid">
                        <div class="field-stack">
                            <platform-field
                                class="field"
                                type="number"
                                mode="edit"
                                .label=${this.t('reflection_node_editor.min_confidence')}
                                .value=${minConfidence}
                                @change=${this._onMinConfidence}
                            ></platform-field>
                            <p class="block-hint">${this.t('reflection_node_editor.min_confidence_hint')}</p>
                        </div>
                        <div class="field-stack full">
                            <p class="block-title" style="margin:0">${this.t('reflection_node_editor.block_on_severities')}</p>
                            <p class="block-hint">${this.t('reflection_node_editor.block_on_severities_hint')}</p>
                            <div class="severity-toggles">
                                ${CRITIC_SEVERITIES.map((severity) => {
                                    const checked = blockOn.includes(severity);
                                    const onlyOne = checked && blockOn.length === 1;
                                    return html`
                                        <platform-field
                                            class="field"
                                            type="boolean"
                                            mode="edit"
                                            .label=${this.t(`reflection_node_editor.severities.${severity}`)}
                                            .value=${checked}
                                            ?disabled=${onlyOne}
                                            @change=${(e) => {
                                                const next = e.detail?.value;
                                                if (typeof next !== 'boolean') {
                                                    throw new TypeError('flows-reflection-node-editor: severity toggle must be boolean');
                                                }
                                                this._onToggleSeverity(severity, next);
                                            }}
                                        ></platform-field>
                                    `;
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        `;
    }

    _renderCriteria() {
        const criteria = this._criteriaList();
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_criteria')}</h4>
                <div class="block-card content-panel">
                    <div class="criteria-list">
                        ${criteria.map((item, index) => {
                            if (!isPlainObject(item)) {
                                throw new Error('flows-reflection-node-editor: criterion object required');
                            }
                            const criterionId = typeof item.criterion_id === 'string' ? item.criterion_id : '';
                            const description = typeof item.description === 'string' ? item.description : '';
                            const severity = this._requiredEnum(item.severity, CRITIC_SEVERITIES, 'criterion.severity');
                            return html`
                                <div class="criterion-card">
                                    <div class="criterion-head">
                                        <span class="criterion-index">${this.t('reflection_node_editor.criteria')} ${index + 1}</span>
                                        <platform-button
                                            size="sm"
                                            variant="ghost"
                                            ?disabled=${criteria.length <= 1}
                                            @click=${() => this._onRemoveCriterion(index)}
                                        >${this.t('reflection_node_editor.criteria_remove')}</platform-button>
                                    </div>
                                    <div class="grid">
                                        <platform-field
                                            class="field"
                                            type="string"
                                            mode="edit"
                                            .label=${this.t('reflection_node_editor.criterion_id')}
                                            .value=${criterionId}
                                            @change=${(e) => {
                                                const value = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
                                                this._onCriterionField(index, 'criterion_id', value);
                                            }}
                                        ></platform-field>
                                        <platform-field
                                            class="field"
                                            type="enum"
                                            mode="edit"
                                            .label=${this.t('reflection_node_editor.criterion_severity')}
                                            .value=${severity}
                                            .config=${{ values: this._enumValues(CRITIC_SEVERITIES, 'reflection_node_editor.severities') }}
                                            @change=${(e) => {
                                                const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                                                this._onCriterionField(index, 'severity', value);
                                            }}
                                        ></platform-field>
                                        <platform-field
                                            class="field full"
                                            type="text"
                                            mode="edit"
                                            .label=${this.t('reflection_node_editor.criterion_description')}
                                            .value=${description}
                                            @change=${(e) => {
                                                const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
                                                this._onCriterionField(index, 'description', value);
                                            }}
                                        ></platform-field>
                                    </div>
                                </div>
                            `;
                        })}
                    </div>
                    <platform-button size="sm" variant="secondary" @click=${this._onAddCriterion}>
                        ${this.t('reflection_node_editor.criteria_add')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderLlmSection() {
        return html`
            <section class="block">
                <h4 class="block-title">${this.t('reflection_node_editor.section_llm')}</h4>
                <p class="block-hint">${this.t('reflection_node_editor.section_llm_hint')}</p>
                <div class="block-card content-panel">
                    <flows-llm-config-editor
                        .config=${this._llmForEditor()}
                        .allowFallbacks=${false}
                        @change=${this._onLlmConfigChange}
                    ></flows-llm-config-editor>
                </div>
            </section>
        `;
    }

    render() {
        const policy = this._policyForEditor();
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
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="stack">
                    ${this._renderIntro()}
                    ${this._renderPresets(policy)}
                    ${this._renderExitsSection()}
                    ${this._renderCheckSection(policy)}
                    ${this._renderBlockRules(policy)}
                    ${this._renderCriteria()}
                    ${this._renderLlmSection()}
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-reflection-node-editor', FlowsReflectionNodeEditor);
