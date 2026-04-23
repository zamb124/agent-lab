/**
 * flows-hitl-node-editor — редактор HITL-ноды (передача оператору).
 *
 * Поля точно по `NodeConfig` (apps/flows/src/models/node_config.py):
 *   - operator_queue_slug
 *   - operator_handoff_mode: 'single_reply' | 'takeover'
 *   - operator_task_title
 *   - operator_user_message (с подсказкой `@var:`)
 *
 * Picker очередей: search + список через useResource('flows/operator_queues').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import { asObject, asString } from '../../_helpers/flows-resolvers.js';

export class FlowsHitlNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
        _queueSearch: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input, select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
            .queue-pick { display: flex; gap: var(--space-2); align-items: stretch; }
            .queue-pick input { flex: 1; }
            .queue-list {
                margin-top: var(--space-1);
                max-height: 160px; overflow-y: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .queue-item {
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                font-size: var(--text-sm);
                display: flex; justify-content: space-between; gap: var(--space-2);
            }
            .queue-item:hover { background: var(--glass-solid-strong); }
            .queue-item .slug { color: var(--text-tertiary); font-family: var(--font-mono, monospace); font-size: var(--text-xs); }
            .queue-item[active] { background: var(--accent-subtle); color: var(--accent); }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'hitl_node';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
        this._queueSearch = '';
        this._queues = this.useResource('flows/operator_queues', { autoload: true });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onQueueSlug(slug) {
        this._emitPatch({ operator_queue_slug: slug });
    }

    _onHandoffMode(e) {
        const v = e.target.value === 'takeover' ? 'takeover' : 'single_reply';
        this._emitPatch({ operator_handoff_mode: v });
    }

    _onTaskTitle(e) {
        this._emitPatch({ operator_task_title: e.target.value });
    }

    _onUserMessage(e) {
        const value = typeof e.detail?.value === 'string' ? e.detail.value : '';
        this._emitPatch({ operator_user_message: value });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const slug = typeof cfg.operator_queue_slug === 'string' ? cfg.operator_queue_slug : '';
        const handoffMode = cfg.operator_handoff_mode === 'takeover' ? 'takeover' : 'single_reply';
        const taskTitle = typeof cfg.operator_task_title === 'string' ? cfg.operator_task_title : '';
        const userMessage = typeof cfg.operator_user_message === 'string' ? cfg.operator_user_message : '';
        const queues = Array.isArray(this._queues.items) ? this._queues.items : [];
        const filtered = this._queueSearch.trim().length === 0
            ? queues
            : queues.filter((q) => {
                const search = this._queueSearch.toLowerCase();
                return asString(q.slug).toLowerCase().includes(search)
                    || asString(q.name).toLowerCase().includes(search);
            });
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'hitl_node'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('hitl_node_editor.queue_slug')}</label>
                        <div class="queue-pick">
                            <input
                                type="text" placeholder=${this.t('hitl_node_editor.queue_picker')}
                                .value=${this._queueSearch}
                                @input=${(e) => { this._queueSearch = e.target.value; }}
                            />
                            <input type="text" .value=${slug}
                                @input=${(e) => this._onQueueSlug(e.target.value)} />
                        </div>
                        ${filtered.length > 0 ? html`
                            <div class="queue-list">
                                ${filtered.map((q) => html`
                                    <div class="queue-item" ?active=${q.slug === slug}
                                        @click=${() => this._onQueueSlug(q.slug)}>
                                        <span>${q.name}</span>
                                        <span class="slug">${q.slug}</span>
                                    </div>
                                `)}
                            </div>
                        ` : ''}
                    </div>
                    <div class="field">
                        <label>${this.t('hitl_node_editor.handoff_mode')}</label>
                        <select .value=${handoffMode} @change=${this._onHandoffMode}>
                            <option value="single_reply" ?selected=${handoffMode === 'single_reply'}>${this.t('hitl_node_editor.single_reply')}</option>
                            <option value="takeover" ?selected=${handoffMode === 'takeover'}>${this.t('hitl_node_editor.takeover')}</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>${this.t('hitl_node_editor.task_title')}</label>
                        <input type="text" .value=${taskTitle} @input=${this._onTaskTitle} />
                    </div>
                    <div class="field">
                        <label>${this.t('hitl_node_editor.user_message')}</label>
                        <prompt-editor
                            .value=${userMessage}
                            .variables=${this.flowVariables && typeof this.flowVariables === 'object' ? this.flowVariables : {}}
                            label=${this.t('hitl_node_editor.user_message')}
                            @change=${this._onUserMessage}
                        ></prompt-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-hitl-node-editor', FlowsHitlNodeEditor);
