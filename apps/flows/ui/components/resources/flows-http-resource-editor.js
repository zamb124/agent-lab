/**
 * flows-http-resource-editor — ресурс http (REST endpoint config).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-code-editor.js';

export class FlowsHttpResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); padding: 0 var(--space-3); }
            .field input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(config) {
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...(this.resource?.config || {}), ...config } } });
    }

    render() {
        const cfg = this.resource?.config || {};
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'http'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('http_resource_editor.field_base_url')}</label>
                        <input
                            type="url"
                            .value=${cfg.base_url || ''}
                            @input=${(e) => this._emitConfig({ base_url: e.target.value })}
                        />
                    </div>
                    <div class="field">
                        <label>${this.t('http_resource_editor.field_default_headers')}</label>
                        <flows-code-editor
                            language="json"
                            .value=${JSON.stringify(cfg.default_headers || {}, null, 2)}
                            @change=${(e) => {
                                try {
                                    this._emitConfig({ default_headers: JSON.parse(e.detail?.value || '{}') });
                                } catch { /* invalid */ }
                            }}
                        ></flows-code-editor>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-http-resource-editor', FlowsHttpResourceEditor);
