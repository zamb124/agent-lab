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
                <label class="form-label">${this.i18n.t('resource_editor.secret.label_key')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${key}
                    @input=${(e) => this._onInputChange('key', e.target.value)}
                    placeholder=${this.i18n.t('resource_editor.secret.placeholder_key')}
                />
                <span class="form-hint">${this.i18n.t('resource_editor.secret.hint_key')}</span>
            </div>
        `;
    }
}

customElements.define('secret-resource-editor', SecretResourceEditor);
