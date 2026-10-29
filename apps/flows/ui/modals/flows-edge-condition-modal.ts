/**
 * flows-edge-condition-modal — редактирование условия перехода ребра.
 *
 * Открывается:
 *   - кликом по подписи ребра на канвасе (если condition уже задан);
 *   - из контекстного меню ребра (`edit_condition`).
 *
 * Два режима:
 *   - Простой: variable + operator + value → сохраняется как
 *     `{type: 'simple', variable, operator, value}`.
 *   - Code: функция `check(args, state)` в языке isolated runner → сохраняется
 *     как `{type: 'code', language, code}`.
 *
 * Ссылка пропуска очищает условие (`null`).
 *
 * Сохранение идёт в editor-resource: `updateBranchData` с новым
 * `edges[edgeIndex].condition` + `setDirty: true`. UI читает legacy `type=python`,
 * но сохраняет новый `type=code`.
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import '../components/editors/flows-code-editor.js';
import { getEdgeEndpoints, isPlainObject } from '../_helpers/flows-resolvers.js';
import {
    listReflectionExits,
    syncReflectionEdgeFromPort,
} from '../_helpers/flows-reflection-defaults.js';
import {
    FLOW_CODE_LANGUAGES,
    edgeConditionStarterCodeForLanguage,
    isKnownEdgeConditionStarterCode,
    normalizeFlowCodeLanguage,
} from '../_helpers/flows-code-languages.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

function branchRecord(value: unknown): Record<string, unknown> | null {
    if (!isPlainObject(value)) return null;
    const row: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

const OPERATORS = Object.freeze(['==', '!=', '>', '<', '>=', '<=', 'in']);

const STD_STATE_FIELDS = Object.freeze([
    'content',
    'route',
    'status',
    'result',
    'category',
    'type',
]);

function quoteValue(value: unknown) {
    if (value === null || value === undefined) return "''";
    const str = String(value);
    if (str.length === 0) return "''";
    if (!Number.isNaN(Number(str))) return str;
    return `'${str}'`;
}

export class FlowsEdgeConditionModal extends PlatformFormModal {
    static modalKind = 'flows.edge_condition';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        edgeIndex: { type: Number },
        _mode: { state: true },
        _variable: { state: true },
        _operator: { state: true },
        _value: { state: true },
        _pythonCode: { state: true },
        _codeLanguage: { state: true },
        _hydrated: { state: true },
        _codeValidationStatus: { state: true },
        _codeValidationMessage: { state: true },
    }
    declare edgeIndex: number;
    declare _mode: string;
    declare _variable: string;
    declare _operator: string;
    declare _value: string;
    declare _pythonCode: string;
    declare _codeLanguage: string;
    declare _hydrated: boolean;
    declare _codeValidationStatus: string;
    declare _codeValidationMessage: string;
;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        glassStyles,
        ...formStyles,
        css`
            .modal-content { padding: var(--space-5) var(--space-6); }

            .condition-header {
                margin-bottom: var(--space-4);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
            }
            .condition-header h3 {
                margin: 0 0 var(--space-1);
                font-size: var(--text-md);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .condition-subtitle {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                font-family: var(--font-mono);
            }

            .condition-mode {
                margin-bottom: var(--space-4);
            }

            .builder-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(88px, 120px) minmax(0, 1fr);
                gap: var(--space-3);
                align-items: start;
            }
            .builder-cell {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .python-mode { margin-top: var(--space-2); }
            .code-mode-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .code-validation-status {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                min-width: 0;
                max-width: 260px;
                height: 28px;
                padding: 0 9px;
                box-sizing: border-box;
                border-radius: var(--radius-full, 999px);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1;
                white-space: nowrap;
            }
            .code-validation-status[data-state='valid'] {
                color: var(--success);
                background: var(--success-bg);
                border-color: var(--success-border);
            }
            .code-validation-status[data-state='invalid'] {
                color: var(--error);
                background: var(--error-bg);
                border-color: var(--error-border);
            }
            .code-validation-text {
                overflow: hidden;
                text-overflow: ellipsis;
            }
            flows-code-editor { display: block; min-height: 200px; }
            .python-hint {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.5;
            }

            .condition-preview {
                margin-top: var(--space-4);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
            }
            .preview-label {
                margin-bottom: var(--space-1);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .preview-code {
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                color: var(--accent);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-sm);
            }
            .preview-code.empty { color: var(--text-tertiary); font-style: italic; }

            .skip-condition { margin-top: var(--space-3); text-align: center; }
            .skip-link {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                cursor: pointer;
                text-decoration: underline;
            }
            .skip-link:hover { color: var(--text-primary); }

            .variables-hint {
                margin-top: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .variables-hint strong { color: var(--text-primary); }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _codeValidateOp: OpController;
    private _codeValidationTimer: number;
    private _codeValidationSeq: number;

    constructor() {
        super();
        this.edgeIndex = -1;
        this._mode = 'simple';
        this._variable = '';
        this._operator = '==';
        this._value = '';
        this._codeLanguage = 'python';
        this._pythonCode = edgeConditionStarterCodeForLanguage(this._codeLanguage);
        this._hydrated = false;
        this._codeValidationStatus = 'idle';
        this._codeValidationMessage = '';
        this._codeValidationTimer = 0;
        this._codeValidationSeq = 0;
        this._editor = this.useOp('flows/editor');
        this._codeValidateOp = this.useOp('flows/code_validate');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('_pythonCode') || changed.has('_codeLanguage') || changed.has('_mode')) {
            this._scheduleCodeValidation();
        }
        if (this._hydrated || this.edgeIndex < 0) return;
        const edges = this._currentEdges();
        const edge = edges[this.edgeIndex];
        if (!isPlainObject(edge)) return;
        this._loadCondition(edge.condition);
        this._hydrated = true;
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
    }

    _currentEdges(): unknown[] {
        const data = branchRecord(this._editor.state?.branchData);
        if (data === null || !Array.isArray(data.edges)) return [];
        return data.edges;
    }

    _currentEdge() {
        const edges = this._currentEdges();
        if (this.edgeIndex < 0 || this.edgeIndex >= edges.length) return null;
        return edges[this.edgeIndex];
    }

    _loadCondition(condition: unknown) {
        if (condition === null || condition === undefined || condition === '') {
            this._mode = 'simple';
            this._variable = '';
            this._operator = '==';
            this._value = '';
            this._codeLanguage = 'python';
            this._pythonCode = edgeConditionStarterCodeForLanguage(this._codeLanguage);
            return;
        }
        if (isPlainObject(condition)) {
            const type = condition.type;
            if (type === 'code') {
                this._mode = 'python';
                this._codeLanguage = normalizeFlowCodeLanguage(condition.language);
                this._pythonCode = typeof condition.code === 'string' && condition.code.length > 0
                    ? condition.code
                    : edgeConditionStarterCodeForLanguage(this._codeLanguage);
                return;
            }
            if (type === 'simple') {
                this._mode = 'simple';
                this._variable = typeof condition.variable === 'string' ? condition.variable : '';
                this._operator = typeof condition.operator === 'string' ? condition.operator : '==';
                this._value = condition.value === undefined || condition.value === null
                    ? ''
                    : String(condition.value);
                return;
            }
        }
        throw new TypeError('flows-edge-condition-modal: edge.condition must be a typed object');
    }

    _collectVariables() {
        const set = new Set<string>();
        const data = branchRecord(this._editor.state?.branchData);
        if (data !== null) {
            const variables = data.variables;
            if (isPlainObject(variables)) {
                for (const key of Object.keys(variables)) {
                    set.add(`variables.${key}`);
                }
            }
            const edge = this._currentEdge();
            if (isPlainObject(edge)) {
                const { from_node: fromId } = getEdgeEndpoints(edge);
                const nodes = data.nodes;
                const sourceNode = fromId.length > 0 && isPlainObject(nodes) ? nodes[fromId] : null;
                if (isPlainObject(sourceNode) && isPlainObject(sourceNode.config)) {
                    const mapping = sourceNode.config.output_mapping;
                    if (isPlainObject(mapping)) {
                        for (const target of Object.values(mapping)) {
                            if (typeof target === 'string' && target.length > 0) {
                                set.add(target);
                            }
                        }
                    }
                    const schema = sourceNode.config.output_schema;
                    if (sourceNode.config.structured_output === true && isPlainObject(schema) && isPlainObject(schema.properties) && !isPlainObject(mapping)) {
                        for (const prop of Object.keys(schema.properties)) {
                            set.add(prop);
                        }
                    }
                }
            }
        }
        for (const std of STD_STATE_FIELDS) set.add(std);
        return Array.from(set).sort();
    }

    _buildConditionValue() {
        if (this._mode === 'python') {
            return {
                type: 'code',
                language: normalizeFlowCodeLanguage(this._codeLanguage),
                code: this._pythonCode,
            };
        }
        if (this._variable.length === 0 || this._value.length === 0) {
            return null;
        }
        return {
            type: 'simple',
            variable: this._variable,
            operator: this._operator,
            value: this._value,
        };
    }

    _previewText() {
        if (this._mode === 'python') return this.t('edge_condition_modal.preview_python');
        if (this._variable.length === 0 || this._value.length === 0) return '';
        return `${this._variable} ${this._operator} ${quoteValue(this._value)}`;
    }

    override validateForm() {
        const errors: Record<string, string> = {};
        if (this._mode === 'simple') {
            if (this._variable.length === 0 && this._value.length > 0) {
                errors.variable = this.t('edge_condition_modal.err_variable');
            }
            if (this._variable.length > 0 && this._value.length === 0) {
                errors.value = this.t('edge_condition_modal.err_value');
            }
        } else if (this._mode === 'python') {
            if (this._pythonCode.trim().length === 0) {
                errors.code = this.t('edge_condition_modal.err_code');
            } else if (this._codeValidationStatus === 'pending') {
                errors.code = this.t('code_workbench.validation_checking');
            } else if (this._codeValidationStatus === 'invalid') {
                errors.code = this._codeValidationMessage;
            }
        }
        return errors;
    }

    override async handleSubmit() {
        this._persist(this._buildConditionValue());
    }

    _persist(condition: unknown) {
        const data = branchRecord(this._editor.state?.branchData);
        if (data === null || this.edgeIndex < 0) {
            this.closeAfterSave();
            return;
        }
        const edges: unknown[] = Array.isArray(data.edges) ? [...data.edges] : [];
        if (this.edgeIndex >= edges.length) {
            this.closeAfterSave();
            return;
        }
        const currentEdge = edges[this.edgeIndex];
        edges[this.edgeIndex] = syncReflectionEdgeFromPort(
            currentEdge,
            condition,
            this._reflectionAllowedExitIds(data, currentEdge),
        );
        this._editor.updateBranchData({ data: { ...data, edges } });
        this._editor.setDirty({ dirty: true });
        this.closeAfterSave();
    }

    _reflectionAllowedExitIds(branchData: Record<string, unknown>, edge: unknown): string[] | null {
        if (!isPlainObject(edge)) {
            return null;
        }
        const fromNodeId = typeof edge.from_node === 'string' && edge.from_node.length > 0 ? edge.from_node : null;
        if (fromNodeId === null) {
            return null;
        }
        const nodes = branchData.nodes;
        if (!isPlainObject(nodes)) {
            return null;
        }
        const node = nodes[fromNodeId];
        if (!isPlainObject(node) || node.type !== 'reflection') {
            return null;
        }
        const policy = isPlainObject(node.critic_policy) ? node.critic_policy : null;
        return listReflectionExits(policy).map((item: { id: unknown }) => {
            if (typeof item.id !== 'string' || item.id.length === 0) {
                throw new Error('flows-edge-condition-modal: reflection exit id required');
            }
            return item.id;
        });
    }

    _onModeChange(mode: string) {
        if (this._mode === mode) return;
        this._mode = mode;
        this.isDirty = true;
    }

    _onVariableChange(e: CustomEvent) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: variable change expects string detail.value');
        }
        this._variable = v;
        this.isDirty = true;
    }

    _onOperatorChange(e: CustomEvent) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: operator change expects string detail.value');
        }
        this._operator = v;
        this.isDirty = true;
    }

    _onValueInput(e: CustomEvent) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: value change expects string detail.value');
        }
        this._value = v;
        this.isDirty = true;
    }

    _onPythonChange(e: CustomEvent) {
        const next = e.detail?.value;
        if (typeof next !== 'string') return;
        this._pythonCode = next;
        this.isDirty = true;
    }

    _setCodeLanguage(language: unknown) {
        const normalized = normalizeFlowCodeLanguage(language);
        if (this._codeLanguage === normalized) {
            return;
        }
        const currentCode = this._pythonCode;
        this._codeLanguage = normalized;
        if (currentCode.trim().length === 0 || isKnownEdgeConditionStarterCode(currentCode)) {
            this._pythonCode = edgeConditionStarterCodeForLanguage(normalized);
        }
        this.isDirty = true;
    }

    _validationPayload() {
        return {
            code: this._pythonCode,
            language: normalizeFlowCodeLanguage(this._codeLanguage),
            kind: 'node',
            node_type: 'code',
            entrypoint: 'check',
        };
    }

    _scheduleCodeValidation() {
        if (this._codeValidationTimer) {
            window.clearTimeout(this._codeValidationTimer);
            this._codeValidationTimer = 0;
        }
        if (this._mode !== 'python' || this._pythonCode.trim().length === 0) {
            this._codeValidationSeq += 1;
            this._codeValidationStatus = 'idle';
            this._codeValidationMessage = '';
            return;
        }
        this._codeValidationStatus = 'pending';
        this._codeValidationMessage = this.t('code_workbench.validation_checking');
        this._codeValidationTimer = window.setTimeout(() => {
            this._codeValidationTimer = 0;
            void this._runCodeValidation();
        }, 650);
    }

    async _runCodeValidation() {
        const seq = this._codeValidationSeq + 1;
        this._codeValidationSeq = seq;
        let result;
        try {
            result = await this._codeValidateOp.run(this._validationPayload());
        } catch (err) {
            if (seq !== this._codeValidationSeq) {
                return;
            }
            this._codeValidationStatus = 'invalid';
            this._codeValidationMessage = err instanceof Error ? err.message : String(err);
            return;
        }
        if (seq !== this._codeValidationSeq) {
            return;
        }
        const outcome = isPlainObject(result) ? result : null;
        if (outcome === null || outcome.valid !== true) {
            const error = outcome === null ? undefined : outcome.error;
            const message = typeof error === 'string'
                ? error
                : this.t('code_workbench.validation_invalid');
            this._codeValidationStatus = 'invalid';
            this._codeValidationMessage = message;
            return;
        }
        this._codeValidationStatus = 'valid';
        this._codeValidationMessage = this.t('code_workbench.validation_valid');
    }

    _renderValidationStatus() {
        const status = this._codeValidationStatus;
        if (status === 'idle') {
            return '';
        }
        let iconName = 'circle';
        let label = this._codeValidationMessage;
        if (status === 'pending') {
            label = this.t('code_workbench.validation_checking');
        } else if (status === 'valid') {
            iconName = 'check';
            label = this.t('code_workbench.validation_valid');
        } else if (status === 'invalid') {
            iconName = 'alert-triangle';
            if (typeof label !== 'string' || label.length === 0) {
                label = this.t('code_workbench.validation_invalid');
            }
        }
        return html`
            <span class="code-validation-status glass-subtle" data-state=${status} title=${label}>
                <platform-icon name=${iconName} size="14"></platform-icon>
                <span class="code-validation-text">${label}</span>
            </span>
        `;
    }

    _renderCodeLanguageSegment() {
        const current = normalizeFlowCodeLanguage(this._codeLanguage);
        return html`
            <platform-segmented-control
                density="compact"
                .value=${current}
                .items=${FLOW_CODE_LANGUAGES.map((lang) => ({
                    value: lang.value,
                    label: lang.label,
                    title: lang.label,
                }))}
                aria-label=${this.t('code_workbench.language_aria')}
                @change=${(e: CustomEvent) => this._setCodeLanguage(e.detail.value)}
            ></platform-segmented-control>
        `;
    }

    _onSkip() {
        this._persist(null);
    }

    override renderHeader() {
        return html`<span>${this.t('edge_condition_modal.title')}</span>`;
    }

    override _saveHeaderTitle() {
        return this.t('edge_condition_modal.save_header_title');
    }

    override renderBody() {
        const edge = this._currentEdge();
        const { from_node: fromId, to_node: toId } = edge
            ? getEdgeEndpoints(edge)
            : { from_node: '', to_node: '' };
        const preview = this._previewText();
        const sep = this.t('edge_condition_modal.subtitle_separator');
        return html`
            <div class="condition-header">
                <h3>${this.t('edge_condition_modal.heading')}</h3>
                <div class="condition-subtitle">${fromId} ${sep} ${toId}</div>
            </div>

            <platform-segmented-control
                class="condition-mode"
                full-width
                density="compact"
                .value=${this._mode}
                .items=${[
                    { value: 'simple', label: this.t('edge_condition_modal.mode_simple') },
                    { value: 'python', label: this.t('edge_condition_modal.mode_python') },
                ]}
                aria-label=${this.t('edge_condition_modal.mode_aria')}
                @change=${(e: CustomEvent) => this._onModeChange(e.detail.value)}
            ></platform-segmented-control>

            <form @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                ${this._mode === 'simple' ? this._renderSimple() : this._renderPython()}

                <div class="condition-preview">
                    <div class="preview-label">${this.t('edge_condition_modal.preview_label')}</div>
                    <div class="preview-code glass-subtle ${preview.length === 0 ? 'empty' : ''}">${preview.length === 0 ? this.t('edge_condition_modal.preview_empty') : preview}</div>
                </div>

                <div class="skip-condition">
                    <span class="skip-link" @click=${this._onSkip}>${this.t('edge_condition_modal.skip_no_condition')}</span>
                </div>
            </form>
        `;
    }

    _renderSimple() {
        const variables = this._collectVariables();
        const variableEnumConfig = {
            values: [
                { value: '', label: this.t('edge_condition_modal.select_placeholder') },
                ...variables.map((v) => ({ value: v, label: v })),
            ],
        };
        const operatorEnumConfig = {
            values: OPERATORS.map((op) => ({ value: op, label: op })),
        };
        return html`
            <div class="builder-row">
                <div class="builder-cell">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('edge_condition_modal.label_variable')}
                        .value=${this._variable}
                        .config=${variableEnumConfig}
                        .error=${this.fieldError('variable')}
                        @change=${this._onVariableChange}
                    ></platform-field>
                </div>
                <div class="builder-cell">
                    <platform-field
                        type="enum"
                        mode="edit"
                        .label=${this.t('edge_condition_modal.label_operator')}
                        .value=${this._operator}
                        .config=${operatorEnumConfig}
                        @change=${this._onOperatorChange}
                    ></platform-field>
                </div>
                <div class="builder-cell">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('edge_condition_modal.label_value')}
                        .value=${this._value}
                        placeholder=${this.t('edge_condition_modal.value_placeholder')}
                        .error=${this.fieldError('value')}
                        @change=${this._onValueInput}
                    ></platform-field>
                </div>
            </div>
            ${variables.length > 0 ? html`
                <div class="variables-hint">
                    <strong>${this.t('edge_condition_modal.variables_available')}</strong>
                    ${variables.slice(0, 6).join(', ')}${variables.length > 6 ? '…' : ''}
                </div>
            ` : ''}
        `;
    }

    _renderPython() {
        return html`
            <div class="python-mode">
                <div class="code-mode-head">
                    ${this._renderValidationStatus()}
                    ${this._renderCodeLanguageSegment()}
                </div>
                <flows-code-editor
                    .value=${this._pythonCode}
                    .language=${normalizeFlowCodeLanguage(this._codeLanguage)}
                    @change=${this._onPythonChange}
                ></flows-code-editor>
                <div class="python-hint">
                    ${this.t('edge_condition_modal.python_hint_1')}
                    <br>${this.t('edge_condition_modal.python_hint_2')}
                </div>
                ${this.renderFieldError('code')}
            </div>
        `;
    }

    override renderFooter(): TemplateResult {
        return html``;
    }
}

customElements.define('flows-edge-condition-modal', FlowsEdgeConditionModal);
registerModalKind(FlowsEdgeConditionModal.modalKind, 'flows-edge-condition-modal');
