/**
 * flows-http-resource-editor — ресурс http.
 *
 * Поля точно по `HTTPResourceConfig`:
 *   - base_url (str)
 *   - headers (dict<str, str>)
 *   - timeout (int)
 *   - auth_type ('none' | 'bearer' | 'basic' | 'api_key')
 *   - auth_value (str)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-resource-editor.js';
import '../editors/flows-json-field-editor.js';
import '../editors/flows-variable-input.js';
import { asString } from '../../_helpers/flows-resolvers.js';

const AUTH_TYPES = Object.freeze(['', 'bearer', 'basic', 'api_key']);

export class FlowsHttpResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body { padding: 0 var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
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
        this.compactHeader = false;
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    _strDetail(e, ctx) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`flows-http-resource-editor: ${ctx} change detail`);
        }
        if (!('value' in d)) {
            throw new Error(`flows-http-resource-editor: ${ctx} detail.value`);
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error(`flows-http-resource-editor: ${ctx} string required`);
        }
        return v;
    }

    _onHttpTimeout(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-http-resource-editor: timeout change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-http-resource-editor: timeout detail.value');
        }
        const v = d.value;
        if (v === null) {
            this._emitConfig({ timeout: 30 });
            return;
        }
        if (typeof v !== 'number' || !Number.isFinite(v)) {
            throw new Error('flows-http-resource-editor: timeout number required');
        }
        const n = Math.floor(v);
        this._emitConfig({ timeout: n > 0 ? n : 30 });
    }

    _onAuthType(e) {
        const raw = this._strDetail(e, 'auth_type');
        this._emitConfig({ auth_type: raw.length > 0 ? raw : null });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const baseUrl = typeof cfg.base_url === 'string' ? cfg.base_url : '';
        const timeout = typeof cfg.timeout === 'number' ? cfg.timeout : 30;
        const authType = typeof cfg.auth_type === 'string' ? cfg.auth_type : '';
        const authValue = typeof cfg.auth_value === 'string' ? cfg.auth_value : '';
        const headersJson = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        const authEnumValues = AUTH_TYPES.map((t) => ({
            value: t,
            label: t === '' ? this.t('http_resource_editor.auth_none') : this.t(`http_resource_editor.auth_${t}`),
        }));
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'http'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <platform-field
                        mode="edit"
                        type="string"
                        input-type="url"
                        .label=${this.t('http_resource_editor.base_url')}
                        .placeholder=${'https://api.example.com'}
                        .value=${baseUrl}
                        @change=${(e) => this._emitConfig({ base_url: this._strDetail(e, 'base_url') })}
                    ></platform-field>
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="integer"
                            .label=${this.t('http_resource_editor.timeout')}
                            .value=${timeout}
                            @change=${this._onHttpTimeout}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('http_resource_editor.auth_type')}
                            .value=${authType}
                            .config=${{ values: authEnumValues }}
                            @change=${this._onAuthType}
                        ></platform-field>
                    </div>
                    ${authType ? html`
                        <div class="field">
                            <label>${this.t('http_resource_editor.auth_value')}</label>
                            <flows-variable-input
                                .value=${authValue}
                                @change=${(e) => this._emitConfig({ auth_value: asString(e.detail?.value) })}
                            ></flows-variable-input>
                        </div>
                    ` : ''}
                    <div class="field">
                        <label>${this.t('http_resource_editor.headers')}</label>
                        <flows-json-field-editor
                            .value=${headersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._emitConfig({ headers: e.detail.parsed && typeof e.detail.parsed === 'object' ? e.detail.parsed : {} }); }}
                        ></flows-json-field-editor>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-http-resource-editor', FlowsHttpResourceEditor);
