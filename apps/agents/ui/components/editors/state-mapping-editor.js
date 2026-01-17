/**
 * StateMappingEditor - унифицированный редактор маппинга данных
 * Работает в трёх режимах: 
 * - input (state -> param)
 * - output (result -> state)
 * - both (табы input/output в одном компоненте)
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
            
            /* Табы для режима both */
            .tabs-container {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            
            .tab-btn {
                padding: var(--space-1) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .tab-btn:hover {
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
            }
            
            .tab-btn.active {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: var(--accent);
            }
            
            .tab-btn .count {
                margin-left: var(--space-1);
                padding: 0 var(--space-1);
                font-size: 10px;
                color: var(--text-tertiary);
                background: var(--glass-tint-medium);
                border-radius: var(--radius-xs);
            }
            
            .tab-btn.active .count {
                color: var(--accent);
                background: var(--accent-bg);
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
        inputMappings: { type: Object },
        outputMappings: { type: Object },
        stateVariables: { type: Array, attribute: 'state-variables' },
        readonly: { type: Boolean },
        mappingsList: { type: Array, state: true },
        activeTab: { type: String, state: true },
        inputMappingsList: { type: Array, state: true },
        outputMappingsList: { type: Array, state: true },
    };

    constructor() {
        super();
        this.mode = 'input';
        this.mappings = {};
        this.inputMappings = {};
        this.outputMappings = {};
        this.stateVariables = [];
        this.readonly = false;
        this.mappingsList = [];
        this.activeTab = 'input';
        this.inputMappingsList = [];
        this.outputMappingsList = [];
    }

    updated(changedProperties) {
        if (this.mode === 'both') {
            if (changedProperties.has('inputMappings')) {
                this._parseInputMappingsForBoth();
            }
            if (changedProperties.has('outputMappings')) {
                this._parseOutputMappingsForBoth();
            }
        } else {
            if (changedProperties.has('mappings')) {
                this._parseMappings();
            }
        }
    }

    get _currentMode() {
        return this.mode === 'both' ? this.activeTab : this.mode;
    }

    get _currentList() {
        if (this.mode === 'both') {
            return this.activeTab === 'input' ? this.inputMappingsList : this.outputMappingsList;
        }
        return this.mappingsList;
    }

    get _title() {
        return this._currentMode === 'input' ? 'Input Mapping' : 'Output Mapping';
    }

    get _labels() {
        if (this._currentMode === 'input') {
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
        if (this._currentMode === 'input') {
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
        if (this._currentMode === 'input') {
            return 'Нет маппингов';
        }
        return 'Нет маппингов';
    }

    get _hintText() {
        if (this._currentMode === 'input') {
            return 'state/var/const → параметр';
        }
        return 'результат → state';
    }

    get _typeOptions() {
        if (this._currentMode === 'input') {
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

    _parseInputMappingsForBoth() {
        const currentValue = this._getValueForMode('input', this.inputMappingsList);
        const currentStr = JSON.stringify(currentValue);
        const newStr = JSON.stringify(this.inputMappings || {});
        
        if (currentStr === newStr) return;
        if ((!this.inputMappings || Object.keys(this.inputMappings).length === 0) && this.inputMappingsList.length > 0) return;
        
        if (!this.inputMappings || Object.keys(this.inputMappings).length === 0) {
            this.inputMappingsList = [];
            return;
        }
        
        this.inputMappingsList = Object.entries(this.inputMappings).map(([target, sourceValue]) => {
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
            
            return { source, type, target, id: generateId() };
        });
    }

    _parseOutputMappingsForBoth() {
        const currentValue = this._getValueForMode('output', this.outputMappingsList);
        const currentStr = JSON.stringify(currentValue);
        const newStr = JSON.stringify(this.outputMappings || {});
        
        if (currentStr === newStr) return;
        if ((!this.outputMappings || Object.keys(this.outputMappings).length === 0) && this.outputMappingsList.length > 0) return;
        
        if (!this.outputMappings || Object.keys(this.outputMappings).length === 0) {
            this.outputMappingsList = [];
            return;
        }
        
        this.outputMappingsList = Object.entries(this.outputMappings).map(([source, target]) => ({
            source,
            type: 'result',
            target: typeof target === 'string' ? target : JSON.stringify(target),
            id: generateId()
        }));
    }

    _parseMappings() {
        const currentValue = this.getValue();
        const currentStr = JSON.stringify(currentValue);
        const newStr = JSON.stringify(this.mappings || {});
        
        if (currentStr === newStr) return;
        if ((!this.mappings || Object.keys(this.mappings).length === 0) && this.mappingsList.length > 0) return;
        
        if (!this.mappings || Object.keys(this.mappings).length === 0) {
            this.mappingsList = [];
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
            
            return { source, type, target, id: generateId() };
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

    _getValueForMode(mode, list) {
        const result = {};
        
        if (mode === 'input') {
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

    getValue() {
        if (this.mode === 'both') {
            return {
                input: this._getValueForMode('input', this.inputMappingsList),
                output: this._getValueForMode('output', this.outputMappingsList)
            };
        }
        return this._getValueForMode(this.mode, this.mappingsList);
    }

    getInputValue() {
        return this._getValueForMode('input', this.inputMappingsList);
    }

    getOutputValue() {
        return this._getValueForMode('output', this.outputMappingsList);
    }

    setValue(mapping) {
        this.mappings = mapping;
        this._parseMappings();
    }

    _addMapping() {
        if (this.mode === 'both') {
            const defaultType = this.activeTab === 'input' ? '@state' : 'result';
            if (this.activeTab === 'input') {
                this.inputMappingsList = [
                    ...this.inputMappingsList,
                    { source: '', type: defaultType, target: '', id: generateId() }
                ];
            } else {
                this.outputMappingsList = [
                    ...this.outputMappingsList,
                    { source: '', type: defaultType, target: '', id: generateId() }
                ];
            }
        } else {
            const defaultType = this.mode === 'input' ? '@state' : 'result';
            this.mappingsList = [
                ...this.mappingsList,
                { source: '', type: defaultType, target: '', id: generateId() }
            ];
        }
    }

    _removeMapping(id) {
        if (this.mode === 'both') {
            if (this.activeTab === 'input') {
                this.inputMappingsList = this.inputMappingsList.filter(m => m.id !== id);
                this._emitInputChange();
            } else {
                this.outputMappingsList = this.outputMappingsList.filter(m => m.id !== id);
                this._emitOutputChange();
            }
        } else {
            this.mappingsList = this.mappingsList.filter(m => m.id !== id);
            this._emitChange();
        }
    }

    _updateMapping(id, field, value) {
        if (this.mode === 'both') {
            if (this.activeTab === 'input') {
                this.inputMappingsList = this.inputMappingsList.map(m => 
                    m.id === id ? { ...m, [field]: value } : m
                );
                this._emitInputChange();
            } else {
                this.outputMappingsList = this.outputMappingsList.map(m => 
                    m.id === id ? { ...m, [field]: value } : m
                );
                this._emitOutputChange();
            }
        } else {
            this.mappingsList = this.mappingsList.map(m => 
                m.id === id ? { ...m, [field]: value } : m
            );
            this._emitChange();
        }
    }

    _emitChange() {
        this.emit('change', { value: this.getValue() });
    }

    _emitInputChange() {
        this.emit('input-change', { value: this.getInputValue() });
    }

    _emitOutputChange() {
        this.emit('output-change', { value: this.getOutputValue() });
    }

    _getAutocompleteOptions() {
        if (!this.stateVariables || this.stateVariables.length === 0) {
            return [];
        }
        return this.stateVariables;
    }

    _switchTab(tab) {
        this.activeTab = tab;
    }

    _renderTabs() {
        const inputCount = this.inputMappingsList.length;
        const outputCount = this.outputMappingsList.length;
        
        return html`
            <div class="tabs-container">
                <button 
                    type="button" 
                    class="tab-btn ${this.activeTab === 'input' ? 'active' : ''}"
                    @click=${() => this._switchTab('input')}
                >
                    Input${inputCount > 0 ? html`<span class="count">${inputCount}</span>` : ''}
                </button>
                <button 
                    type="button" 
                    class="tab-btn ${this.activeTab === 'output' ? 'active' : ''}"
                    @click=${() => this._switchTab('output')}
                >
                    Output${outputCount > 0 ? html`<span class="count">${outputCount}</span>` : ''}
                </button>
            </div>
        `;
    }

    _renderMappingContent() {
        const mappingsList = this._currentList;
        const labels = this._labels;
        const placeholders = this._placeholders;
        const typeOptions = this._typeOptions;
        const autocompleteOptions = this._getAutocompleteOptions();
        const showTypeSelect = this._currentMode === 'input';
        
        return html`
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
                            ${this._currentMode === 'input' && autocompleteOptions.length > 0 ? html`
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
        `;
    }

    render() {
        if (this.mode === 'both') {
            return html`
                <div class="mapping-container">
                    <div class="mapping-header">
                        ${this._renderTabs()}
                        ${!this.readonly ? html`
                            <button type="button" class="add-btn" @click=${this._addMapping}>
                                + Добавить
                            </button>
                        ` : ''}
                    </div>
                    ${this._renderMappingContent()}
                </div>
            `;
        }
        
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
                ${this._renderMappingContent()}
            </div>
        `;
    }
}

customElements.define('state-mapping-editor', StateMappingEditor);
