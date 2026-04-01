/**
 * LLMConfigEditor - редактор конфигурации LLM (модель, temperature, max_tokens, provider, api_key, base_url)
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
            
            .credentials-section {
                margin-top: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
            }
            
            .credentials-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }
            
            .config-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `
    ];

    static properties = {
        model: { type: String },
        temperature: { type: Number },
        maxTokens: { type: Number, attribute: 'max-tokens' },
        provider: { type: String },
        apiKey: { type: String, attribute: 'api-key' },
        baseUrl: { type: String, attribute: 'base-url' },
        models: { type: Array },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.model = 'gpt-4o';
        this.temperature = 0.2;
        this.maxTokens = null;
        this.provider = '';
        this.apiKey = '';
        this.baseUrl = '';
        this.models = [];
        this.loading = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadModels();
    }

    async _loadModels(provider = null) {
        this.loading = true;
        
        if (this.a2a) {
            // Передаём provider в API - если указан, получим модели этого провайдера
            const models = await this.a2a.getAvailableModels(provider || this.provider || null);
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
        if (this.provider) {
            config.provider = this.provider;
        }
        if (this.apiKey) {
            config.api_key = this.apiKey;
        }
        if (this.baseUrl) {
            config.base_url = this.baseUrl;
        }
        return config;
    }

    setValue(config) {
        if (config.model) this.model = config.model;
        if (config.temperature !== undefined) this.temperature = config.temperature;
        if (config.max_tokens) this.maxTokens = config.max_tokens;
        if (config.provider !== undefined) this.provider = config.provider || '';
        if (config.api_key !== undefined) this.apiKey = config.api_key || '';
        if (config.base_url !== undefined) this.baseUrl = config.base_url || '';
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
    
    _onProviderChange(e) {
        this.provider = e.target.value;
        // Перезагружаем модели при смене провайдера
        this._loadModels(this.provider || null);
        this._emitChange();
    }
    
    _onApiKeyChange(e) {
        this.apiKey = e.target.value;
        this._emitChange();
    }
    
    _onBaseUrlChange(e) {
        this.baseUrl = e.target.value;
        this._emitChange();
    }

    _emitChange() {
        this.emit('change', { value: this.getValue() });
    }

    render() {
        const showCredentials = this.provider !== '';
        
        return html`
            <div class="config-container">
                <div class="config-field">
                    <label class="config-label">${this.i18n.t('llm_config_editor.label_model')}</label>
                    ${this.loading 
                        ? html`<span class="loading">${this.i18n.t('llm_config_editor.loading')}</span>`
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
                    <label class="config-label">${this.i18n.t('llm_config_editor.label_temperature')}: ${this.temperature.toFixed(1)}</label>
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
                    <label class="config-label">${this.i18n.t('llm_config_editor.label_max_tokens')}</label>
                    <input
                        type="number"
                        class="config-input"
                        placeholder=${this.i18n.t('llm_config_editor.placeholder_auto')}
                        .value=${this.maxTokens || ''}
                        @input=${this._onMaxTokensChange}
                    />
                </div>
                
                <div class="config-field">
                    <label class="config-label">${this.i18n.t('llm_config_editor.label_provider')}</label>
                    <select 
                        class="config-select"
                        .value=${this.provider}
                        @change=${this._onProviderChange}
                    >
                        <option value="">${this.i18n.t('llm_config_editor.option_system_default')}</option>
                        <option value="openai" ?selected=${this.provider === 'openai'}>OpenAI</option>
                        <option value="openrouter" ?selected=${this.provider === 'openrouter'}>OpenRouter</option>
                        <option value="bothub" ?selected=${this.provider === 'bothub'}>Bothub</option>
                    </select>
                    <div class="config-hint">${this.i18n.t('llm_config_editor.hint_provider')}</div>
                </div>
                
                ${showCredentials ? html`
                    <div class="credentials-section">
                        <div class="credentials-title">${this.i18n.t('llm_config_editor.credentials_for', { provider: this.provider })}</div>
                        
                        <div class="config-field">
                            <label class="config-label">${this.i18n.t('llm_config_editor.label_api_key')}</label>
                            <input
                                type="text"
                                class="config-input"
                                placeholder=${this.i18n.t('llm_config_editor.placeholder_api_key')}
                                .value=${this.apiKey}
                                @input=${this._onApiKeyChange}
                            />
                            <div class="config-hint">${this.i18n.t('llm_config_editor.hint_api_key')}</div>
                        </div>
                        
                        <div class="config-field">
                            <label class="config-label">${this.i18n.t('llm_config_editor.label_base_url')}</label>
                            <input
                                type="text"
                                class="config-input"
                                placeholder=${this.i18n.t('llm_config_editor.placeholder_base_url')}
                                .value=${this.baseUrl}
                                @input=${this._onBaseUrlChange}
                            />
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('llm-config-editor', LLMConfigEditor);

