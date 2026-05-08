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
import '@platform/lib/components/fields/platform-field.js';
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

    _strDetail(e, ctx) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`flows-files-resource-editor: ${ctx} change detail`);
        }
        if (!('value' in d)) {
            throw new Error(`flows-files-resource-editor: ${ctx} detail.value`);
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error(`flows-files-resource-editor: ${ctx} string required`);
        }
        return v;
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
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.bucket')}
                            .value=${bucket}
                            @change=${(e) => this._emitConfig({ bucket: this._strDetail(e, 'bucket') })}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.prefix')}
                            .value=${prefix}
                            @change=${(e) => this._emitConfig({ prefix: this._strDetail(e, 'prefix') })}
                        ></platform-field>
                    </div>
                    <platform-field
                        mode="edit"
                        type="string"
                        input-type="url"
                        .label=${this.t('files_resource_editor.endpoint_url')}
                        .placeholder=${'https://s3.amazonaws.com'}
                        .value=${endpoint}
                        @change=${(e) => {
                            const v = this._strDetail(e, 'endpoint_url');
                            this._emitConfig({ endpoint_url: v.length > 0 ? v : null });
                        }}
                    ></platform-field>
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.access_key_id')}
                            .value=${accessKey}
                            @change=${(e) => {
                                const v = this._strDetail(e, 'access_key_id');
                                this._emitConfig({ access_key_id: v.length > 0 ? v : null });
                            }}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.region')}
                            .value=${region}
                            @change=${(e) => {
                                const v = this._strDetail(e, 'region');
                                this._emitConfig({ region: v.length > 0 ? v : 'us-east-1' });
                            }}
                        ></platform-field>
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
