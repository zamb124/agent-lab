/**
 * flows-channel-node-editor — channel node (отправка через channel).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';

export class FlowsChannelNodeEditor extends PlatformElement {
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
                .nodeType=${'channel'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('channel_node_editor.field_channel_type')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.channel_type || 'a2a'}
                        @change=${(e) => this._onConfigChange('channel_type', e.target.value)}
                    >
                        <option value="a2a">a2a</option>
                        <option value="webhook">webhook</option>
                        <option value="telegram">telegram</option>
                    </select>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-channel-node-editor', FlowsChannelNodeEditor);
