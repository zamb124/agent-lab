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
                <label class="form-label">Bucket</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${bucket}
                    @input=${(e) => this._onInputChange('bucket', e.target.value)}
                    placeholder="my-bucket"
                />
                <span class="form-hint">S3 bucket name</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Prefix</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${prefix}
                    @input=${(e) => this._onInputChange('prefix', e.target.value)}
                    placeholder="uploads/"
                />
                <span class="form-hint">Префикс пути (опционально)</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Endpoint URL</label>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${endpointUrl}
                    @input=${(e) => this._onInputChange('endpoint_url', e.target.value)}
                    placeholder="http://minio:9000"
                />
                <span class="form-hint">S3 endpoint URL (для MinIO)</span>
            </div>
            
            <div class="form-group">
                <label class="form-label">Region</label>
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
