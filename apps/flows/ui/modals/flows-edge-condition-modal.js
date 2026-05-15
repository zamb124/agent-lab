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
 *   - Python: код функции `def check(state) -> bool:` → сохраняется
 *     как `{type: 'python', code}`.
 *
 * Skip-link очищает условие (`null`).
 *
 * Сохранение идёт в editor-resource: `updateBranchData` с новым
 * `edges[edgeIndex].condition` + `setDirty: true`. Backend хранит поле в
 * `Edge.condition: Optional[Union[str, Dict]]` и понимает оба формата.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/editors/flows-code-editor.js';
import { getEdgeEndpoints } from '../_helpers/flows-resolvers.js';

const DEFAULT_PYTHON_CODE = `def check(state):
    """
    Edge transition condition.

    Args:
        state: dict - current execution state

    Returns:
        bool - True when the condition is met
    """
    return state.get('route') == 'expected_value'
`;

const OPERATORS = Object.freeze(['==', '!=', '>', '<', '>=', '<=', 'in']);

const STD_STATE_FIELDS = Object.freeze([
    'content',
    'route',
    'status',
    'result',
    'category',
    'type',
]);

function quoteValue(value) {
    if (value === null || value === undefined) return "''";
    const str = String(value);
    if (str.length === 0) return "''";
    if (!Number.isNaN(Number(str))) return str;
    return `'${str}'`;
}

function parseLegacyString(condition) {
    if (typeof condition !== 'string' || condition.length === 0) {
        return { variable: '', operator: '==', value: '' };
    }
    for (const op of ['!=', '>=', '<=', '==', '>', '<', 'in']) {
        const sep = ` ${op} `;
        const idx = condition.indexOf(sep);
        if (idx > 0) {
            const variable = condition.slice(0, idx).trim();
            const raw = condition.slice(idx + sep.length).trim();
            const value = raw.replace(/^['"]|['"]$/g, '');
            return { variable, operator: op, value };
        }
    }
    return { variable: '', operator: '==', value: '' };
}

export class FlowsEdgeConditionModal extends PlatformFormModal {
    static modalKind = 'flows.edge_condition';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        edgeIndex: { type: Number },
        _mode: { state: true },
        _variable: { state: true },
        _operator: { state: true },
        _value: { state: true },
        _pythonCode: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
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
                font-family: var(--font-mono, monospace);
            }

            .mode-tabs {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }
            .mode-tab {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                text-align: center;
            }
            .mode-tab:hover { color: var(--text-primary); border-color: var(--border-medium); }
            .mode-tab.active {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: var(--accent);
            }

            .builder-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(88px, 120px) minmax(0, 1fr);
                gap: var(--space-3);
                align-items: end;
            }
            .form-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }
            .form-field label {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                overflow-wrap: anywhere;
            }
            select, input {
                width: 100%;
                box-sizing: border-box;
                height: 36px;
                padding: 0 var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                font: inherit;
            }
            select:focus, input:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-light);
            }

            .python-mode { margin-top: var(--space-2); }
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
                font-family: var(--font-mono, monospace);
                font-size: var(--text-sm);
                color: var(--accent);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
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

            .form-error {
                margin-top: var(--space-1);
                font-size: var(--text-xs);
                color: var(--error);
            }
        `,
    ];

    constructor() {
        super();
        this.edgeIndex = -1;
        this._mode = 'simple';
        this._variable = '';
        this._operator = '==';
        this._value = '';
        this._pythonCode = DEFAULT_PYTHON_CODE;
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (this._hydrated || this.edgeIndex < 0) return;
        const edges = this._currentEdges();
        const edge = edges[this.edgeIndex];
        if (!edge) return;
        this._loadCondition(edge.condition);
        this._hydrated = true;
    }

    _currentEdges() {
        const data = this._editor.state?.branchData;
        if (!data || !Array.isArray(data.edges)) return [];
        return data.edges;
    }

    _currentEdge() {
        const edges = this._currentEdges();
        if (this.edgeIndex < 0 || this.edgeIndex >= edges.length) return null;
        return edges[this.edgeIndex];
    }

    _loadCondition(condition) {
        if (condition === null || condition === undefined || condition === '') {
            this._mode = 'simple';
            this._variable = '';
            this._operator = '==';
            this._value = '';
            this._pythonCode = DEFAULT_PYTHON_CODE;
            return;
        }
        if (typeof condition === 'object') {
            const type = condition.type;
            if (type === 'python') {
                this._mode = 'python';
                this._pythonCode = typeof condition.code === 'string' && condition.code.length > 0
                    ? condition.code
                    : DEFAULT_PYTHON_CODE;
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
        if (typeof condition === 'string') {
            const parsed = parseLegacyString(condition);
            this._mode = 'simple';
            this._variable = parsed.variable;
            this._operator = parsed.operator;
            this._value = parsed.value;
            return;
        }
    }

    _collectVariables() {
        const set = new Set();
        const data = this._editor.state?.branchData;
        if (data) {
            const variables = data.variables;
            if (variables && typeof variables === 'object') {
                for (const key of Object.keys(variables)) {
                    set.add(`variables.${key}`);
                }
            }
            const edge = this._currentEdge();
            if (edge) {
                const { from: fromId } = getEdgeEndpoints(edge);
                const sourceNode = fromId && data.nodes ? data.nodes[fromId] : null;
                if (sourceNode && sourceNode.config) {
                    const mapping = sourceNode.config.output_mapping;
                    if (mapping && typeof mapping === 'object') {
                        for (const target of Object.values(mapping)) {
                            if (typeof target === 'string' && target.length > 0) {
                                set.add(target);
                            }
                        }
                    }
                    const schema = sourceNode.config.output_schema;
                    if (sourceNode.config.structured_output && schema && schema.properties && !mapping) {
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
            return { type: 'python', code: this._pythonCode };
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

    validateForm() {
        const errors = {};
        if (this._mode === 'simple') {
            if (this._variable.length === 0 && this._value.length > 0) {
                errors.variable = this.t('edge_condition_modal.err_variable');
            }
            if (this._variable.length > 0 && this._value.length === 0) {
                errors.value = this.t('edge_condition_modal.err_value');
            }
        } else if (this._mode === 'python') {
            if (this._pythonCode.indexOf('def check') < 0) {
                errors.code = this.t('edge_condition_modal.err_code');
            }
        }
        return errors;
    }

    async handleSubmit() {
        this._persist(this._buildConditionValue());
    }

    _persist(condition) {
        const data = this._editor.state?.branchData;
        if (!data || this.edgeIndex < 0) {
            this.closeAfterSave();
            return;
        }
        const edges = Array.isArray(data.edges) ? [...data.edges] : [];
        if (this.edgeIndex >= edges.length) {
            this.closeAfterSave();
            return;
        }
        edges[this.edgeIndex] = { ...edges[this.edgeIndex], condition };
        this._editor.updateBranchData({ data: { ...data, edges } });
        this._editor.setDirty({ dirty: true });
        this.closeAfterSave();
    }

    _onModeChange(mode) {
        if (this._mode === mode) return;
        this._mode = mode;
        this.isDirty = true;
    }

    _onVariableChange(e) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: variable change expects string detail.value');
        }
        this._variable = v;
        this.isDirty = true;
    }

    _onOperatorChange(e) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: operator change expects string detail.value');
        }
        this._operator = v;
        this.isDirty = true;
    }

    _onValueInput(e) {
        const v = e.detail.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-edge-condition-modal: value change expects string detail.value');
        }
        this._value = v;
        this.isDirty = true;
    }

    _onPythonChange(e) {
        const next = e.detail?.value;
        if (typeof next !== 'string') return;
        this._pythonCode = next;
        this.isDirty = true;
    }

    _onSkip() {
        this._persist(null);
    }

    renderHeader() {
        return html`<span>${this.t('edge_condition_modal.title')}</span>`;
    }

    _saveHeaderTitle() {
        return this.t('edge_condition_modal.save_header_title');
    }

    renderBody() {
        const edge = this._currentEdge();
        const { from: fromId, to: toId } = edge ? getEdgeEndpoints(edge) : { from: '', to: '' };
        const preview = this._previewText();
        const sep = this.t('edge_condition_modal.subtitle_separator');
        return html`
            <div class="condition-header">
                <h3>${this.t('edge_condition_modal.heading')}</h3>
                <div class="condition-subtitle">${fromId} ${sep} ${toId}</div>
            </div>

            <div class="mode-tabs">
                <button
                    type="button"
                    class="mode-tab ${this._mode === 'simple' ? 'active' : ''}"
                    @click=${() => this._onModeChange('simple')}
                >${this.t('edge_condition_modal.mode_simple')}</button>
                <button
                    type="button"
                    class="mode-tab ${this._mode === 'python' ? 'active' : ''}"
                    @click=${() => this._onModeChange('python')}
                >${this.t('edge_condition_modal.mode_python')}</button>
            </div>

            <form @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                ${this._mode === 'simple' ? this._renderSimple() : this._renderPython()}

                <div class="condition-preview">
                    <div class="preview-label">${this.t('edge_condition_modal.preview_label')}</div>
                    <div class="preview-code ${preview.length === 0 ? 'empty' : ''}">${preview.length === 0 ? this.t('edge_condition_modal.preview_empty') : preview}</div>
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
                <div class="form-field">
                    <label>${this.t('edge_condition_modal.label_variable')}</label>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .value=${this._variable}
                        .config=${variableEnumConfig}
                        @change=${this._onVariableChange}
                    ></platform-field>
                    ${this.renderFieldError('variable')}
                </div>
                <div class="form-field">
                    <label>${this.t('edge_condition_modal.label_operator')}</label>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .value=${this._operator}
                        .config=${operatorEnumConfig}
                        @change=${this._onOperatorChange}
                    ></platform-field>
                </div>
                <div class="form-field">
                    <label>${this.t('edge_condition_modal.label_value')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${this._value}
                        placeholder=${this.t('edge_condition_modal.value_placeholder')}
                        @change=${this._onValueInput}
                    ></platform-field>
                    ${this.renderFieldError('value')}
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
                <flows-code-editor
                    .value=${this._pythonCode}
                    language="python"
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

    renderFooter() {
        return html``;
    }
}

customElements.define('flows-edge-condition-modal', FlowsEdgeConditionModal);
registerModalKind(FlowsEdgeConditionModal.modalKind, 'flows-edge-condition-modal');
