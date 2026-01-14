/**
 * InputMappingEditor - визуальный редактор маппинга входных данных
 * Позволяет маппить поля из state на параметры
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

function generateId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return 'id-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

export class InputMappingEditor extends PlatformElement {
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
            }
            
            .mapping-input {
                width: 100%;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                outline: none;
            }
            
            .mapping-input:focus {
                border-color: var(--accent);
            }
            
            .mapping-arrow {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
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
        `
    ];

    static properties = {
        mappings: { type: Object },
        availableState: { type: Object, attribute: 'available-state' },
        readonly: { type: Boolean },
        mappingsList: { type: Array },
    };

    constructor() {
        super();
        this.mappings = {};
        this.availableState = {};
        this.readonly = false;
        this.mappingsList = [];
        console.log('[InputMappingEditor] Constructor called');
    }

    connectedCallback() {
        super.connectedCallback();
        console.log('[InputMappingEditor] connectedCallback, mappingsList:', this.mappingsList);
    }

    updated(changedProperties) {
        if (changedProperties.has('mappings')) {
            console.log('[InputMappingEditor] mappings changed:', this.mappings);
            this._parseMappings();
        }
    }

    _parseMappings() {
        if (!this.mappings) {
            this.mappingsList = [];
            return;
        }
        
        // Проверяем, совпадает ли новое значение mappings с текущим getValue()
        const currentValue = this.getValue();
        const currentKeys = Object.keys(currentValue).sort().join(',');
        const newKeys = Object.keys(this.mappings).sort().join(',');
        
        // Если ключи совпадают, проверяем значения
        if (currentKeys === newKeys) {
            let allMatch = true;
            for (const key in this.mappings) {
                if (this.mappings[key] !== currentValue[key]) {
                    allMatch = false;
                    break;
                }
            }
            // Если всё совпадает, не перезаписываем mappingsList
            if (allMatch) {
                console.log('[InputMappingEditor] _parseMappings: values match, skipping parse');
                return;
            }
        }
        
        console.log('[InputMappingEditor] _parseMappings: parsing new mappings', this.mappings);
        
        if (Array.isArray(this.mappings)) {
            this.mappingsList = this.mappings.map(m => ({
                ...m,
                id: m.id || generateId(),
            }));
            return;
        }
        
        if (typeof this.mappings === 'object') {
            this.mappingsList = Object.entries(this.mappings).map(([param, source]) => ({
                param,
                source: typeof source === 'string' ? source : JSON.stringify(source),
                id: generateId(),
            }));
        }
    }

    getValue() {
        const result = {};
        const mappingsList = this.mappingsList || [];
        for (const m of mappingsList) {
            if (m.param && m.source) {
                result[m.param] = m.source;
            }
        }
        return result;
    }

    setValue(mapping) {
        this.mappings = mapping;
        this._parseMappings();
    }

    setAvailableState(state) {
        this.availableState = state;
    }

    _addMapping() {
        console.log('[InputMappingEditor] _addMapping called, current list:', this.mappingsList);
        const currentList = this.mappingsList || [];
        this.mappingsList = [
            ...currentList,
            { param: '', source: '@state:', id: generateId() }
        ];
        console.log('[InputMappingEditor] New list:', this.mappingsList);
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

    _getStateFields() {
        const fields = [];
        const traverse = (obj, prefix = '') => {
            for (const [key, value] of Object.entries(obj)) {
                const path = prefix ? `${prefix}.${key}` : key;
                fields.push(path);
                if (value && typeof value === 'object' && !Array.isArray(value)) {
                    traverse(value, path);
                }
            }
        };
        traverse(this.availableState);
        return fields;
    }

    render() {
        console.log('[InputMappingEditor] render called, mappingsList:', this.mappingsList);
        const stateFields = this._getStateFields();
        const mappingsList = this.mappingsList || [];
        console.log('[InputMappingEditor] Local mappingsList:', mappingsList);
        
        return html`
            <div class="mapping-container">
                <div class="mapping-header">
                    <span class="mapping-title">Input Mapping</span>
                    ${!this.readonly ? html`
                        <button type="button" class="add-btn" @click=${this._addMapping}>
                            + Добавить
                        </button>
                    ` : ''}
                </div>
                
                ${mappingsList.length === 0 ? html`
                    <div class="empty-state">
                        Нет маппингов. Добавьте для передачи данных из state.
                    </div>
                ` : mappingsList.map(m => html`
                    <div class="mapping-row">
                        <div class="mapping-field">
                            <input
                                type="text"
                                class="mapping-input"
                                placeholder="param_name"
                                .value=${m.param}
                                ?readonly=${this.readonly}
                                @input=${(e) => this._updateMapping(m.id, 'param', e.target.value)}
                            />
                        </div>
                        <span class="mapping-arrow">←</span>
                        <div class="mapping-field">
                            <input
                                type="text"
                                class="mapping-input"
                                placeholder="@state:field.path"
                                .value=${m.source}
                                ?readonly=${this.readonly}
                                list="state-fields-${m.id}"
                                @input=${(e) => this._updateMapping(m.id, 'source', e.target.value)}
                            />
                            <datalist id="state-fields-${m.id}">
                                ${stateFields.map(f => html`<option value="@state:${f}">`)}
                            </datalist>
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
                
                <div class="hint">
                    Формат: @state:path.to.field или @var:variable_name
                </div>
            </div>
        `;
    }
}

customElements.define('input-mapping-editor', InputMappingEditor);

