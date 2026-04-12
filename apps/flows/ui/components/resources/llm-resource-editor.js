/**
 * LLMResourceEditor - редактор LLM ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class LLMResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'bot';
    }

    getColor() {
        return '#ec4899';
    }

    getTypeName() {
        return 'LLM Resource';
    }

    renderFields() {
        const provider = this.resourceConfig?.provider || 'openrouter';
        const model = this.resourceConfig?.model || '';
        const temperature = this.resourceConfig?.temperature ?? 0.7;
        const maxTokens = this.resourceConfig?.max_tokens || '';
        const apiKey = this.resourceConfig?.api_key || '';
        const baseUrl = this.resourceConfig?.base_url || '';

        return html`
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_provider')}</label>
                <select 
                    class="form-select"
                    .value=${provider}
                    @change=${(e) => this._onInputChange('provider', e.target.value)}
                >
                    <option value="openrouter">OpenRouter</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="bothub">BotHub</option>
                    <option value="provider_litserve">Provider LitServe</option>
                </select>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_model')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${model}
                    @input=${(e) => this._onInputChange('model', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.llm.placeholder_model')}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.llm.hint_model')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_temperature')}</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${temperature}
                    min="0"
                    max="2"
                    step="0.1"
                    @input=${(e) => this._onInputChange('temperature', parseFloat(e.target.value) || 0.7)}
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_max_tokens')}</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${maxTokens}
                    @input=${(e) => this._onInputChange('max_tokens', parseInt(e.target.value) || null)}
                    placeholder=${this.i18n.t('resource_editor.llm.placeholder_max_tokens')}
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_api_key')}</label>
                <input 
                    type="password" 
                    class="form-input"
                    .value=${apiKey}
                    @input=${(e) => this._onInputChange('api_key', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.llm.placeholder_api_key')}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.llm.hint_api_key')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.llm.label_base_url')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${baseUrl}
                    @input=${(e) => this._onInputChange('base_url', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.llm.placeholder_base_url')}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.llm.hint_base_url')}</span>
            </div>
        `;
    }
}

customElements.define('llm-resource-editor', LLMResourceEditor);
