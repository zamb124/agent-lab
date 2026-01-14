/**
 * LLMConfigEditor - редактор конфигурации LLM (модель, temperature, max_tokens)
 * Загружает список моделей из API /registry/models/values
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LLMConfigEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .config-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .config-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .config-field {
                flex: 1;
            }
            
            .config-label {
                display: block;
                margin-bottom: var(--space-1);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .config-select,
            .config-input {
                width: 100%;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                transition: border-color var(--duration-fast) var(--easing-default);
            }
            
            .config-select:focus,
            .config-input:focus {
                border-color: var(--accent);
            }
            
            .config-select {
                appearance: none;
                cursor: pointer;
                padding-right: var(--space-6);
                background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23999' viewBox='0 0 16 16'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E");
                background-repeat: no-repeat;
                background-position: right 8px center;
            }
            
            .config-input[type="number"] {
                -moz-appearance: textfield;
            }
            
            .config-input[type="number"]::-webkit-outer-spin-button,
            .config-input[type="number"]::-webkit-inner-spin-button {
                -webkit-appearance: none;
                margin: 0;
            }
            
            .temp-value {
                min-width: 40px;
                text-align: center;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            
            .temp-slider {
                flex: 1;
                height: 4px;
                background: var(--border-subtle);
                border-radius: 2px;
                appearance: none;
                cursor: pointer;
            }
            
            .temp-slider::-webkit-slider-thumb {
                appearance: none;
                width: 14px;
                height: 14px;
                background: var(--accent);
                border-radius: 50%;
                cursor: pointer;
            }
            
            .loading {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `
    ];

    static properties = {
        model: { type: String },
        temperature: { type: Number },
        maxTokens: { type: Number, attribute: 'max-tokens' },
        models: { type: Array },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.model = 'gpt-4o';
        this.temperature = 0.2;
        this.maxTokens = null;
        this.models = [];
        this.loading = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadModels();
    }

    async _loadModels() {
        this.loading = true;
        
        if (this.a2a) {
            const models = await this.a2a.getAvailableModels();
            if (Array.isArray(models) && models.length > 0) {
                this.models = models.map(m => ({ id: m, name: m }));
            } else {
                this.models = this._getDefaultModels();
            }
        } else {
            this.models = this._getDefaultModels();
        }
        
        this.loading = false;
    }

    _getDefaultModels() {
        return [
            { id: 'gpt-4o', name: 'GPT-4o' },
            { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
            { id: 'gpt-4.1', name: 'GPT-4.1' },
            { id: 'yandexgpt', name: 'YandexGPT' },
        ];
    }

    getValue() {
        const config = {
            model: this.model,
            temperature: this.temperature,
        };
        if (this.maxTokens) {
            config.max_tokens = this.maxTokens;
        }
        return config;
    }

    setValue(config) {
        if (config.model) this.model = config.model;
        if (config.temperature !== undefined) this.temperature = config.temperature;
        if (config.max_tokens) this.maxTokens = config.max_tokens;
    }

    _onModelChange(e) {
        this.model = e.target.value;
        this._emitChange();
    }

    _onTemperatureChange(e) {
        this.temperature = parseFloat(e.target.value);
        this._emitChange();
    }

    _onMaxTokensChange(e) {
        const value = e.target.value.trim();
        this.maxTokens = value ? parseInt(value, 10) : null;
        this._emitChange();
    }

    _emitChange() {
        this.emit('change', { value: this.getValue() });
    }

    render() {
        return html`
            <div class="config-container">
                <div class="config-field">
                    <label class="config-label">Model</label>
                    ${this.loading 
                        ? html`<span class="loading">Загрузка...</span>`
                        : html`
                            <select 
                                class="config-select"
                                .value=${this.model}
                                @change=${this._onModelChange}
                            >
                                ${this.models.map(m => html`
                                    <option value=${m.id} ?selected=${m.id === this.model}>${m.name}</option>
                                `)}
                            </select>
                        `
                    }
                </div>
                
                <div class="config-field">
                    <label class="config-label">Temperature: ${this.temperature.toFixed(1)}</label>
                    <div class="config-row">
                        <input
                            type="range"
                            class="temp-slider"
                            min="0"
                            max="2"
                            step="0.1"
                            .value=${String(this.temperature)}
                            @input=${this._onTemperatureChange}
                        />
                    </div>
                </div>
                
                <div class="config-field">
                    <label class="config-label">Max Tokens (опционально)</label>
                    <input
                        type="number"
                        class="config-input"
                        placeholder="Авто"
                        .value=${this.maxTokens || ''}
                        @input=${this._onMaxTokensChange}
                    />
                </div>
            </div>
        `;
    }
}

customElements.define('llm-config-editor', LLMConfigEditor);

