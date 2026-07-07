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

function firstTurn(testCase) {
    const turns = asArray(testCase && testCase.turns);
    return turns.length > 0 ? turns[0] : null;
}

function firstCheck(testCase) {
    const turn = firstTurn(testCase);
    const checks = asArray(turn && turn.checks);
    return checks.length > 0 ? checks[0] : null;
}

function inputContent(testCase) {
    const turn = firstTurn(testCase);
    if (!turn || typeof turn !== 'object') {
        return '';
    }
    const input = turn.input;
    if (!input || typeof input !== 'object') {
        return '';
    }
    return stringValue(input, 'content');
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

export class FlowsEvaluationCaseEditor extends PlatformElement {
    static properties = {
        suite: { type: Object },
        testCase: { type: Object },
        catalog: { type: Array },
        busy: { type: Boolean },
        _hydratedCaseId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _input: { state: true },
        _checkType: { state: true },
        _contains: { state: true },
        _notContains: { state: true },
        _regexPattern: { state: true },
        _minChars: { state: true },
        _maxChars: { state: true },
        _statePath: { state: true },
        _stateOperator: { state: true },
        _jsonSchema: { state: true },
        _traceAssertion: { state: true },
        _traceValue: { state: true },
        _rubricVersionId: { state: true },
        _builtinMetricId: { state: true },
        _reference: { state: true },
        _codeLanguage: { state: true },
        _codeSource: { state: true },
        _tags: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        panelShellStyles,
        css`
            :host {
                display: flex;
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
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: 14px;
                display: flex;
                flex-direction: column;
                gap: 12px;
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

            .check-type-scroll {
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
                color: var(--accent);
                background: color-mix(in srgb, var(--accent), transparent 91%);
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
        this._hydratedCaseId = '';
        this._name = '';
        this._description = '';
        this._input = '';
        this._checkType = 'contains';
        this._contains = '';
        this._notContains = '';
        this._regexPattern = '';
        this._minChars = '';
        this._maxChars = '';
        this._statePath = 'response';
        this._stateOperator = 'ne';
        this._jsonSchema = '{\n  \"type\": \"object\"\n}';
        this._traceAssertion = 'tool_called';
        this._traceValue = '';
        this._rubricVersionId = '';
        this._builtinMetricId = 'answer_relevance';
        this._reference = '';
        this._codeLanguage = 'python';
        this._codeSource = 'def evaluate(item, sample):\n    return {\"score\": 1.0, \"passed\": True}\n';
        this._tags = '';
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('testCase')) {
            this._hydrateFromCase();
        }
    }

    _hydrateFromCase() {
        const caseId = stringValue(this.testCase, 'case_id');
        if (caseId === this._hydratedCaseId) {
            return;
        }
        this._hydratedCaseId = caseId;
        this._name = stringValue(this.testCase, 'name');
        this._description = stringValue(this.testCase, 'description');
        this._input = inputContent(this.testCase);
        this._tags = tagsText(this.testCase && this.testCase.tags);
        const check = firstCheck(this.testCase);
        if (!check || typeof check !== 'object') {
            this._checkType = 'contains';
            this._contains = '';
            this._notContains = '';
            this._regexPattern = '';
            this._minChars = '';
            this._maxChars = '';
            this._statePath = 'response';
            this._stateOperator = 'ne';
            this._jsonSchema = '{\n  \"type\": \"object\"\n}';
            this._traceAssertion = 'tool_called';
            this._traceValue = '';
            this._rubricVersionId = '';
            this._builtinMetricId = 'answer_relevance';
            this._reference = '';
            this._codeLanguage = 'python';
            return;
        }
        this._checkType = stringValue(check, 'type');
        if (this._checkType.length === 0) {
            this._checkType = 'contains';
        }
        this._contains = asArray(check.values).filter((item) => typeof item === 'string').join(', ');
        this._notContains = this._checkType === 'not_contains' ? this._contains : '';
        this._regexPattern = stringValue(check, 'pattern');
        this._minChars = optionalNumberText(check.min_chars);
        this._maxChars = optionalNumberText(check.max_chars);
        this._statePath = stringValue(check, 'path').length > 0 ? stringValue(check, 'path') : 'response';
        this._stateOperator = stringValue(check, 'operator').length > 0 ? stringValue(check, 'operator') : 'ne';
        this._jsonSchema = jsonText(check.json_schema);
        this._traceAssertion = stringValue(check, 'assertion').length > 0 ? stringValue(check, 'assertion') : 'tool_called';
        this._traceValue = stringValue(check, 'value');
        this._rubricVersionId = stringValue(check, 'rubric_version_id');
        this._builtinMetricId = stringValue(check, 'evaluator_id').length > 0 ? stringValue(check, 'evaluator_id') : 'answer_relevance';
        this._reference = stringValue(check, 'reference');
        this._codeLanguage = stringValue(check, 'language').length > 0 ? stringValue(check, 'language') : 'python';
        if (this._checkType === 'code' && stringValue(check, 'source').length > 0) {
            this._codeSource = stringValue(check, 'source');
        }
    }

    _fieldValue(event) {
        const detail = event.detail;
        return detail && typeof detail.value === 'string' ? detail.value : '';
    }

    _setCheckType(checkType) {
        this._checkType = checkType;
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

    _onCodeInput(event) {
        const target = event.target;
        this._codeSource = target && typeof target.value === 'string' ? target.value : '';
    }

    _onJsonSchemaInput(event) {
        const target = event.target;
        this._jsonSchema = target && typeof target.value === 'string' ? target.value : '';
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

    _submit() {
        const name = this._name.trim();
        const input = this._input.trim();
        if (name.length === 0 || input.length === 0) {
            this.toast('evaluation.toast.case_required', { type: 'error' });
            return;
        }
        const check = this._buildCheck();
        if (check === null) {
            return;
        }
        const tags = this._tags.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
        const body = {
            name,
            description: this._description,
            branch_ids: '*',
            target: { type: 'flow' },
            initial_state: null,
            turns: this._buildTurns(input, check),
            max_turns: numberValue(this.testCase, 'max_turns', 10),
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

    _buildTurns(input, check) {
        const first = {
            input: { type: 'text', content: input },
            checks: [check],
        };
        const existingTurns = asArray(this.testCase && this.testCase.turns);
        if (existingTurns.length <= 1) {
            return [first];
        }
        return [first, ...existingTurns.slice(1)];
    }

    _buildCheck() {
        if (this._checkType === 'contains') {
            const values = this._contains.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
            if (values.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'contains', source: 'response', values, mode: 'any', case_sensitive: false, state_path: null };
        }
        if (this._checkType === 'not_contains') {
            const values = this._notContains.split(',').map((item) => item.trim()).filter((item) => item.length > 0);
            if (values.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'not_contains', source: 'response', values, case_sensitive: false, state_path: null };
        }
        if (this._checkType === 'regex') {
            const pattern = this._regexPattern.trim();
            if (pattern.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'regex', source: 'response', pattern, ignore_case: true, state_path: null };
        }
        if (this._checkType === 'length') {
            const minChars = this._optionalInt(this._minChars, 'evaluation.toast.length_invalid');
            const maxChars = this._optionalInt(this._maxChars, 'evaluation.toast.length_invalid');
            if (minChars === undefined || maxChars === undefined) {
                return null;
            }
            if (minChars === null && maxChars === null) {
                this.toast('evaluation.toast.length_required', { type: 'error' });
                return null;
            }
            return { type: 'length', source: 'response', min_chars: minChars, max_chars: maxChars, state_path: null };
        }
        if (this._checkType === 'state_path') {
            const path = this._statePath.trim();
            if (path.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'state_path', path, operator: this._stateOperator, value: null };
        }
        if (this._checkType === 'json_schema') {
            try {
                const parsed = JSON.parse(this._jsonSchema);
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
        if (this._checkType === 'trace_assertion') {
            const value = this._traceValue.trim();
            if (value.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'trace_assertion', assertion: this._traceAssertion, value };
        }
        if (this._checkType === 'llm_judge') {
            const rubricVersionId = this._rubricVersionId.trim();
            if (rubricVersionId.length === 0) {
                this.toast('evaluation.toast.rubric_required', { type: 'error' });
                return null;
            }
            return { type: 'llm_judge', rubric_version_id: rubricVersionId, judge_node_id: null, judge_node: null };
        }
        if (this._checkType === 'builtin_metric') {
            return {
                type: 'builtin_metric',
                evaluator_id: this._builtinMetricId,
                source: 'response',
                state_path: null,
                reference: this._reference,
                threshold: null,
                judge_node_id: null,
                judge_node: null,
            };
        }
        if (this._checkType === 'code') {
            const source = this._codeSource.trim();
            if (source.length === 0) {
                this.toast('evaluation.toast.check_required', { type: 'error' });
                return null;
            }
            return { type: 'code', language: this._codeLanguage, source, entrypoint: null };
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported check type ${this._checkType}`);
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
                        <platform-field
                            class="full prompt-field"
                            pill-density="compact"
                            type="text"
                            mode="edit"
                            .label=${this.t('evaluation.case_editor.input')}
                            .hint=${this.t('evaluation.hints.case_input')}
                            .placeholder=${this.t('evaluation.case_editor.input_placeholder')}
                            .value=${this._input}
                            @change=${(event) => { this._input = this._fieldValue(event); }}
                        ></platform-field>
                    </div>

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
                            .value=${this._checkType}
                            .items=${this._checkTypeItems()}
                            aria-label=${this.t('evaluation.case_editor.check_type_aria')}
                            @change=${(event) => this._setCheckType(event.detail.value)}
                        ></platform-segmented-control>
                    </div>

                    ${this._renderCheckEditor()}
                </div>
                <div class="footer">
                    <platform-button variant="primary" density="compact" ?disabled=${this.busy} @click=${this._submit}>
                        <platform-icon name="save" size="14"></platform-icon>
                        ${caseId.length > 0 ? this.t('evaluation.case_editor.save') : this.t('evaluation.case_editor.create')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderCheckEditor() {
        if (this._checkType === 'contains') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.contains_values')}
                    .hint=${this.t('evaluation.hints.contains_values')}
                    .placeholder=${this.t('evaluation.case_editor.contains_placeholder')}
                    .value=${this._contains}
                    @change=${(event) => { this._contains = this._fieldValue(event); }}
                ></platform-field>
            `;
        }
        if (this._checkType === 'not_contains') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.not_contains_values')}
                    .hint=${this.t('evaluation.hints.not_contains_values')}
                    .placeholder=${this.t('evaluation.case_editor.not_contains_placeholder')}
                    .value=${this._notContains}
                    @change=${(event) => { this._notContains = this._fieldValue(event); }}
                ></platform-field>
            `;
        }
        if (this._checkType === 'regex') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.regex_pattern')}
                    .hint=${this.t('evaluation.hints.regex_pattern')}
                    .placeholder=${this.t('evaluation.case_editor.regex_placeholder')}
                    .value=${this._regexPattern}
                    @change=${(event) => { this._regexPattern = this._fieldValue(event); }}
                ></platform-field>
            `;
        }
        if (this._checkType === 'length') {
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.min_chars')}
                        .hint=${this.t('evaluation.hints.min_chars')}
                        .value=${this._minChars}
                        @change=${(event) => { this._minChars = this._fieldValue(event); }}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.max_chars')}
                        .hint=${this.t('evaluation.hints.max_chars')}
                        .value=${this._maxChars}
                        @change=${(event) => { this._maxChars = this._fieldValue(event); }}
                    ></platform-field>
                </div>
            `;
        }
        if (this._checkType === 'state_path') {
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.state_path')}
                        .hint=${this.t('evaluation.hints.state_path')}
                        .value=${this._statePath}
                        @change=${(event) => { this._statePath = this._fieldValue(event); }}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.state_operator')}
                        .hint=${this.t('evaluation.hints.state_operator')}
                        .value=${this._stateOperator}
                        @change=${(event) => { this._stateOperator = this._fieldValue(event); }}
                    ></platform-field>
                </div>
            `;
        }
        if (this._checkType === 'json_schema') {
            return html`
                <platform-json-editor
                    class="json-schema-editor"
                    validate-json
                    show-toolbar="false"
                    min-height="150"
                    .value=${this._jsonSchema}
                    @change=${(event) => {
                        if (event.detail && typeof event.detail.value === 'string') {
                            this._jsonSchema = event.detail.value;
                        }
                    }}
                ></platform-json-editor>
            `;
        }
        if (this._checkType === 'trace_assertion') {
            return html`
                <div class="grid">
                    <div class="full">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .value=${this._traceAssertion}
                            .items=${this._traceAssertionItems()}
                            aria-label=${this.t('evaluation.case_editor.trace_assertion_aria')}
                            @change=${(event) => { this._traceAssertion = event.detail.value; }}
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
                        .value=${this._traceValue}
                        @change=${(event) => { this._traceValue = this._fieldValue(event); }}
                    ></platform-field>
                </div>
            `;
        }
        if (this._checkType === 'llm_judge') {
            return html`
                <platform-field
                    pill-density="compact"
                    type="string"
                    mode="edit"
                    .label=${this.t('evaluation.case_editor.rubric_version_id')}
                    .hint=${this.t('evaluation.hints.rubric_version_id')}
                    .value=${this._rubricVersionId}
                    @change=${(event) => { this._rubricVersionId = this._fieldValue(event); }}
                ></platform-field>
            `;
        }
        if (this._checkType === 'builtin_metric') {
            const metrics = this._catalogMetrics();
            return html`
                <div class="grid">
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.metric_id')}
                        .hint=${this.t('evaluation.hints.metric_id')}
                        .value=${this._builtinMetricId}
                        @change=${(event) => { this._builtinMetricId = this._fieldValue(event); }}
                    ></platform-field>
                    <platform-field
                        pill-density="compact"
                        type="string"
                        mode="edit"
                        .label=${this.t('evaluation.case_editor.reference')}
                        .hint=${this.t('evaluation.hints.reference')}
                        .value=${this._reference}
                        @change=${(event) => { this._reference = this._fieldValue(event); }}
                    ></platform-field>
                    <div class="full">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .value=${this._builtinMetricId}
                            .items=${this._builtinMetricItems(metrics)}
                            aria-label=${this.t('evaluation.case_editor.builtin_metric_aria')}
                            @change=${(event) => { this._builtinMetricId = event.detail.value; }}
                        ></platform-segmented-control>
                    </div>
                </div>
            `;
        }
        if (this._checkType === 'code') {
            return html`
                <platform-segmented-control
                    full-width
                    density="compact"
                    .value=${this._codeLanguage}
                    .items=${this._codeLanguageItems()}
                    aria-label=${this.t('evaluation.case_editor.code_language_aria')}
                    @change=${(event) => { this._codeLanguage = event.detail.value; }}
                ></platform-segmented-control>
                <flows-code-editor
                    language=${this._codeLanguage}
                    .value=${this._codeSource}
                    .showToolbar=${false}
                    .fillParent=${true}
                    @change=${(event) => {
                        if (event.detail && typeof event.detail.value === 'string') {
                            this._codeSource = event.detail.value;
                        }
                    }}
                ></flows-code-editor>
            `;
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported render check type ${this._checkType}`);
    }
}

customElements.define('flows-evaluation-case-editor', FlowsEvaluationCaseEditor);
