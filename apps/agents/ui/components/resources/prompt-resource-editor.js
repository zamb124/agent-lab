/**
 * PromptResourceEditor - редактор prompt ресурса
 */
import { html, css } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class PromptResourceEditor extends BaseResourceEditor {
    static styles = [
        BaseResourceEditor.styles,
        css`
            .template-textarea {
                min-height: 200px;
                font-family: var(--font-mono);
                font-size: var(--text-sm);
            }
        `
    ];

    getIconName() {
        return 'chat';
    }

    getColor() {
        return '#10b981';
    }

    getTypeName() {
        return 'Prompt Resource';
    }

    renderFields() {
        const template = this.resourceConfig?.template || '';
        const variables = this.resourceConfig?.variables || {};
        const variablesJson = JSON.stringify(variables, null, 2);

        return html`
            <div class="form-group">
                <label class="form-label">Template</label>
                <textarea 
                    class="form-input template-textarea"
                    .value=${template}
                    @input=${(e) => this._onInputChange('template', e.target.value)}
                    placeholder="Ты {{ role }}. Твоя задача: {{ task }}"
                ></textarea>
                <span class="form-hint">Jinja2 шаблон промпта</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Default Variables (JSON)</label>
                <textarea 
                    class="form-input"
                    .value=${variablesJson}
                    @input=${(e) => this._onVariablesChange(e.target.value)}
                    placeholder='{"role": "assistant"}'
                    rows="4"
                ></textarea>
                <span class="form-hint">Значения переменных по умолчанию</span>
            </div>
        `;
    }

    _onVariablesChange(value) {
        try {
            const parsed = JSON.parse(value);
            this._onInputChange('variables', parsed);
        } catch (e) {
            // Игнорируем ошибки парсинга при вводе
        }
    }
}

customElements.define('prompt-resource-editor', PromptResourceEditor);
