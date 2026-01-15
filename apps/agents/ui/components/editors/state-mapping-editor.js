/**
 * StateMappingEditor - унифицированный редактор маппинга данных
 * Работает в двух режимах: input (state -> param) и output (result -> state)
 * 
 * Формат хранения:
 * - input: {"param_name": "@state:field"} или {"param": "@var:name"} или {"param": "const"}
 * - output: {"result_field": "state_field"}
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

function generateId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return 'id-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

export class StateMappingEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .mapping-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .mapping-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding-bottom: var(--space-2);
            }
            
            .mapping-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .add-btn {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--accent);
                background: var(--accent-subtle);
                border: none;
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .add-btn:hover {
                background: var(--accent);
                color: white;
            }
            
            .mapping-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .mapping-field {
                flex: 1;
                min-width: 0;
            }
            
            .mapping-field.type-field {
                flex: 0 0 100px;
            }
            
            .mapping-input, .mapping-select {
                width: 100%;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                outline: none;
            }
            
            .mapping-input:focus, .mapping-select:focus {
                border-color: var(--accent);
            }
            
            .mapping-arrow {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                flex-shrink: 0;
            }
            
            .mapping-remove {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                color: var(--text-tertiary);
                background: none;
                border: none;
                border-radius: var(--radius-sm);
                cursor: pointer;
                flex-shrink: 0;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .mapping-remove:hover {
                color: var(--error);
                background: var(--error-bg);
            }
            
            .empty-state {
                padding: var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-align: center;
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }
            
            .hint {
                margin-top: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .labels-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-2);
                margin-bottom: var(--space-1);
            }
            
            .label {
                flex: 1;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                min-width: 0;
            }
            
            .label.type-label {
                flex: 0 0 100px;
            }
            
            .label-spacer {
                width: 24px;
                flex-shrink: 0;
            }
            
            .arrow-spacer {
                width: 16px;
                flex-shrink: 0;
            }
        `
    ];

    static properties = {
        mode: { type: String },
        mappings: { type: Object },
        stateVariables: { type: Array, attribute: 'state-variables' },
        readonly: { type: Boolean },
        mappingsList: { type: Array, state: true },
    };

    constructor() {
        super();
        this.mode = 'input';
        this.mappings = {};
        this.stateVariables = [];
        this.readonly = false;
        this.mappingsList = [];
    }

    updated(changedProperties) {
        if (changedProperties.has('mappings')) {
            this._parseMappings();
        }
    }

    get _title() {
        return this.mode === 'input' ? 'Input Mapping' : 'Output Mapping';
    }

    get _labels() {
        if (this.mode === 'input') {
            return {
                source: 'Source',
                type: 'Type',
                target: 'Parameter'
            };
        }
        return {
            source: 'Result field',
            type: 'Type',
            target: 'State field'
        };
    }

    get _placeholders() {
        if (this.mode === 'input') {
            return {
                source: 'field.path',
                target: 'param_name'
            };
        }
        return {
            source: 'result_field',
            target: 'state_field'
        };
    }

    get _emptyText() {
        if (this.mode === 'input') {
            return 'Нет маппингов. Добавьте для передачи данных из state в параметры.';
        }
        return 'Нет маппингов. Добавьте для записи результата в state.';
    }

    get _hintText() {
        if (this.mode === 'input') {
            return 'Маппинг: state/var/const → параметр ноды';
        }
        return 'Маппинг: поле результата → поле state';
    }

    get _typeOptions() {
        if (this.mode === 'input') {
            return [
                { value: '@state', label: '@state' },
                { value: '@var', label: '@var' },
                { value: 'const', label: 'const' }
            ];
        }
        return [
            { value: 'result', label: 'result' }
        ];
    }

    _parseMappings() {
        if (!this.mappings || Object.keys(this.mappings).length === 0) {
            this.mappingsList = [];
            return;
        }
        
        const currentValue = this.getValue();
        const currentStr = JSON.stringify(currentValue);
        const newStr = JSON.stringify(this.mappings);
        
        if (currentStr === newStr) {
            return;
        }
        
        if (this.mode === 'input') {
            this._parseInputMappings();
        } else {
            this._parseOutputMappings();
        }
    }

    _parseInputMappings() {
        this.mappingsList = Object.entries(this.mappings).map(([target, sourceValue]) => {
            let type = 'const';
            let source = sourceValue;
            
            if (typeof sourceValue === 'string') {
                if (sourceValue.startsWith('@state:')) {
                    type = '@state';
                    source = sourceValue.slice(7);
                } else if (sourceValue.startsWith('@var:')) {
                    type = '@var';
                    source = sourceValue.slice(5);
                }
            }
            
            return {
                source,
                type,
                target,
                id: generateId()
            };
        });
    }

    _parseOutputMappings() {
        this.mappingsList = Object.entries(this.mappings).map(([source, target]) => ({
            source,
            type: 'result',
            target: typeof target === 'string' ? target : JSON.stringify(target),
            id: generateId()
        }));
    }

    getValue() {
        const result = {};
        const list = this.mappingsList || [];
        
        if (this.mode === 'input') {
            for (const m of list) {
                if (m.target && m.source) {
                    let value;
                    if (m.type === '@state') {
                        value = `@state:${m.source}`;
                    } else if (m.type === '@var') {
                        value = `@var:${m.source}`;
                    } else {
                        value = m.source;
                    }
                    result[m.target] = value;
                }
            }
        } else {
            for (const m of list) {
                if (m.source && m.target) {
                    result[m.source] = m.target;
                }
            }
        }
        
        return result;
    }

    setValue(mapping) {
        this.mappings = mapping;
        this._parseMappings();
    }

    _addMapping() {
        const currentList = this.mappingsList || [];
        const defaultType = this.mode === 'input' ? '@state' : 'result';
        
        this.mappingsList = [
            ...currentList,
            { source: '', type: defaultType, target: '', id: generateId() }
        ];
        this._emitChange();
    }

    _removeMapping(id) {
        const currentList = this.mappingsList || [];
        this.mappingsList = currentList.filter(m => m.id !== id);
        this._emitChange();
    }

    _updateMapping(id, field, value) {
        const currentList = this.mappingsList || [];
        this.mappingsList = currentList.map(m => 
            m.id === id ? { ...m, [field]: value } : m
        );
        this._emitChange();
    }

    _emitChange() {
        this.emit('change', { value: this.getValue() });
    }

    _getAutocompleteOptions() {
        if (!this.stateVariables || this.stateVariables.length === 0) {
            return [];
        }
        return this.stateVariables;
    }

    render() {
        const mappingsList = this.mappingsList || [];
        const labels = this._labels;
        const placeholders = this._placeholders;
        const typeOptions = this._typeOptions;
        const autocompleteOptions = this._getAutocompleteOptions();
        const showTypeSelect = this.mode === 'input';
        
        return html`
            <div class="mapping-container">
                <div class="mapping-header">
                    <span class="mapping-title">${this._title}</span>
                    ${!this.readonly ? html`
                        <button type="button" class="add-btn" @click=${this._addMapping}>
                            + Добавить
                        </button>
                    ` : ''}
                </div>
                
                ${mappingsList.length === 0 ? html`
                    <div class="empty-state">
                        ${this._emptyText}
                    </div>
                ` : html`
                    <div class="labels-row">
                        <span class="label">${labels.source}</span>
                        ${showTypeSelect ? html`
                            <span class="arrow-spacer"></span>
                            <span class="label type-label">${labels.type}</span>
                        ` : ''}
                        <span class="arrow-spacer"></span>
                        <span class="label">${labels.target}</span>
                        ${!this.readonly ? html`<span class="label-spacer"></span>` : ''}
                    </div>
                    ${mappingsList.map(m => html`
                        <div class="mapping-row">
                            <div class="mapping-field">
                                <input
                                    type="text"
                                    class="mapping-input"
                                    placeholder="${placeholders.source}"
                                    .value=${m.source}
                                    ?readonly=${this.readonly}
                                    list="autocomplete-${m.id}"
                                    @input=${(e) => this._updateMapping(m.id, 'source', e.target.value)}
                                />
                                ${this.mode === 'input' && autocompleteOptions.length > 0 ? html`
                                    <datalist id="autocomplete-${m.id}">
                                        ${autocompleteOptions.map(opt => html`<option value="${opt}">`)}
                                    </datalist>
                                ` : ''}
                            </div>
                            ${showTypeSelect ? html`
                                <span class="mapping-arrow">|</span>
                                <div class="mapping-field type-field">
                                    <select
                                        class="mapping-select"
                                        .value=${m.type}
                                        ?disabled=${this.readonly}
                                        @change=${(e) => this._updateMapping(m.id, 'type', e.target.value)}
                                    >
                                        ${typeOptions.map(opt => html`
                                            <option value="${opt.value}" ?selected=${m.type === opt.value}>
                                                ${opt.label}
                                            </option>
                                        `)}
                                    </select>
                                </div>
                            ` : ''}
                            <span class="mapping-arrow">→</span>
                            <div class="mapping-field">
                                <input
                                    type="text"
                                    class="mapping-input"
                                    placeholder="${placeholders.target}"
                                    .value=${m.target}
                                    ?readonly=${this.readonly}
                                    @input=${(e) => this._updateMapping(m.id, 'target', e.target.value)}
                                />
                            </div>
                            ${!this.readonly ? html`
                                <button 
                                    type="button" 
                                    class="mapping-remove"
                                    @click=${() => this._removeMapping(m.id)}
                                >×</button>
                            ` : ''}
                        </div>
                    `)}
                `}
                
                <div class="hint">
                    ${this._hintText}
                </div>
            </div>
        `;
    }
}

customElements.define('state-mapping-editor', StateMappingEditor);
