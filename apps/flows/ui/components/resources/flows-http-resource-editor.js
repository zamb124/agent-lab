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
import './flows-base-resource-editor.js';
import '../editors/flows-json-field-editor.js';
import '../editors/flows-variable-input.js';
import { asString } from '../../_helpers/flows-resolvers.js';

const AUTH_TYPES = Object.freeze(['', 'bearer', 'basic', 'api_key']);

export class FlowsHttpResourceEditor extends PlatformElement {
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
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const baseUrl = typeof cfg.base_url === 'string' ? cfg.base_url : '';
        const timeout = typeof cfg.timeout === 'number' ? cfg.timeout : 30;
        const authType = typeof cfg.auth_type === 'string' ? cfg.auth_type : '';
        const authValue = typeof cfg.auth_value === 'string' ? cfg.auth_value : '';
        const headersJson = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'http'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="field">
                        <label>${this.t('http_resource_editor.base_url')}</label>
                        <input type="url" placeholder="https://api.example.com"
                            .value=${baseUrl}
                            @input=${(e) => this._emitConfig({ base_url: e.target.value })} />
                    </div>
                    <div class="grid">
                        <div class="field">
                            <label>${this.t('http_resource_editor.timeout')}</label>
                            <input type="number" min="1" step="1"
                                .value=${String(timeout)}
                                @input=${(e) => {
                                    const v = parseInt(e.target.value, 10);
                                    this._emitConfig({ timeout: Number.isFinite(v) && v > 0 ? v : 30 });
                                }} />
                        </div>
                        <div class="field">
                            <label>${this.t('http_resource_editor.auth_type')}</label>
                            <select .value=${authType}
                                @change=${(e) => this._emitConfig({ auth_type: e.target.value.length > 0 ? e.target.value : null })}>
                                ${AUTH_TYPES.map((t) => html`<option value=${t} ?selected=${t === authType}>${t === '' ? this.t('http_resource_editor.auth_none') : this.t(`http_resource_editor.auth_${t}`)}</option>`)}
                            </select>
                        </div>
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
