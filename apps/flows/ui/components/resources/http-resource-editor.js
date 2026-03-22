/**
 * HTTPResourceEditor - редактор HTTP ресурса
 */
import { html, css } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class HTTPResourceEditor extends BaseResourceEditor {
    static styles = [
        BaseResourceEditor.styles,
        css`
            .headers-textarea {
                font-family: var(--font-mono);
                font-size: var(--text-sm);
            }
        `
    ];

    getIconName() {
        return 'globe';
    }

    getColor() {
        return '#06b6d4';
    }

    getTypeName() {
        return 'HTTP Resource';
    }

    renderFields() {
        const baseUrl = this.resourceConfig?.base_url || '';
        const headers = this.resourceConfig?.headers || {};
        const headersJson = JSON.stringify(headers, null, 2);
        const timeout = this.resourceConfig?.timeout || 30;
        const authType = this.resourceConfig?.auth_type || '';
        const authValue = this.resourceConfig?.auth_value || '';

        return html`
            <div class="form-group">
                <label class="form-label">Base URL</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${baseUrl}
                    @input=${(e) => this._onInputChange('base_url', e.target.value)}
                    placeholder="https://api.example.com"
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">Headers (JSON)</label>
                <textarea 
                    class="form-input headers-textarea"
                    .value=${headersJson}
                    @input=${(e) => this._onHeadersChange(e.target.value)}
                    placeholder='{"Content-Type": "application/json"}'
                    rows="4"
                ></textarea>
            </div>
            
            <div class="form-group">
                <label class="form-label">Timeout (sec)</label>
                <input 
                    type="number" 
                    class="form-input"
                    .value=${timeout}
                    min="1"
                    max="300"
                    @input=${(e) => this._onInputChange('timeout', parseInt(e.target.value) || 30)}
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">Auth Type</label>
                <select 
                    class="form-select"
                    .value=${authType}
                    @change=${(e) => this._onInputChange('auth_type', e.target.value)}
                >
                    <option value="">None</option>
                    <option value="bearer">Bearer Token</option>
                    <option value="basic">Basic Auth</option>
                    <option value="api_key">API Key</option>
                </select>
            </div>
            
            ${authType ? html`
                <div class="form-group">
                    <label class="form-label">Auth Value</label>
                    <input 
                        type="password" 
                        class="form-input"
                        .value=${authValue}
                        @input=${(e) => this._onInputChange('auth_value', e.target.value)}
                        placeholder="@var:API_KEY"
                    />
                    <span class="form-hint">Токен или @var:SECRET_NAME</span>
                </div>
            ` : ''}
        `;
    }

    _onHeadersChange(value) {
        try {
            const parsed = JSON.parse(value);
            this._onInputChange('headers', parsed);
        } catch (e) {
            // Игнорируем ошибки парсинга при вводе
        }
    }
}

customElements.define('http-resource-editor', HTTPResourceEditor);
