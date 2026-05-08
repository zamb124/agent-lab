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
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/prompt-editor.js';
import { asObject, asString } from '../../_helpers/flows-resolvers.js';

export class FlowsHitlNodeEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
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
            .queue-pick .queue-search-input {
                flex: 1;
                min-width: 0;
            }
            .queue-pick platform-field {
                flex: 1;
                min-width: 0;
            }
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
        this.branchId = '';
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

    _onQueueSearchInput(e) {
        this._queueSearch = e.target.value;
    }

    _onSlugField(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: slug change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: slug detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-hitl-node-editor: slug string required');
        }
        this._onQueueSlug(v);
    }

    _onHandoffMode(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: handoff change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: handoff detail.value');
        }
        const raw = d.value;
        if (typeof raw !== 'string') {
            throw new Error('flows-hitl-node-editor: handoff string required');
        }
        const v = raw === 'takeover' ? 'takeover' : 'single_reply';
        this._emitPatch({ operator_handoff_mode: v });
    }

    _onTaskTitle(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: task title change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: task title detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-hitl-node-editor: task title string required');
        }
        this._emitPatch({ operator_task_title: v });
    }

    _onUserMessage(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: user message change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: user message detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-hitl-node-editor: user message string required');
        }
        this._emitPatch({ operator_user_message: v });
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
        const handoffValues = [
            { value: 'single_reply', label: this.t('hitl_node_editor.single_reply') },
            { value: 'takeover', label: this.t('hitl_node_editor.takeover') },
        ];
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
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
                                type="text"
                                class="queue-search-input"
                                data-canon="search-as-you-type"
                                placeholder=${this.t('hitl_node_editor.queue_picker')}
                                .value=${this._queueSearch}
                                @input=${this._onQueueSearchInput}
                            />
                            <platform-field
                                mode="edit"
                                type="string"
                                .value=${slug}
                                @change=${this._onSlugField}
                            ></platform-field>
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
                    <platform-field
                        mode="edit"
                        type="enum"
                        .label=${this.t('hitl_node_editor.handoff_mode')}
                        .value=${handoffMode}
                        .config=${{ values: handoffValues }}
                        @change=${this._onHandoffMode}
                    ></platform-field>
                    <platform-field
                        mode="edit"
                        type="string"
                        .label=${this.t('hitl_node_editor.task_title')}
                        .value=${taskTitle}
                        @change=${this._onTaskTitle}
                    ></platform-field>
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
