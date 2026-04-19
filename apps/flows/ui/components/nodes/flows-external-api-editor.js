/**
 * flows-external-api-editor — http_call / external_api node.
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-editor.js';

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];

export class FlowsExternalApiEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
    };

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
    }

    _onConfigChange(field, value) {
        const cfg = { ...(this.nodeConfig?.config || {}), [field]: value };
        this.emit('change', { nodeId: this.nodeId, patch: { config: cfg } });
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'external_api'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('external_api_editor.field_method')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.method || 'GET'}
                        @change=${(e) => this._onConfigChange('method', e.target.value)}
                    >
                        ${HTTP_METHODS.map((m) => html`<option value=${m}>${m}</option>`)}
                    </select>
                    <label>${this.t('external_api_editor.field_url')}</label>
                    <input
                        type="url"
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.url || ''}
                        @input=${(e) => this._onConfigChange('url', e.target.value)}
                    />
                    <label>${this.t('external_api_editor.field_headers')}</label>
                    <flows-code-editor
                        language="json"
                        .value=${JSON.stringify(cfg.headers || {}, null, 2)}
                        @change=${(e) => {
                            try {
                                this._onConfigChange('headers', JSON.parse(e.detail?.value || '{}'));
                            } catch { /* invalid */ }
                        }}
                    ></flows-code-editor>
                    <label>${this.t('external_api_editor.field_body')}</label>
                    <flows-code-editor
                        language="json"
                        .value=${JSON.stringify(cfg.body || {}, null, 2)}
                        @change=${(e) => {
                            try {
                                this._onConfigChange('body', JSON.parse(e.detail?.value || '{}'));
                            } catch { /* invalid */ }
                        }}
                    ></flows-code-editor>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-external-api-editor', FlowsExternalApiEditor);
