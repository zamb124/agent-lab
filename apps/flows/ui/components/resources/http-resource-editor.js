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
                <label class="form-label">${this.i18n.t('resource_editor.http.label_base_url')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${baseUrl}
                    @input=${(e) => this._onInputChange('base_url', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.http.placeholder_base_url')}
                />
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.http.label_headers')}</label>
                <textarea 
                    class="form-input headers-textarea"
                    .value=${headersJson}
                    @input=${(e) => this._onHeadersChange(e.target.value)}
                    placeholder='{"Content-Type": "application/json"}'
                    rows="4"
                ></textarea>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.http.label_timeout')}</label>
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
                <label class="form-label">${this.i18n.t('resource_editor.http.label_auth_type')}</label>
                <select 
                    class="form-select"
                    .value=${authType}
                    @change=${(e) => this._onInputChange('auth_type', e.target.value)}
                >
                    <option value="">${this.i18n.t('resource_editor.http.auth_none')}</option>
                    <option value="bearer">${this.i18n.t('resource_editor.http.auth_bearer')}</option>
                    <option value="basic">${this.i18n.t('resource_editor.http.auth_basic')}</option>
                    <option value="api_key">${this.i18n.t('resource_editor.http.auth_api_key')}</option>
                </select>
            </div>
            
            ${authType ? html`
                <div class="form-group">
                    <label class="form-label">${this.i18n.t('resource_editor.http.label_auth_value')}</label>
                    <input 
                        type="password" 
                        class="form-input"
                        .value=${authValue}
                        @input=${(e) => this._onInputChange('auth_value', e.target.value)}
                        placeholder=${this.i18n.t('resource_editor.http.placeholder_auth_value')}
                    />
                    <span class="form-hint">${this.i18n.t('resource_editor.http.hint_auth_value')}</span>
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
