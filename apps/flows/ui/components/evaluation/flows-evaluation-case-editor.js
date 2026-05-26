import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-help-hint.js';
import { evaluationCatalogNameKey } from '../../_helpers/evaluation-catalog-labels.js';

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
    return JSON.stringify(value, null, 2);
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
        css`
            :host {
                display: flex;
                min-width: 0;
                min-height: 0;
                color: var(--text-primary);
                --field-pill-bg: color-mix(in srgb, var(--bg-surface), transparent 14%);
                --field-pill-border: var(--border-subtle);
                --field-pill-radius: 14px;
                --field-pill-padding-y: 7px;
                --field-pill-padding-x: 12px;
                --field-pill-gap: 4px;
                --field-pill-gap-textarea: 5px;
                --field-pill-number-spin-height: 32px;
                --field-pill-textarea-min-height: 74px;
                --field-pill-label-size: 10px;
                --field-pill-label-letter: 0;
                --field-pill-input-size: var(--text-sm);
                --field-pill-input-weight: var(--font-medium);
            }

            .panel {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }

            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: linear-gradient(180deg, color-mix(in srgb, var(--glass-solid-medium), transparent 8%), transparent);
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

            .segmented {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
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

            .segmented button,
            .action-btn {
                min-height: 34px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                padding: 0 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .segmented button:hover,
            .action-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .segmented button[data-active="true"] {
                color: var(--text-primary);
                border-color: color-mix(in srgb, var(--accent), transparent 54%);
                background: color-mix(in srgb, var(--accent), transparent 86%);
            }

            .code {
                min-height: 128px;
                resize: vertical;
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--bg-surface), transparent 12%);
                color: var(--text-primary);
                font: 13px/1.45 var(--font-mono);
                outline: none;
            }

            .json {
                min-height: 150px;
            }

            .code:focus {
                border-color: var(--accent);
                box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent), transparent 78%);
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

            .action-btn.primary {
                background: var(--accent);
                color: var(--text-inverse);
                border-color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .action-btn.primary:hover {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
                box-shadow: var(--accent-glow);
            }

            .action-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                box-shadow: none;
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
                <section class="panel">
                    <div class="empty">
                        <span class="empty-mark"><platform-icon name="checklist" size="20"></platform-icon></span>
                        <span>${this.t('evaluation.case_editor.no_suite')}</span>
                    </div>
                </section>
            `;
        }
        const caseId = stringValue(this.testCase, 'case_id');
        return html`
            <section class="panel">
                <div class="head">
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
                    <div class="segmented">
                        ${this._renderCheckButton('contains', 'search-check', this.t('evaluation.case_editor.check_contains'))}
                        ${this._renderCheckButton('not_contains', 'shield', this.t('evaluation.case_editor.check_not_contains'))}
                        ${this._renderCheckButton('regex', 'code', this.t('evaluation.case_editor.check_regex'))}
                        ${this._renderCheckButton('length', 'list', this.t('evaluation.case_editor.check_length'))}
                        ${this._renderCheckButton('state_path', 'braces', this.t('evaluation.case_editor.check_state'))}
                        ${this._renderCheckButton('json_schema', 'table', this.t('evaluation.case_editor.check_json_schema'))}
                        ${this._renderCheckButton('trace_assertion', 'activity', this.t('evaluation.case_editor.check_trace'))}
                        ${this._renderCheckButton('builtin_metric', 'badge-check', this.t('evaluation.case_editor.check_builtin'))}
                        ${this._renderCheckButton('llm_judge', 'sparkles', this.t('evaluation.case_editor.check_judge'))}
                        ${this._renderCheckButton('code', 'code', this.t('evaluation.case_editor.check_code'))}
                    </div>

                    ${this._renderCheckEditor()}
                </div>
                <div class="footer">
                    <button class="action-btn primary" type="button" ?disabled=${this.busy} @click=${this._submit}>
                        <platform-icon name="save" size="14"></platform-icon>
                        ${caseId.length > 0 ? this.t('evaluation.case_editor.save') : this.t('evaluation.case_editor.create')}
                    </button>
                </div>
            </section>
        `;
    }

    _renderCheckButton(checkType, icon, label) {
        return html`
            <button type="button" data-active=${this._checkType === checkType ? 'true' : 'false'} @click=${() => this._setCheckType(checkType)}>
                <platform-icon name=${icon} size="14"></platform-icon>
                ${label}
            </button>
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
                <textarea
                    class="code json"
                    data-canon="code-editor"
                    spellcheck="false"
                    aria-label=${this.t('evaluation.case_editor.json_schema')}
                    .value=${this._jsonSchema}
                    @input=${this._onJsonSchemaInput}
                ></textarea>
            `;
        }
        if (this._checkType === 'trace_assertion') {
            return html`
                <div class="grid">
                    <div class="full segmented">
                        ${this._renderTraceButton('tool_called', this.t('evaluation.case_editor.trace_tool_called'))}
                        ${this._renderTraceButton('node_completed', this.t('evaluation.case_editor.trace_node_completed'))}
                        ${this._renderTraceButton('node_failed', this.t('evaluation.case_editor.trace_node_failed'))}
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
                    <div class="full segmented">
                        ${metrics.map((item) => this._renderMetricChip(item))}
                    </div>
                </div>
            `;
        }
        if (this._checkType === 'code') {
            return html`
                <div class="segmented">
                    ${this._renderLanguageButton('python')}
                    ${this._renderLanguageButton('javascript')}
                    ${this._renderLanguageButton('typescript')}
                    ${this._renderLanguageButton('go')}
                    ${this._renderLanguageButton('csharp')}
                </div>
                <textarea
                    class="code"
                    data-canon="code-editor"
                    spellcheck="false"
                    aria-label=${this.t('evaluation.case_editor.code_source')}
                    .value=${this._codeSource}
                    @input=${this._onCodeInput}
                ></textarea>
            `;
        }
        throw new Error(`FlowsEvaluationCaseEditor: unsupported render check type ${this._checkType}`);
    }

    _renderMetricChip(item) {
        const metricId = stringValue(item, 'evaluator_id');
        return html`
            <button type="button" data-active=${this._builtinMetricId === metricId ? 'true' : 'false'} @click=${() => { this._builtinMetricId = metricId; }}>
                ${this.t(evaluationCatalogNameKey(metricId))}
            </button>
        `;
    }

    _renderTraceButton(assertion, label) {
        return html`
            <button type="button" data-active=${this._traceAssertion === assertion ? 'true' : 'false'} @click=${() => { this._traceAssertion = assertion; }}>
                ${label}
            </button>
        `;
    }

    _renderLanguageButton(language) {
        return html`
            <button type="button" data-active=${this._codeLanguage === language ? 'true' : 'false'} @click=${() => { this._codeLanguage = language; }}>
                <platform-icon name=${language} size="14"></platform-icon>
                ${language}
            </button>
        `;
    }
}

customElements.define('flows-evaluation-case-editor', FlowsEvaluationCaseEditor);
