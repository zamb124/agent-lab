/**
 * flows-remote-flow-editor — remote_flow node (A2A endpoint).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-code-editor.js';

export class FlowsRemoteFlowEditor extends PlatformElement {
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
                .nodeType=${'remote_flow'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('remote_flow_editor.field_url')}</label>
                    <input
                        type="url"
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.url || ''}
                        @input=${(e) => this._onConfigChange('url', e.target.value)}
                    />
                    <label>${this.t('remote_flow_editor.field_skill_id')}</label>
                    <input
                        type="text"
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.skill_id || ''}
                        @input=${(e) => this._onConfigChange('skill_id', e.target.value)}
                    />
                    <label>${this.t('remote_flow_editor.field_auth_headers')}</label>
                    <flows-code-editor
                        language="json"
                        .value=${JSON.stringify(cfg.auth_headers || {}, null, 2)}
                        @change=${(e) => {
                            try {
                                this._onConfigChange('auth_headers', JSON.parse(e.detail?.value || '{}'));
                            } catch { /* invalid */ }
                        }}
                    ></flows-code-editor>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-remote-flow-editor', FlowsRemoteFlowEditor);
