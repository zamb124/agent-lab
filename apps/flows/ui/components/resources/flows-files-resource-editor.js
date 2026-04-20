/**
 * flows-files-resource-editor — ресурс files (S3 хранилище).
 *
 * Поля точно по `FilesResourceConfig`:
 *   - bucket (str, required)
 *   - prefix (str)
 *   - endpoint_url (str)
 *   - access_key_id (str)
 *   - secret_access_key (str, через variable-input)
 *   - region (str, default 'us-east-1')
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-variable-input.js';

export class FlowsFilesResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body { padding: 0 var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const bucket = typeof cfg.bucket === 'string' ? cfg.bucket : '';
        const prefix = typeof cfg.prefix === 'string' ? cfg.prefix : '';
        const endpoint = typeof cfg.endpoint_url === 'string' ? cfg.endpoint_url : '';
        const accessKey = typeof cfg.access_key_id === 'string' ? cfg.access_key_id : '';
        const secretKey = typeof cfg.secret_access_key === 'string' ? cfg.secret_access_key : '';
        const region = typeof cfg.region === 'string' ? cfg.region : 'us-east-1';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'files'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="grid">
                        <div class="field">
                            <label>${this.t('files_resource_editor.bucket')}</label>
                            <input type="text" .value=${bucket}
                                @input=${(e) => this._emitConfig({ bucket: e.target.value })} />
                        </div>
                        <div class="field">
                            <label>${this.t('files_resource_editor.prefix')}</label>
                            <input type="text" .value=${prefix}
                                @input=${(e) => this._emitConfig({ prefix: e.target.value })} />
                        </div>
                    </div>
                    <div class="field">
                        <label>${this.t('files_resource_editor.endpoint_url')}</label>
                        <input type="url" placeholder="https://s3.amazonaws.com" .value=${endpoint}
                            @input=${(e) => this._emitConfig({ endpoint_url: e.target.value.length > 0 ? e.target.value : null })} />
                    </div>
                    <div class="grid">
                        <div class="field">
                            <label>${this.t('files_resource_editor.access_key_id')}</label>
                            <input type="text" .value=${accessKey}
                                @input=${(e) => this._emitConfig({ access_key_id: e.target.value.length > 0 ? e.target.value : null })} />
                        </div>
                        <div class="field">
                            <label>${this.t('files_resource_editor.region')}</label>
                            <input type="text" .value=${region}
                                @input=${(e) => this._emitConfig({ region: e.target.value.length > 0 ? e.target.value : 'us-east-1' })} />
                        </div>
                    </div>
                    <div class="field">
                        <label>${this.t('files_resource_editor.secret_access_key')}</label>
                        <flows-variable-input
                            .value=${secretKey}
                            @change=${(e) => { const v = e.detail?.value; this._emitConfig({ secret_access_key: typeof v === 'string' && v.length > 0 ? v : null }); }}
                        ></flows-variable-input>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-files-resource-editor', FlowsFilesResourceEditor);
