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
                <label class="form-label">Provider</label>
                <select 
                    class="form-select"
                    .value=${provider}
                    @change=${(e) => this._onInputChange('provider', e.target.value)}
                >
                    <option value="openrouter">OpenRouter</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="bothub">BotHub</option>
                </select>
            </div>
            
            <div class="form-group">
                <label class="form-label">Model</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${model}
                    @input=${(e) => this._onInputChange('model', e.target.value)}
                    placeholder="openai/gpt-4o"
                />
                <span class="form-hint">Полное имя модели</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Temperature</label>
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
                <label class="form-label">Max Tokens</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${maxTokens}
                    @input=${(e) => this._onInputChange('max_tokens', parseInt(e.target.value) || null)}
                    placeholder="По умолчанию модели"
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">API Key</label>
                <input 
                    type="password" 
                    class="form-input"
                    .value=${apiKey}
                    @input=${(e) => this._onInputChange('api_key', e.target.value)}
                    placeholder="@var:OPENROUTER_KEY"
                />
                <span class="form-hint">Прямой ключ или @var:SECRET_NAME</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Base URL</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${baseUrl}
                    @input=${(e) => this._onInputChange('base_url', e.target.value)}
                    placeholder="https://openrouter.ai/api/v1"
                />
                <span class="form-hint">Base URL провайдера (опционально)</span>
            </div>
        `;
    }
}

customElements.define('llm-resource-editor', LLMResourceEditor);
