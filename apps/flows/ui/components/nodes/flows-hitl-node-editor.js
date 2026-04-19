/**
 * flows-hitl-node-editor — hitl_node (operator handoff).
 */

import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';

export class FlowsHitlNodeEditor extends PlatformElement {
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
        this._queues = this.useResource('flows/operator_queues', { autoload: true });
    }

    _onConfigChange(field, value) {
        const cfg = { ...(this.nodeConfig?.config || {}), [field]: value };
        this.emit('change', { nodeId: this.nodeId, patch: { config: cfg } });
    }

    render() {
        const cfg = this.nodeConfig?.config || {};
        const queues = this._queues.items || [];
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${'hitl_node'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <label>${this.t('hitl_node_editor.queue_slug_label')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.assignee_queue || ''}
                        @change=${(e) => this._onConfigChange('assignee_queue', e.target.value)}
                    >
                        <option value="">—</option>
                        ${queues.map((q) => html`<option value=${q.slug}>${q.name} (${q.slug})</option>`)}
                    </select>
                    <label>${this.t('hitl_node_editor.task_title_label')}</label>
                    <input
                        type="text"
                        style="display:block;width:100%;padding:var(--space-2);margin-bottom:var(--space-3);"
                        .value=${cfg.task_title || ''}
                        @input=${(e) => this._onConfigChange('task_title', e.target.value)}
                    />
                    <label>${this.t('hitl_node_editor.user_message_label')}</label>
                    <textarea
                        style="display:block;width:100%;padding:var(--space-2);min-height:80px;margin-bottom:var(--space-3);"
                        .value=${cfg.user_facing_message || ''}
                        @input=${(e) => this._onConfigChange('user_facing_message', e.target.value)}
                    ></textarea>
                    <label>${this.t('hitl_node_editor.handoff_mode_label')}</label>
                    <select
                        style="display:block;width:100%;padding:var(--space-2);"
                        .value=${cfg.handoff_mode || 'single_reply'}
                        @change=${(e) => this._onConfigChange('handoff_mode', e.target.value)}
                    >
                        <option value="single_reply">${this.t('hitl_node_editor.handoff_mode_single_reply')}</option>
                        <option value="takeover">${this.t('hitl_node_editor.handoff_mode_takeover')}</option>
                    </select>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-hitl-node-editor', FlowsHitlNodeEditor);
