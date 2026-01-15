/**
 * EdgeConditionModal - модальное окно для редактирования условий связи между нодами
 * Поддерживает два режима: Simple (визуальный) и Python (код)
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import '../components/editors/python-code-editor.js';

const DEFAULT_PYTHON_CODE = `def check(state):
    """
    Проверка условия перехода.
    
    Args:
        state: dict - текущее состояние
        
    Returns:
        bool - True если условие выполнено
    """
    return state.get('route') == 'expected_value'
`;

export class EdgeConditionModal extends PlatformFormModal {
    static styles = [
        PlatformFormModal.styles,
        css`
            .modal-body {
                padding: var(--space-6);
                min-width: 500px;
            }
            
            .condition-header {
                margin-bottom: var(--space-6);
                padding-bottom: var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .condition-header h3 {
                margin: 0 0 var(--space-2);
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .condition-subtitle {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                font-family: var(--font-mono);
            }
            
            .mode-tabs {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }
            
            .mode-tab {
                flex: 1;
                padding: var(--space-2) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                text-align: center;
            }
            
            .mode-tab:hover {
                color: var(--text-primary);
                border-color: var(--border-medium);
            }
            
            .mode-tab.active {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: var(--accent);
            }
            
            .condition-builder {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }
            
            .builder-row {
                display: grid;
                grid-template-columns: 1fr auto 1fr;
                gap: var(--space-3);
                align-items: start;
            }
            
            .form-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .form-field label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            select, input {
                width: 100%;
                height: var(--input-height);
                padding: 0 var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-bg-subtle);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            select:hover, input:hover {
                border-color: var(--border-strong);
            }
            
            select:focus, input:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-light);
            }
            
            select option {
                background: var(--bg-secondary);
                color: var(--text-primary);
            }
            
            .operator-connector {
                display: flex;
                align-items: center;
                justify-content: center;
                height: var(--input-height);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-top: 26px;
            }
            
            .condition-preview {
                padding: var(--space-4);
                background: var(--glass-bg-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
            }
            
            .preview-label {
                margin-bottom: var(--space-2);
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
                background: rgba(16, 163, 127, 0.08);
                border-radius: var(--radius-sm);
                border: 1px solid rgba(16, 163, 127, 0.2);
            }
            
            .preview-empty {
                color: var(--text-tertiary);
                font-style: italic;
            }
            
            .skip-condition {
                margin-top: var(--space-4);
                text-align: center;
            }
            
            .skip-link {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                cursor: pointer;
                text-decoration: underline;
                transition: color var(--duration-fast);
            }
            
            .skip-link:hover {
                color: var(--text-primary);
            }
            
            .python-mode {
                margin-bottom: var(--space-4);
            }
            
            .python-hint {
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .variables-hint {
                margin-top: var(--space-2);
                padding: var(--space-2);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            
            .variables-hint strong {
                color: var(--text-primary);
            }
        `
    ];

    static properties = {
        ...PlatformFormModal.properties,
        fromNode: { type: String },
        toNode: { type: String },
        condition: { type: Object },
        variables: { type: Array },
        sourceNodeConfig: { type: Object },
        stateVariables: { type: Array },
        
        mode: { type: String },
        selectedVariable: { type: String },
        selectedOperator: { type: String },
        conditionValue: { type: String },
        pythonCode: { type: String },
        preview: { type: String },
    };

    constructor() {
        super();
        this.fromNode = '';
        this.toNode = '';
        this.condition = null;
        this.variables = [];
        this.sourceNodeConfig = null;
        this.stateVariables = [];
        
        this.mode = 'simple';
        this.selectedVariable = '';
        this.selectedOperator = '==';
        this.conditionValue = '';
        this.pythonCode = DEFAULT_PYTHON_CODE;
        this.preview = '';
        
        this.title = 'Условие перехода';
    }

    connectedCallback() {
        super.connectedCallback();
        this._parseExistingCondition();
        this._updatePreview();
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('condition')) {
            this._parseExistingCondition();
        }
    }

    _parseExistingCondition() {
        if (!this.condition) {
            this.mode = 'simple';
            this.selectedVariable = '';
            this.selectedOperator = '==';
            this.conditionValue = '';
            this.pythonCode = DEFAULT_PYTHON_CODE;
            return;
        }
        
        if (typeof this.condition === 'object') {
            if (this.condition.type === 'python') {
                this.mode = 'python';
                this.pythonCode = this.condition.code || DEFAULT_PYTHON_CODE;
            } else if (this.condition.type === 'simple') {
                this.mode = 'simple';
                this.selectedVariable = this.condition.variable || '';
                this.selectedOperator = this.condition.operator || '==';
                this.conditionValue = this.condition.value || '';
            }
        } else if (typeof this.condition === 'string') {
            this.mode = 'simple';
            const parsed = this._parseLegacyCondition(this.condition);
            this.selectedVariable = parsed.variable;
            this.selectedOperator = parsed.operator;
            this.conditionValue = parsed.value;
        }
        
        this._updatePreview();
    }

    _parseLegacyCondition(condition) {
        if (!condition) {
            return { variable: '', operator: '==', value: '' };
        }
        
        const operators = ['!=', '>=', '<=', '==', '>', '<', 'in'];
        for (const op of operators) {
            if (condition.includes(` ${op} `)) {
                const [variable, rawValue] = condition.split(` ${op} `);
                const value = rawValue?.replace(/^['"]|['"]$/g, '') || '';
                return { 
                    variable: variable.trim(), 
                    operator: op, 
                    value: value.trim() 
                };
            }
        }
        
        return { variable: '', operator: '==', value: '' };
    }

    _collectAllVariables() {
        const vars = new Set();
        
        // Переданные variables (legacy)
        if (this.variables && Array.isArray(this.variables)) {
            this.variables.forEach(v => vars.add(v));
        }
        
        // State variables
        if (this.stateVariables && Array.isArray(this.stateVariables)) {
            this.stateVariables.forEach(v => vars.add(`variables.${v}`));
        }
        
        // Из output_mapping исходящей ноды
        if (this.sourceNodeConfig?.output_mapping) {
            const mapping = this.sourceNodeConfig.output_mapping;
            if (typeof mapping === 'object') {
                Object.values(mapping).forEach(stateField => {
                    if (typeof stateField === 'string') {
                        vars.add(stateField);
                    }
                });
            }
        }
        
        // Из output_schema если structured_output
        if (this.sourceNodeConfig?.structured_output && 
            this.sourceNodeConfig?.output_schema?.properties &&
            !this.sourceNodeConfig?.output_mapping) {
            Object.keys(this.sourceNodeConfig.output_schema.properties).forEach(prop => {
                vars.add(prop);
            });
        }
        
        // Стандартные поля state
        ['content', 'route', 'status', 'result', 'category', 'type'].forEach(f => vars.add(f));
        
        return Array.from(vars).sort();
    }

    _buildCondition() {
        if (this.mode === 'python') {
            return {
                type: 'python',
                code: this.pythonCode
            };
        }
        
        if (!this.selectedVariable || !this.conditionValue) {
            return null;
        }
        
        return {
            type: 'simple',
            variable: this.selectedVariable,
            operator: this.selectedOperator,
            value: this.conditionValue
        };
    }

    _buildPreviewString() {
        if (this.mode === 'python') {
            return 'Python: check(state) -> bool';
        }
        
        if (!this.selectedVariable || !this.conditionValue) {
            return '';
        }
        
        const value = this.conditionValue.trim();
        const quotedValue = isNaN(value) ? `'${value}'` : value;
        return `${this.selectedVariable} ${this.selectedOperator} ${quotedValue}`;
    }

    _updatePreview() {
        this.preview = this._buildPreviewString();
    }

    _onModeChange(newMode) {
        this.mode = newMode;
        this._updatePreview();
    }

    _onVariableChange(e) {
        this.selectedVariable = e.target.value;
        this._updatePreview();
    }

    _onOperatorChange(e) {
        this.selectedOperator = e.target.value;
        this._updatePreview();
    }

    _onValueInput(e) {
        this.conditionValue = e.target.value;
        this._updatePreview();
    }

    _onPythonCodeChange(e) {
        this.pythonCode = e.detail.value;
        this._updatePreview();
    }

    _skipCondition() {
        this.emit('condition-saved', { 
            fromNode: this.fromNode, 
            toNode: this.toNode, 
            condition: null 
        });
        this.close();
    }

    validateForm() {
        const errors = {};
        
        if (this.mode === 'simple') {
            if (!this.selectedVariable && this.conditionValue) {
                errors.variable = 'Выберите переменную';
            }
            
            if (this.selectedVariable && !this.conditionValue) {
                errors.value = 'Введите значение';
            }
        }
        
        if (this.mode === 'python') {
            if (!this.pythonCode || !this.pythonCode.includes('def check')) {
                errors.code = 'Код должен содержать функцию check(state)';
            }
        }
        
        return errors;
    }

    async handleSubmit() {
        const condition = this._buildCondition();
        
        this.emit('condition-saved', {
            fromNode: this.fromNode,
            toNode: this.toNode,
            condition,
        });
        
        this.close();
    }

    renderBody() {
        const allVariables = this._collectAllVariables();
        
        return html`
            <div class="condition-header">
                <h3>Условие перехода</h3>
                <div class="condition-subtitle">
                    ${this.fromNode} → ${this.toNode}
                </div>
            </div>
            
            <div class="mode-tabs">
                <button 
                    type="button"
                    class="mode-tab ${this.mode === 'simple' ? 'active' : ''}"
                    @click=${() => this._onModeChange('simple')}
                >
                    Простой режим
                </button>
                <button 
                    type="button"
                    class="mode-tab ${this.mode === 'python' ? 'active' : ''}"
                    @click=${() => this._onModeChange('python')}
                >
                    Python код
                </button>
            </div>
            
            <form @submit=${(e) => { e.preventDefault(); this._onSubmit(e); }}>
                ${this.mode === 'simple' ? this._renderSimpleMode(allVariables) : this._renderPythonMode()}
                
                <div class="condition-preview">
                    <div class="preview-label">Результат:</div>
                    <div class="preview-code ${!this.preview ? 'preview-empty' : ''}">
                        ${this.preview || '—'}
                    </div>
                </div>
                
                <div class="skip-condition">
                    <span class="skip-link" @click=${this._skipCondition}>
                        Пропустить (без условия)
                    </span>
                </div>
            </form>
        `;
    }

    _renderSimpleMode(allVariables) {
        return html`
            <div class="condition-builder">
                <div class="builder-row">
                    <div class="form-field">
                        <label for="variable">Переменная</label>
                        <select 
                            id="variable"
                            .value=${this.selectedVariable}
                            @change=${this._onVariableChange}
                        >
                            <option value="">-- выберите --</option>
                            ${allVariables.map(v => html`
                                <option value="${v}" ?selected=${v === this.selectedVariable}>
                                    ${v}
                                </option>
                            `)}
                        </select>
                        ${this.renderFieldError('variable')}
                    </div>
                    
                    <div class="operator-connector">
                        <select
                            .value=${this.selectedOperator}
                            @change=${this._onOperatorChange}
                            style="width: 80px; padding: 0 var(--space-2);"
                        >
                            <option value="==">==</option>
                            <option value="!=">!=</option>
                            <option value=">">&gt;</option>
                            <option value="<">&lt;</option>
                            <option value=">=">&gt;=</option>
                            <option value="<=">&lt;=</option>
                            <option value="in">in</option>
                        </select>
                    </div>
                    
                    <div class="form-field">
                        <label for="value">Значение</label>
                        <input
                            id="value"
                            type="text"
                            .value=${this.conditionValue}
                            @input=${this._onValueInput}
                            placeholder="order"
                        />
                        ${this.renderFieldError('value')}
                    </div>
                </div>
            </div>
            
            ${this.sourceNodeConfig ? html`
                <div class="variables-hint">
                    <strong>Доступные переменные:</strong> ${allVariables.slice(0, 5).join(', ')}${allVariables.length > 5 ? '...' : ''}
                </div>
            ` : ''}
        `;
    }

    _renderPythonMode() {
        return html`
            <div class="python-mode">
                <python-code-editor
                    .value=${this.pythonCode}
                    @change=${this._onPythonCodeChange}
                    min-height="180"
                    show-header="false"
                ></python-code-editor>
                <div class="python-hint">
                    Функция <code>check(state)</code> должна возвращать <code>True</code> или <code>False</code>.
                    <br>state - это dict со всеми переменными текущего состояния.
                </div>
                ${this.renderFieldError('code')}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="secondary" @click=${this.close}>
                Отмена
            </platform-button>
            <platform-button 
                variant="primary" 
                ?loading=${this.loading}
                @click=${this._onSubmit}
            >
                Применить
            </platform-button>
        `;
    }
}

customElements.define('edge-condition-modal', EdgeConditionModal);
