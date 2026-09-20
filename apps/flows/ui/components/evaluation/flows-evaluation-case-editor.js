import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-json-editor.js';
import '../editors/flows-code-editor.js';
import { evaluationCatalogNameKey } from '../../_helpers/evaluation-catalog-labels.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import {
    flowBodyWithNode,
    flowBodyWithoutNode,
    listEffectiveLlmNodes,
    newEvaluationNodeId,
    requireEvaluationRole,
} from '../../_helpers/evaluation-flow-nodes.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';

function asArray(value) {
    return Array.isArray(value) ? value : [];
}

function stringValue(record, field) {
    if (!record || typeof record !== 'object') {
        return '';
    }
    const value = record[field];
    return typeof value === 'string' ? value : '';
}

function numberValue(record, field, standard) {
    if (!record || typeof record !== 'object') {
        return standard;
    }
    const value = record[field];
    return typeof value === 'number' && Number.isFinite(value) ? Math.trunc(value) : standard;
}

function tagsText(tags) {
    return asArray(tags).filter((item) => typeof item === 'string' && item.length > 0).join(', ');
}

function optionalNumberText(value) {
    return typeof value === 'number' && Number.isFinite(value) ? String(Math.trunc(value)) : '';
}

function jsonText(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return '{\n  \"type\": \"object\"\n}';
    }
    return formatJsonPretty(value);
}

function defaultCheckCodeSource() {
    return 'def evaluate(item, sample):\n    return {\"score\": 1.0, \"passed\": True}\n';
}

function defaultInputCodeSource() {
    return 'def generate(item):\n    return \"hello\"\n';
}

function emptyTurnDraft() {
    return {
        inputType: 'text',
        content: '',
        inputCodeLanguage: 'python',
        inputCodeSource: defaultInputCodeSource(),
        nodeId: '',
        checkType: 'contains',
        contains: '',
        notContains: '',
        regexPattern: '',
        minChars: '',
        maxChars: '',
        statePath: 'response',
        stateOperator: 'ne',
        jsonSchema: '{\n  \"type\": \"object\"\n}',
        traceAssertion: 'tool_called',
        traceValue: '',
        rubricId: '',
        rubricVersionId: '',
        judgeNodeId: '',
        builtinMetricId: 'answer_relevance',
        reference: '',
        checkCodeLanguage: 'python',
        checkCodeSource: defaultCheckCodeSource(),
    };
}

function hydrateTurnFromCase(turn) {
    const draft = emptyTurnDraft();
    if (!turn || typeof turn !== 'object') {
        return draft;
    }
    const input = turn.input;
    if (input && typeof input === 'object') {
        const inputType = stringValue(input, 'type');
        if (inputType === 'text' || inputType === 'inline_code' || inputType === 'node') {
            draft.inputType = inputType;
        }
        draft.content = stringValue(input, 'content');
        draft.inputCodeLanguage = stringValue(input, 'language').length > 0
            ? stringValue(input, 'language')
            : 'python';
        draft.inputCodeSource = stringValue(input, 'source').length > 0
            ? stringValue(input, 'source')
            : defaultInputCodeSource();
        draft.nodeId = stringValue(input, 'node_id');
    }
    const checks = asArray(turn.checks);
    const check = checks.length > 0 ? checks[0] : null;
    if (!check || typeof check !== 'object') {
        return draft;
    }
    const checkType = stringValue(check, 'type');
    draft.checkType = checkType.length > 0 ? checkType : 'contains';
    draft.contains = asArray(check.values).filter((item) => typeof item === 'string').join(', ');
    draft.notContains = draft.checkType === 'not_contains' ? draft.contains : '';
    draft.regexPattern = stringValue(check, 'pattern');
    draft.minChars = optionalNumberText(check.min_chars);
    draft.maxChars = optionalNumberText(check.max_chars);
    draft.statePath = stringValue(check, 'path').length > 0 ? stringValue(check, 'path') : 'response';
    draft.stateOperator = stringValue(check, 'operator').length > 0 ? stringValue(check, 'operator') : 'ne';
    draft.jsonSchema = jsonText(check.json_schema);
    draft.traceAssertion = stringValue(check, 'assertion').length > 0
        ? stringValue(check, 'assertion')
        : 'tool_called';
    draft.traceValue = stringValue(check, 'value');
    draft.rubricVersionId = stringValue(check, 'rubric_version_id');
    draft.judgeNodeId = stringValue(check, 'judge_node_id');
    draft.builtinMetricId = stringValue(check, 'evaluator_id').length > 0
        ? stringValue(check, 'evaluator_id')
        : 'answer_relevance';
    draft.reference = stringValue(check, 'reference');
    draft.checkCodeLanguage = stringValue(check, 'language').length > 0
        ? stringValue(check, 'language')
        : 'python';
    if (draft.checkType === 'code' && stringValue(check, 'source').length > 0) {
        draft.checkCodeSource = stringValue(check, 'source');
    }
    return draft;
}

export class FlowsEvaluationCaseEditor extends PlatformElement {
    static properties = {
        suite: { type: Object },
        testCase: { type: Object },
        catalog: { type: Array },
        busy: { type: Boolean },
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _hydratedCaseId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _tags: { state: true },
        _turns: { state: true },
        _activeTurnIndex: { state: true },
        _rubrics: { state: true },
        _rubricVersions: { state: true },
        _rubricDraftName: { state: true },
        _rubricDraftPrompt: { state: true },
        _rubricDraftThreshold: { state: true },
        _showRubricCreate: { state: true },
        _nodeBusy: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        panelShellStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                width: 100%;
                height: 100%;
                min-width: 0;
                min-height: 0;
                color: var(--text-primary);
            }

            .title {
                min-width: 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .title platform-help-hint,
            .section-label platform-help-hint {
                flex: 0 0 auto;
            }

            .body {
                flex: 1 1 auto;
                min-height: 0;
                overflow-x: hidden;
                overflow-y: auto;
                padding: 14px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                overscroll-behavior: contain;
            }

            .body > * {
                flex: 0 0 auto;
                min-width: 0;
            }

            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }

            .full {
                grid-column: 1 / -1;
            }

            platform-field {
                display: block;
                min-width: 0;
            }

            platform-field.text-field {
                --field-pill-textarea-min-height: 86px;
            }

            platform-field.prompt-field {
                --field-pill-textarea-min-height: 104px;
            }

            .check-type-scroll,
            .turn-scroll {
                overflow-x: auto;
            }

            .section-label {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .row-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
            }

            .enum-suffix-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex: 0 0 auto;
            }

            .code {
                min-height: 128px;
            }

            flows-code-editor,
            platform-json-editor {
                min-height: 128px;
            }

            platform-json-editor.json-schema-editor {
                min-height: 150px;
            }

            .footer {
                flex: 0 0 auto;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
                padding: 12px 14px;
                border-top: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--bg-surface), transparent 18%);
            }

            .empty {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-6);
                color: var(--text-tertiary);
                text-align: center;
            }

            .empty-mark {
                width: 46px;
                height: 46px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 14px;
                border: 1px solid color-mix(in srgb, var(--accent), transparent 66%);
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent), transparent 86%);
            }

            @media (max-width: 920px) {
                .grid {
                    grid-template-columns: 1fr;
                }

                .full {
                    grid-column: auto;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.suite = null;
        this.testCase = null;
        this.catalog = [];
        this.busy = false;
        this.flowId = '';
        this.branchId = 'default';
        this._hydratedCaseId = '';
        this._name = '';
        this._description = '';
        this._tags = '';
        this._turns = [emptyTurnDraft()];
        this._activeTurnIndex = 0;
        this._rubrics = [];
        this._rubricVersions = [];
        this._rubricDraftName = '';
        this._rubricDraftPrompt = '';
        this._rubricDraftThreshold = '7';
        this._showRubricCreate = false;
        this._nodeBusy = false;
        this._flows = this.useResource('flows/flows');
        this._flowUpdate = this.useOp('flows/flow_update');
        this._rubricsList = this.useOp('flows/evaluation_rubrics_list');
        this._rubricCreate = this.useOp('flows/evaluation_rubric_create');
        this._rubricVersionsList = this.useOp('flows/evaluation_rubric_versions_list');
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('testCase')) {
            this._hydrateFromCase();
        }
        if (changed.has('flowId') || changed.has('branchId')) {
            void this._ensureFlowLoaded();
            void this._loadRubrics();
        }
    }

    async _ensureFlowLoaded() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        if (this._flows.byId[this.flowId]) {
            this.requestUpdate();
            return;
        }
        await this._flows.fetchItem(this.flowId);
        this.requestUpdate();
    }

    async _loadRubrics() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this._rubrics = [];
            return;
        }
        const result = await this._rubricsList.run({ flow_id: this.flowId });
        this._rubrics = asArray(result && result.items);
        const turn = this._activeTurn();
        if (turn.rubricVersionId.length > 0 && turn.rubricId.length === 0) {
            await this._resolveRubricIdForVersion(turn.rubricVersionId);
        } else if (turn.rubricId.length > 0) {
            await this._loadRubricVersions(turn.rubricId);
        }
    }

    async _resolveRubricIdForVersion(rubricVersionId) {
        for (const rubric of this._rubrics) {
            const rubricId = stringValue(rubric, 'rubric_id');
            if (rubricId.length === 0) {
                continue;
            }
            const versionsResult = await this._rubricVersionsList.run({ rubric_id: rubricId });
            const versions = asArray(versionsResult && versionsResult.items);
            const found = versions.find((item) => stringValue(item, 'rubric_version_id') === rubricVersionId);
            if (found) {
                this._patchActiveTurn({ rubricId });
                this._rubricVersions = versions;
                return;
            }
        }
    }

    async _loadRubricVersions(rubricId) {
        if (rubricId.length === 0) {
            this._rubricVersions = [];
            return;
        }
        const result = await this._rubricVersionsList.run({ rubric_id: rubricId });
        this._rubricVersions = asArray(result && result.items);
    }

    _branchId() {
        if (typeof this.branchId !== 'string') {
            return 'default';
        }
        const value = this.branchId.trim();
        if (value.length === 0 || value === 'base') {
            return 'default';
        }
        return value;
    }

    _flowRecord() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return null;
        }
        const item = this._flows.byId[this.flowId];
        return item && typeof item === 'object' ? item : null;
    }

    _llmNodes() {
        const flow = this._flowRecord();
        if (!flow) {
            return [];
        }
        return listEffectiveLlmNodes(flow, this._branchId());
    }

    _hydrateFromCase() {
        const caseId = stringValue(this.testCase, 'case_id');
        if (caseId === this._hydratedCaseId) {
            return;
        }
        this._hydratedCaseId = caseId;
        this._name = stringValue(this.testCase, 'name');
        this._description = stringValue(this.testCase, 'description');
        this._tags = tagsText(this.testCase && this.testCase.tags);
        const turns = asArray(this.testCase && this.testCase.turns);
        this._turns = turns.length > 0 ? turns.map((turn) => hydrateTurnFromCase(turn)) : [emptyTurnDraft()];
        this._activeTurnIndex = 0;
        this._showRubricCreate = false;
        void this._loadRubrics();
    }

    _activeTurn() {
        if (this._activeTurnIndex < 0 || this._activeTurnIndex >= this._turns.length) {
            throw new Error('FlowsEvaluationCaseEditor: active turn index out of range');
        }
        return this._turns[this._activeTurnIndex];
    }

    _patchActiveTurn(patch) {
        const next = this._turns.map((turn, index) => {
            if (index !== this._activeTurnIndex) {
                return turn;
            }
            return { ...turn, ...patch };
        });
        this._turns = next;
    }

    _fieldValue(event) {
        const detail = event.detail;
        return detail && typeof detail.value === 'string' ? detail.value : '';
    }

    _setCheckType(checkType) {
        this._patchActiveTurn({ checkType });
    }

    _setInputType(inputType) {
        this._patchActiveTurn({ inputType });
    }

    _checkTypeItems() {
        return [
            { value: 'contains', label: this.t('evaluation.case_editor.check_contains'), icon: 'search-check' },
            { value: 'not_contains', label: this.t('evaluation.case_editor.check_not_contains'), icon: 'shield' },
            { value: 'regex', label: this.t('evaluation.case_editor.check_regex'), icon: 'code' },
            { value: 'length', label: this.t('evaluation.case_editor.check_length'), icon: 'list' },
            { value: 'state_path', label: this.t('evaluation.case_editor.check_state'), icon: 'braces' },
            { value: 'json_schema', label: this.t('evaluation.case_editor.check_json_schema'), icon: 'table' },
            { value: 'trace_assertion', label: this.t('evaluation.case_editor.check_trace'), icon: 'activity' },
            { value: 'builtin_metric', label: this.t('evaluation.case_editor.check_builtin'), icon: 'badge-check' },
            { value: 'llm_judge', label: this.t('evaluation.case_editor.check_judge'), icon: 'sparkles' },
            { value: 'code', label: this.t('evaluation.case_editor.check_code'), icon: 'code' },
        ];
    }

    _inputTypeItems() {
        return [
            { value: 'text', label: this.t('evaluation.case_editor.input_text'), icon: 'type' },
            { value: 'inline_code', label: this.t('evaluation.case_editor.input_inline_code'), icon: 'code' },
            { value: 'node', label: this.t('evaluation.case_editor.input_node'), icon: 'bot' },
        ];
    }

    _turnItems() {
        return this._turns.map((_, index) => ({
            value: String(index),
            label: this.t('evaluation.case_editor.turn_n', { n: index + 1 }),
        }));
    }

    _traceAssertionItems() {
        return [
            { value: 'tool_called', label: this.t('evaluation.case_editor.trace_tool_called') },
            { value: 'node_completed', label: this.t('evaluation.case_editor.trace_node_completed') },
            { value: 'node_failed', label: this.t('evaluation.case_editor.trace_node_failed') },
        ];
    }

    _builtinMetricItems(metrics) {
        return metrics.map((item) => {
            const metricId = stringValue(item, 'evaluator_id');
            return {
                value: metricId,
                label: this.t(evaluationCatalogNameKey(metricId)),
            };
        });
    }

    _codeLanguageItems() {
        return ['python', 'javascript', 'typescript', 'go', 'csharp'].map((language) => ({
            value: language,
            label: language,
            icon: language,
        }));
    }

    _llmNodeEnumConfig(preferRole) {
        const nodes = this._llmNodes();
        const preferred = preferRole
            ? nodes.filter((node) => node.evaluation_role === preferRole)
            : nodes;
        const source = preferred.length > 0 ? preferred : nodes;
        const values = source.map((node) => ({
            value: node.node_id,
            label: node.name,
        }));
        if (values.length === 0) {
            return {
                values: [{
                    value: '',
                    label: this.t('evaluation.case_editor.no_llm_nodes'),
                }],
            };
        }
        return { values };
    }

    _rubricEnumConfig() {
        const values = this._rubrics.map((rubric) => ({
            value: stringValue(rubric, 'rubric_id'),
            label: stringValue(rubric, 'name'),
        }));
        if (values.length === 0) {
            return {
                values: [{
                    value: '',
                    label: this.t('evaluation.case_editor.no_rubrics'),
                }],
            };
        }
        return { values };
    }

    _rubricVersionEnumConfig() {
        const values = this._rubricVersions.map((version) => {
            const versionId = stringValue(version, 'rubric_version_id');
            const versionNumber = version && typeof version.version === 'number'
                ? String(version.version)
                : stringValue(version, 'version');
            return {
                value: versionId,
                label: `v${versionNumber} · ${versionId.slice(0, 8)}`,
            };
        });
        if (values.length === 0) {
            return {
                values: [{
                    value: '',
                    label: this.t('evaluation.case_editor.no_rubric_versions'),
                }],
            };
        }
        return { values };
    }

    _catalogMetrics() {
        return asArray(this.catalog).filter((item) => stringValue(item, 'check_type') === 'builtin_metric');
    }

    _optionalInt(value, labelKey) {
        const text = value.trim();
        if (text.length === 0) {
            return null;
        }
        const parsed = Number(text);
        if (!Number.isInteger(parsed) || parsed < 0) {
            this.toast(labelKey, { type: 'error' });
            return undefined;
        }
        return parsed;
    }

    _addTurn() {
        this._turns = [...this._turns, emptyTurnDraft()];
        this._activeTurnIndex = this._turns.length - 1;
    }

    _removeActiveTurn() {
        if (this._turns.length <= 1) {
            return;
        }
        const next = this._turns.filter((_, index) => index !== this._activeTurnIndex);
        this._turns = next;
        this._activeTurnIndex = Math.min(this._activeTurnIndex, next.length - 1);
    }

    _nextEvaluationNodeName(evaluationRole) {
        const role = requireEvaluationRole(evaluationRole);
        const base = role === 'judge'
            ? this.t('evaluation.case_editor.judge_node_default_name')
            : this.t('evaluation.case_editor.tester_node_default_name');
        const taken = new Set(
            this._llmNodes()
                .filter((node) => node.evaluation_role === role)
                .map((node) => node.name),
        );
        if (!taken.has(base)) {
            return base;
        }
        let index = 2;
        while (taken.has(`${base} ${index}`)) {
            index += 1;
        }
        return `${base} ${index}`;
    }

    async _createFlowNode(role) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        const flow = this._flowRecord();
        if (!flow) {
            await this._ensureFlowLoaded();
        }
        const current = this._flowRecord();
        if (!current) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        const evaluationRole = requireEvaluationRole(role);
        const nodeId = newEvaluationNodeId(evaluationRole === 'judge' ? 'eval_judge' : 'eval_tester');
        const prompt = evaluationRole === 'judge'
            ? this.t('evaluation.case_editor.judge_node_default_prompt')
            : this.t('evaluation.case_editor.tester_node_default_prompt');
        const name = this._nextEvaluationNodeName(evaluationRole);
        const nodeConfig = {
            type: 'llm_node',
            name,
            prompt,
            store: { evaluation_role: evaluationRole },
        };
        this._nodeBusy = true;
        try {
            const body = flowBodyWithNode(current, this._branchId(), nodeId, nodeConfig);
            await this._flowUpdate.run({ ...body, flow_id: this.flowId });
            await this._flows.fetchItem(this.flowId);
            if (role === 'judge') {
                this._patchActiveTurn({ judgeNodeId: nodeId });
                this.toast('evaluation.toast.judge_node_created', { type: 'success' });
            } else {
                this._patchActiveTurn({ nodeId, inputType: 'node' });
                this.toast('evaluation.toast.tester_node_created', { type: 'success' });
            }
            this.requestUpdate();
            this._openLlmNodeEditor(nodeId, evaluationRole);
        } finally {
            this._nodeBusy = false;
        }
    }

    _openLlmNodeEditor(nodeId, evaluationRole) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            const role = requireEvaluationRole(evaluationRole);
            this.toast(
                role === 'judge'
                    ? 'evaluation.toast.judge_node_required'
                    : 'evaluation.toast.tester_node_required',
                { type: 'error' },
            );
            return;
        }
        this.openModal('flows.embedded_tool_config', {
            toolRef: null,
            onSave: null,
            flowId: this.flowId,
            branchId: this._branchId(),
            nodeId,
            focusMode: true,
            onSaved: () => {
                void this._flows.fetchItem(this.flowId);
                this.requestUpdate();
            },
        });
    }

    async _deleteFlowNode(nodeId, evaluationRole) {
        const role = requireEvaluationRole(evaluationRole);
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        if (typeof nodeId !== 'string' || nodeId.length === 0) {
            this.toast(
                role === 'judge'
                    ? 'evaluation.toast.judge_node_required'
                    : 'evaluation.toast.tester_node_required',
                { type: 'error' },
            );
            return;
        }
        const ok = await platformConfirm(
            this.t(
                role === 'judge'
                    ? 'evaluation.case_editor.delete_judge_node_message'
                    : 'evaluation.case_editor.delete_tester_node_message',
            ),
            {
                title: this.t(
                    role === 'judge'
                        ? 'evaluation.case_editor.delete_judge_node'
                        : 'evaluation.case_editor.delete_tester_node',
                ),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('evaluation.case_editor.delete_node_confirm'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._ensureFlowLoaded();
        const current = this._flowRecord();
        if (!current) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        this._nodeBusy = true;
        try {
            const body = flowBodyWithoutNode(current, this._branchId(), nodeId);
            await this._flowUpdate.run({ ...body, flow_id: this.flowId });
            await this._flows.fetchItem(this.flowId);
            this._turns = this._turns.map((turn) => {
                if (role === 'judge') {
                    if (turn.judgeNodeId !== nodeId) {
                        return turn;
                    }
                    return { ...turn, judgeNodeId: '' };
                }
                if (turn.nodeId !== nodeId) {
                    return turn;
                }
                return { ...turn, nodeId: '' };
            });
            this.toast(
                role === 'judge'
                    ? 'evaluation.toast.judge_node_deleted'
                    : 'evaluation.toast.tester_node_deleted',
                { type: 'success' },
            );
            this.requestUpdate();
        } finally {
            this._nodeBusy = false;
        }
    }

    async _onRubricSelected(rubricId) {
        this._patchActiveTurn({ rubricId, rubricVersionId: '' });
        await this._loadRubricVersions(rubricId);
        if (this._rubricVersions.length > 0) {
            const latest = this._rubricVersions[this._rubricVersions.length - 1];
            this._patchActiveTurn({
                rubricVersionId: stringValue(latest, 'rubric_version_id'),
            });
        }
    }

    async _createRubric() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this.toast('evaluation.toast.flow_required', { type: 'error' });
            return;
        }
        const name = this._rubricDraftName.trim();
        const prompt = this._rubricDraftPrompt.trim();
        const threshold = Number(this._rubricDraftThreshold);
        if (name.length === 0 || prompt.length === 0 || !Number.isFinite(threshold)) {
            this.toast('evaluation.toast.rubric_create_required', { type: 'error' });
            return;
        }
        const created = await this._rubricCreate.run({
            flow_id: this.flowId,
            name,
            prompt,
            pass_threshold: threshold,
            description: '',
            tags: [],
        });
        if (!created || typeof created !== 'object') {
            throw new Error('FlowsEvaluationCaseEditor: rubric create returned empty payload');
        }
        const rubric = created.rubric;
        const version = created.version;
        if (!rubric || typeof rubric !== 'object' || !version || typeof version !== 'object') {
            throw new Error('FlowsEvaluationCaseEditor: rubric create missing rubric/version');
        }
        this._showRubricCreate = false;
        this._rubricDraftName = '';
        this._rubricDraftPrompt = '';
        this._rubricDraftThreshold = '7';
        await this._loadRubrics();
        this._patchActiveTurn({
            rubricId: stringValue(rubric, 'rubric_id'),
            rubricVersionId: stringValue(version, 'rubric_version_id'),
        });
        await this._loadRubricVersions(stringValue(rubric, 'rubric_id'));
    }

    _submit() {
        const name = this._name.trim();
        if (name.length === 0) {
            this.toast('evaluation.toast.case_required', { type: 'error' });
            return;
        }
        const turns = [];
        for (let index = 0; index < this._turns.length; index += 1) {
            const turn = this._turns[index];
            const input = this._buildInput(turn);
            if (input === null) {
                this._activeTurnIndex = index;
                return;
            }
            const check = this._buildCheck(turn);
            if (check === null) {
                this._activeTurnIndex = index;
                return;
            }
            turns.push({ input, checks: [check] });
        }
        const tags = this._tags.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
        const body = {
            name,
            description: this._description,
            branch_ids: '*',
            target: { type: 'flow' },
            initial_state: null,
            turns,
            max_turns: numberValue(this.testCase, 'max_turns', Math.max(10, turns.length)),
            timeout_seconds: numberValue(this.testCase, 'timeout_seconds', 300),
            enabled: true,
            tags,
            sort_order: numberValue(this.testCase, 'sort_order', 0),
        };
        const caseId = stringValue(this.testCase, 'case_id');
        if (caseId.length > 0) {
            this.emit('case-update', { case_id: caseId, body });
            return;
        }
        this.emit('case-create', { body });
    }

    _buildInput(turn) {
        if (turn.inputType === 'text') {
            const content = turn.content.trim();
            if (content.length === 0) {
                this.toast('evaluation.toast.case_required', { type: 'error' });
                return null;
            }
            return { type: 'text', content };
        }
        if (turn.inputType === 'inline_code') {
            const source = turn.inputCodeSource.trim();
            if (source.length === 0) {
                this.toast('evaluation.toast.case_required', { type: 'error' });
                return null;
            }
            return {
                type: 'inline_code',
                language: turn.inputCodeLanguage,
                source,
                entrypoint: null,
            };
        }
        if (turn.inputType === 'node') {
            const nodeId = turn.nodeId.trim();
            if (nodeId.length === 0) {
                this.toast('evaluation.toast.tester_node_required', { type: 'error' });
                return null;
            }
            return { type: 'node', node_id: nodeId, node: null };
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported input type ${turn.inputType}`);
    }

    _buildCheck(turn) {
        if (turn.checkType === 'contains') {
            const values = turn.contains.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
            if (values.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'contains', source: 'response', values, mode: 'any', case_sensitive: false, state_path: null };
        }
        if (turn.checkType === 'not_contains') {
            const values = turn.notContains.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
            if (values.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'not_contains', source: 'response', values, case_sensitive: false, state_path: null };
        }
        if (turn.checkType === 'regex') {
            const pattern = turn.regexPattern.trim();
            if (pattern.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'regex', source: 'response', pattern, ignore_case: true, state_path: null };
        }
        if (turn.checkType === 'length') {
            const minChars = this._optionalInt(turn.minChars, 'evaluation.toast.length_invalid');
            const maxChars = this._optionalInt(turn.maxChars, 'evaluation.toast.length_invalid');
            if (minChars === undefined || maxChars === undefined) {
                return null;
            }
            if (minChars === null && maxChars === null) {
                this.toast('evaluation.toast.length_required', { type: 'error' });
                return null;
            }
            return { type: 'length', source: 'response', min_chars: minChars, max_chars: maxChars, state_path: null };
        }
        if (turn.checkType === 'state_path') {
            const path = turn.statePath.trim();
            if (path.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'state_path', path, operator: turn.stateOperator, value: null };
        }
        if (turn.checkType === 'json_schema') {
            try {
                const parsed = JSON.parse(turn.jsonSchema);
                if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                    this.toast('evaluation.toast.json_schema_invalid', { type: 'error' });
                    return null;
                }
                return { type: 'json_schema', source: 'state', json_schema: parsed, state_path: 'structured_output' };
            } catch (_error) {
                this.toast('evaluation.toast.json_schema_invalid', { type: 'error' });
                return null;
            }
        }
        if (turn.checkType === 'trace_assertion') {
            const value = turn.traceValue.trim();
            if (value.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'trace_assertion', assertion: turn.traceAssertion, value };
        }
        if (turn.checkType === 'llm_judge') {
            const rubricVersionId = turn.rubricVersionId.trim();
            const judgeNodeId = turn.judgeNodeId.trim();
            if (rubricVersionId.length === 0) {
                this.toast('evaluation.toast.rubric_required', { type: 'error' });
                return null;
            }
            if (judgeNodeId.length === 0) {
                this.toast('evaluation.toast.judge_node_required', { type: 'error' });
                return null;
            }
            return {
                type: 'llm_judge',
                rubric_version_id: rubricVersionId,
                judge_node_id: judgeNodeId,
                judge_node: null,
            };
        }
        if (turn.checkType === 'builtin_metric') {
            return {
                type: 'builtin_metric',
                evaluator_id: turn.builtinMetricId,
                source: 'response',
                state_path: null,
                reference: turn.reference,
                threshold: null,
                judge_node_id: null,
                judge_node: null,
            };
        }
        if (turn.checkType === 'code') {
            const source = turn.checkCodeSource.trim();
            if (source.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'code', language: turn.checkCodeLanguage, source, entrypoint: null };
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported check type ${turn.checkType}`);
    }

    render() {
        const suiteId = stringValue(this.suite, 'suite_id');
        if (suiteId.length === 0) {
            return html`
                <section class="content-panel">
                    <div class="empty">
                        <span class="empty-mark"><platform-icon name="checklist" size="20"></platform-icon></span>
                        <span>${this.t('evaluation.case_editor.no_suite')}</span>
                    </div>
                </section>
            `;
        }
        const caseId = stringValue(this.testCase, 'case_id');
        const turn = this._activeTurn();
        return html`
            <section class="content-panel">
                <div class="content-panel-head">
                    <div class="title">
                        <platform-icon name="file-pen" size="16"></platform-icon>
                        ${caseId.length > 0 ? this.t('evaluation.case_editor.edit_title') : this.t('evaluation.case_editor.create_title')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.case_editor')}
                            .label=${this.t('evaluation.hints.case_editor_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                </div>
                <div class="body">
                    <div class="grid">
                        <platform-field
                            pill-density="compact"
                            type="string"
                            mode="edit"
                            .label=${this.t('evaluation.case_editor.name')}
                            .hint=${this.t('evaluation.hints.case_name')}
                            .placeholder=${this.t('evaluation.case_editor.name_placeholder')}
                            .value=${this._name}
                            @change=${(event) => { this._name = this._fieldValue(event); }}
                        ></platform-field>
                        <platform-field
                            pill-density="compact"
                            type="string"
                            mode="edit"
                            .label=${this.t('evaluation.case_editor.tags')}
                            .hint=${this.t('evaluation.hints.case_tags')}
                            .placeholder=${this.t('evaluation.case_editor.tags_placeholder')}
                            .value=${this._tags}
                            @change=${(event) => { this._tags = this._fieldValue(event); }}
                        ></platform-field>
                        <platform-field
                            class="full text-field"
                            pill-density="compact"
                            type="text"
                            mode="edit"
                            .label=${this.t('evaluation.case_editor.description')}
                            .hint=${this.t('evaluation.hints.case_description')}
                            .placeholder=${this.t('evaluation.case_editor.description_placeholder')}
                            .value=${this._description}
                            @change=${(event) => { this._description = this._fieldValue(event); }}
                        ></platform-field>
                    </div>

                    <div class="section-label">${this.t('evaluation.case_editor.turns')}</div>
                    <div class="row-actions">
                        <div class="turn-scroll">
                            <platform-segmented-control
                                .value=${String(this._activeTurnIndex)}
                                .items=${this._turnItems()}
                                aria-label=${this.t('evaluation.case_editor.turns_aria')}
                                @change=${(event) => {
                                    this._activeTurnIndex = Number(event.detail.value);
                                }}
                            ></platform-segmented-control>
                        </div>
                        <platform-button variant="secondary" density="compact" @click=${this._addTurn}>
                            <platform-icon name="plus" size="14"></platform-icon>
                            ${this.t('evaluation.case_editor.turn_add')}
                        </platform-button>
                        <platform-button
                            variant="secondary"
                            density="compact"
                            ?disabled=${this._turns.length <= 1}
                            @click=${this._removeActiveTurn}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                            ${this.t('evaluation.case_editor.turn_remove')}
                        </platform-button>
                    </div>

                    <div class="section-label">
                        ${this.t('evaluation.case_editor.input_kind')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.case_input')}
                            .label=${this.t('evaluation.hints.case_input_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                    <platform-segmented-control
                        .value=${turn.inputType}
                        .items=${this._inputTypeItems()}
                        aria-label=${this.t('evaluation.case_editor.input_kind_aria')}
                        @change=${(event) => this._setInputType(event.detail.value)}
                    ></platform-segmented-control>
                    ${this._renderInputEditor(turn)}

                    <div class="section-label">
                        ${this.t('evaluation.case_editor.check_type')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.check_type')}
                            .label=${this.t('evaluation.hints.check_type_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                    <div class="check-type-scroll">
                        <platform-segmented-control
                            .value=${turn.checkType}
                            .items=${this._checkTypeItems()}
                            aria-label=${this.t('evaluation.case_editor.check_type_aria')}
                            @change=${(event) => this._setCheckType(event.detail.value)}
                        ></platform-segmented-control>
                    </div>

                    ${this._renderCheckEditor(turn)}
                </div>
                <div class="footer">
                    <platform-button
                        variant="primary"
                        density="compact"
                        ?disabled=${this.busy || this._nodeBusy || this._flowUpdate.busy || this._rubricCreate.busy}
                        @click=${this._submit}
                    >
                        <platform-icon name="save" size="14"></platform-icon>
                        ${caseId.length > 0 ? this.t('evaluation.case_editor.save') : this.t('evaluation.case_editor.create')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderInputEditor(turn) {
        if (turn.inputType === 'text') {
            return html`
                <platform-field
                    class="prompt-field"
                    pill-density="compact"
                    type="text"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.input')}
                    .hint=${this.t('evaluation.hints.case_input')}
                    .placeholder=${this.t('evaluation.case_editor.input_placeholder')}
                    .value=${turn.content}
                    @change=${(event) => this._patchActiveTurn({ content: this._fieldValue(event) })}
                ></platform-field>
            `;
        }
        if (turn.inputType === 'inline_code') {
            return html`
                <platform-segmented-control
                    .value=${turn.inputCodeLanguage}
                    .items=${this._codeLanguageItems()}
                    aria-label=${this.t('evaluation.case_editor.code_language_aria')}
                    @change=${(event) => this._patchActiveTurn({ inputCodeLanguage: event.detail.value })}
                ></platform-segmented-control>
                <flows-code-editor
                    class="code"
                    .value=${turn.inputCodeSource}
                    .language=${turn.inputCodeLanguage}
                    @change=${(event) => {
                        const target = event.target;
                        this._patchActiveTurn({
                            inputCodeSource: target && typeof target.value === 'string' ? target.value : '',
                        });
                    }}
                ></flows-code-editor>
            `;
        }
        return html`
            <div class="grid">
                <platform-field
                    class="full"
                    pill-density="compact"
                    type="enum"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.tester_node')}
                    .hint=${this.t('evaluation.hints.tester_node')}
                    .value=${turn.nodeId}
                    .config=${this._llmNodeEnumConfig('tester')}
                    @change=${(event) => this._patchActiveTurn({ nodeId: this._fieldValue(event) })}
                >
                    <span class="enum-suffix-actions" slot="suffix">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy || turn.nodeId.length === 0}
                            title=${this.t('evaluation.case_editor.edit_tester_node')}
                            aria-label=${this.t('evaluation.case_editor.edit_tester_node')}
                            @click=${() => this._openLlmNodeEditor(turn.nodeId, 'tester')}
                        >
                            <platform-icon name="edit" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy || turn.nodeId.length === 0}
                            title=${this.t('evaluation.case_editor.delete_tester_node')}
                            aria-label=${this.t('evaluation.case_editor.delete_tester_node')}
                            @click=${() => { void this._deleteFlowNode(turn.nodeId, 'tester'); }}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy}
                            title=${this.t('evaluation.case_editor.create_tester_node')}
                            aria-label=${this.t('evaluation.case_editor.create_tester_node')}
                            @click=${() => { void this._createFlowNode('tester'); }}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </platform-button>
                    </span>
                </platform-field>
            </div>
        `;
    }

    _renderCheckEditor(turn) {
        if (turn.checkType === 'contains') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.contains_values')}
                    .hint=${this.t('evaluation.hints.contains_values')}
                    .placeholder=${this.t('evaluation.case_editor.contains_placeholder')}
                    .value=${turn.contains}
                    @change=${(event) => this._patchActiveTurn({ contains: this._fieldValue(event) })}
                ></platform-field>
            `;
        }
        if (turn.checkType === 'not_contains') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.not_contains_values')}
                    .hint=${this.t('evaluation.hints.not_contains_values')}
                    .placeholder=${this.t('evaluation.case_editor.not_contains_placeholder')}
                    .value=${turn.notContains}
                    @change=${(event) => this._patchActiveTurn({ notContains: this._fieldValue(event) })}
                ></platform-field>
            `;
        }
        if (turn.checkType === 'regex') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.regex_pattern')}
                    .hint=${this.t('evaluation.hints.regex_pattern')}
                    .placeholder=${this.t('evaluation.case_editor.regex_placeholder')}
                    .value=${turn.regexPattern}
                    @change=${(event) => this._patchActiveTurn({ regexPattern: this._fieldValue(event) })}
                ></platform-field>
            `;
        }
        if (turn.checkType === 'length') {
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.min_chars')}
                        .hint=${this.t('evaluation.hints.min_chars')}
                        .value=${turn.minChars}
                        @change=${(event) => this._patchActiveTurn({ minChars: this._fieldValue(event) })}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.max_chars')}
                        .hint=${this.t('evaluation.hints.max_chars')}
                        .value=${turn.maxChars}
                        @change=${(event) => this._patchActiveTurn({ maxChars: this._fieldValue(event) })}
                    ></platform-field>
                </div>
            `;
        }
        if (turn.checkType === 'state_path') {
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.state_path')}
                        .hint=${this.t('evaluation.hints.state_path')}
                        .value=${turn.statePath}
                        @change=${(event) => this._patchActiveTurn({ statePath: this._fieldValue(event) })}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.state_operator')}
                        .hint=${this.t('evaluation.hints.state_operator')}
                        .value=${turn.stateOperator}
                        @change=${(event) => this._patchActiveTurn({ stateOperator: this._fieldValue(event) })}
                    ></platform-field>
                </div>
            `;
        }
        if (turn.checkType === 'json_schema') {
            return html`
                <platform-json-editor
                    class="json-schema-editor"
                    validate-json
                    show-toolbar="false"
                    min-height="150"
                    .value=${turn.jsonSchema}
                    @change=${(event) => {
                        if (event.detail && typeof event.detail.value === 'string') {
                            this._patchActiveTurn({ jsonSchema: event.detail.value });
                        }
                    }}
                ></platform-json-editor>
            `;
        }
        if (turn.checkType === 'trace_assertion') {
            return html`
                <div class="grid">
                    <div class="full">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .value=${turn.traceAssertion}
                            .items=${this._traceAssertionItems()}
                            aria-label=${this.t('evaluation.case_editor.trace_assertion_aria')}
                            @change=${(event) => this._patchActiveTurn({ traceAssertion: event.detail.value })}
                        ></platform-segmented-control>
                    </div>
                    <platform-field
                        class="full"
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.trace_value')}
                        .hint=${this.t('evaluation.hints.trace_value')}
                        .placeholder=${this.t('evaluation.case_editor.trace_value_placeholder')}
                        .value=${turn.traceValue}
                        @change=${(event) => this._patchActiveTurn({ traceValue: this._fieldValue(event) })}
                    ></platform-field>
                </div>
            `;
        }
        if (turn.checkType === 'llm_judge') {
            return this._renderJudgeEditor(turn);
        }
        if (turn.checkType === 'builtin_metric') {
            const metrics = this._catalogMetrics();
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.metric_id')}
                        .hint=${this.t('evaluation.hints.metric_id')}
                        .value=${turn.builtinMetricId}
                        @change=${(event) => this._patchActiveTurn({ builtinMetricId: this._fieldValue(event) })}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.reference')}
                        .hint=${this.t('evaluation.hints.reference')}
                        .value=${turn.reference}
                        @change=${(event) => this._patchActiveTurn({ reference: this._fieldValue(event) })}
                    ></platform-field>
                    <div class="full">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .value=${turn.builtinMetricId}
                            .items=${this._builtinMetricItems(metrics)}
                            aria-label=${this.t('evaluation.case_editor.builtin_metric_aria')}
                            @change=${(event) => this._patchActiveTurn({ builtinMetricId: event.detail.value })}
                        ></platform-segmented-control>
                    </div>
                </div>
            `;
        }
        if (turn.checkType === 'code') {
            return html`
                <platform-segmented-control
                    .value=${turn.checkCodeLanguage}
                    .items=${this._codeLanguageItems()}
                    aria-label=${this.t('evaluation.case_editor.code_language_aria')}
                    @change=${(event) => this._patchActiveTurn({ checkCodeLanguage: event.detail.value })}
                ></platform-segmented-control>
                <flows-code-editor
                    class="code"
                    .value=${turn.checkCodeSource}
                    .language=${turn.checkCodeLanguage}
                    @change=${(event) => {
                        const target = event.target;
                        this._patchActiveTurn({
                            checkCodeSource: target && typeof target.value === 'string' ? target.value : '',
                        });
                    }}
                ></flows-code-editor>
            `;
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported render check type ${turn.checkType}`);
    }

    _renderJudgeEditor(turn) {
        return html`
            <div class="grid">
                <platform-field
                    pill-density="compact"
                    type="enum"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.rubric')}
                    .hint=${this.t('evaluation.hints.rubric')}
                    .value=${turn.rubricId}
                    .config=${this._rubricEnumConfig()}
                    @change=${(event) => { void this._onRubricSelected(this._fieldValue(event)); }}
                ></platform-field>
                <platform-field
                    pill-density="compact"
                    type="enum"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.rubric_version')}
                    .hint=${this.t('evaluation.hints.rubric_version_id')}
                    .value=${turn.rubricVersionId}
                    .config=${this._rubricVersionEnumConfig()}
                    @change=${(event) => this._patchActiveTurn({ rubricVersionId: this._fieldValue(event) })}
                ></platform-field>
                <div class="full row-actions">
                    <platform-button
                        variant="secondary"
                        density="compact"
                        @click=${() => { this._showRubricCreate = !this._showRubricCreate; }}
                    >
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('evaluation.case_editor.rubric_create')}
                    </platform-button>
                </div>
                ${this._showRubricCreate ? html`
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.rubric_name')}
                        .value=${this._rubricDraftName}
                        @change=${(event) => { this._rubricDraftName = this._fieldValue(event); }}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.rubric_threshold')}
                        .value=${this._rubricDraftThreshold}
                        @change=${(event) => { this._rubricDraftThreshold = this._fieldValue(event); }}
                    ></platform-field>
                    <platform-field
                        class="full prompt-field"
                        pill-density="compact"
                        type="text"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.rubric_prompt')}
                        .value=${this._rubricDraftPrompt}
                        @change=${(event) => { this._rubricDraftPrompt = this._fieldValue(event); }}
                    ></platform-field>
                    <div class="full row-actions">
                        <platform-button
                            variant="primary"
                            density="compact"
                            ?disabled=${this._rubricCreate.busy}
                            @click=${() => { void this._createRubric(); }}
                        >
                            ${this.t('evaluation.case_editor.rubric_create_save')}
                        </platform-button>
                    </div>
                ` : null}
                <platform-field
                    class="full"
                    pill-density="compact"
                    type="enum"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.judge_node')}
                    .hint=${this.t('evaluation.hints.judge_node')}
                    .value=${turn.judgeNodeId}
                    .config=${this._llmNodeEnumConfig('judge')}
                    @change=${(event) => this._patchActiveTurn({ judgeNodeId: this._fieldValue(event) })}
                >
                    <span class="enum-suffix-actions" slot="suffix">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy || turn.judgeNodeId.length === 0}
                            title=${this.t('evaluation.case_editor.edit_judge_node')}
                            aria-label=${this.t('evaluation.case_editor.edit_judge_node')}
                            @click=${() => this._openLlmNodeEditor(turn.judgeNodeId, 'judge')}
                        >
                            <platform-icon name="edit" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy || turn.judgeNodeId.length === 0}
                            title=${this.t('evaluation.case_editor.delete_judge_node')}
                            aria-label=${this.t('evaluation.case_editor.delete_judge_node')}
                            @click=${() => { void this._deleteFlowNode(turn.judgeNodeId, 'judge'); }}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            ?disabled=${this._nodeBusy || this._flowUpdate.busy}
                            title=${this.t('evaluation.case_editor.create_judge_node')}
                            aria-label=${this.t('evaluation.case_editor.create_judge_node')}
                            @click=${() => { void this._createFlowNode('judge'); }}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </platform-button>
                    </span>
                </platform-field>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-case-editor', FlowsEvaluationCaseEditor);
