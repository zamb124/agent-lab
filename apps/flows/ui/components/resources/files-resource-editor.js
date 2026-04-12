/**
 * FilesResourceEditor - редактор files ресурса
 */
import { html } from 'lit';
import { BaseResourceEditor } from './base-resource-editor.js';

export class FilesResourceEditor extends BaseResourceEditor {
    getIconName() {
        return 'folder';
    }

    getColor() {
        return '#f59e0b';
    }

    getTypeName() {
        return 'Files Resource';
    }

    renderFields() {
        const bucket = this.resourceConfig?.bucket || '';
        const prefix = this.resourceConfig?.prefix || '';
        const endpointUrl = this.resourceConfig?.endpoint_url || '';
        const region = this.resourceConfig?.region || 'us-east-1';

        return html`
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.files.label_bucket')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${bucket}
                    @input=${(e) => this._onInputChange('bucket', e.target.value)}
                    placeholder="my-bucket"
                />
                <span class="form-hint">${this.i18n.t('resource_editor.files.hint_bucket')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.files.label_prefix')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${prefix}
                    @input=${(e) => this._onInputChange('prefix', e.target.value)}
                    placeholder="uploads/"
                />
                <span class="form-hint">${this.i18n.t('resource_editor.files.hint_prefix')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.files.label_endpoint')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${endpointUrl}
                    @input=${(e) => this._onInputChange('endpoint_url', e.target.value)}
                    placeholder="http://minio:9000"
                />
                <span class="form-hint">${this.i18n.t('resource_editor.files.hint_endpoint')}</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">${this.i18n.t('resource_editor.files.label_region')}</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${region}
                    @input=${(e) => this._onInputChange('region', e.target.value)}
                    placeholder="us-east-1"
                />
            </div>
        `;
    }
}

customElements.define('files-resource-editor', FilesResourceEditor);
