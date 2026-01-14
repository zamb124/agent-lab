/**
 * EdgeConditionModal - модальное окно для редактирования условий связи между нодами
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';

export class EdgeConditionModal extends PlatformFormModal {
    static styles = [
        PlatformFormModal.styles,
        css`
            .modal-body {
                padding: var(--space-6);
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
        `
    ];

    static properties = {
        ...PlatformFormModal.properties,
        fromNode: { type: String },
        toNode: { type: String },
        condition: { type: String },
        variables: { type: Array },
        selectedVariable: { type: String },
        selectedOperator: { type: String },
        conditionValue: { type: String },
        preview: { type: String },
    };

    constructor() {
        super();
        this.fromNode = '';
        this.toNode = '';
        this.condition = '';
        this.variables = [];
        
        this.selectedVariable = '';
        this.selectedOperator = '==';
        this.conditionValue = '';
        this.preview = '';
        
        this.title = 'Условие перехода';
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.condition) {
            const parsed = this._parseCondition(this.condition);
            this.selectedVariable = parsed.variable;
            this.selectedOperator = parsed.operator;
            this.conditionValue = parsed.value;
            this._updatePreview();
        }
    }

    _parseCondition(condition) {
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

    _buildCondition() {
        if (!this.selectedVariable || !this.conditionValue) {
            return '';
        }
        
        const value = this.conditionValue.trim();
        const quotedValue = isNaN(value) ? `'${value}'` : value;
        return `${this.selectedVariable} ${this.selectedOperator} ${quotedValue}`;
    }

    _updatePreview() {
        this.preview = this._buildCondition();
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

    _skipCondition() {
        this.emit('condition-saved', { 
            fromNode: this.fromNode, 
            toNode: this.toNode, 
            condition: '' 
        });
        this.close();
    }

    validateForm() {
        const errors = {};
        
        if (!this.selectedVariable && this.conditionValue) {
            errors.variable = 'Выберите переменную';
        }
        
        if (this.selectedVariable && !this.conditionValue) {
            errors.value = 'Введите значение';
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
        return html`
            <div class="condition-header">
                <h3>Условие перехода</h3>
                <div class="condition-subtitle">
                    ${this.fromNode} → ${this.toNode}
                </div>
            </div>
            
            <form @submit=${(e) => { e.preventDefault(); this._onSubmit(e); }}>
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
                                ${this.variables.map(v => html`
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


