/**
 * SecretResourceEditor - редактор secret ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class SecretResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'key';
    }

    getColor() {
        return '#ef4444';
    }

    getTypeName() {
        return 'Secret Resource';
    }

    renderFields() {
        const key = this.resourceConfig?.key || '';

        return html`
            <div class="form-group">
                <label class="form-label">Secret Key</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${key}
                    @input=${(e) => this._onInputChange('key', e.target.value)}
                    placeholder="@var:SECRET_NAME"
                />
                <span class="form-hint">Ссылка на секрет в формате @var:SECRET_NAME</span>
            </div>
        `;
    }
}

customElements.define('secret-resource-editor', SecretResourceEditor);
