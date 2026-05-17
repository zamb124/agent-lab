/**
 * flows-hitl-node-editor — редактор HITL-ноды (передача оператору).
 *
 * Поля точно по `NodeConfig` (apps/flows/src/models/node_config.py):
 *   - operator_queue_slug
 *   - operator_handoff_mode: 'single_reply' | 'takeover'
 *   - operator_task_title
 *   - operator_user_message (с подсказкой `@var:`)
 *
 * Очередь: flows-searchable-combobox + useResource('flows/operator_queues').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '../editors/flows-searchable-combobox.js';
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
        dataflowNode: { type: Object },
        expanded: { type: Boolean, reflect: true },
        embedded: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .queue-combo {
                margin-top: var(--space-1);
            }
            .hitl-handoff-task-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                margin-bottom: var(--space-5);
            }
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
        this.dataflowNode = null;
        this.expanded = false;
        this.embedded = false;
        this._queues = this.useResource('flows/operator_queues', { autoload: true });
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _onQueueCombobox(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: queue combobox detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: queue combobox detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-hitl-node-editor: queue slug string required');
        }
        this._emitPatch({ operator_queue_slug: v });
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
        const queueOptions = queues.reduce((acc, q) => {
            const slugVal = asString(q.slug);
            if (slugVal.length === 0) {
                return acc;
            }
            const nameVal = asString(q.name);
            const label = nameVal.length > 0 ? nameVal : slugVal;
            acc.push({ value: slugVal, label });
            return acc;
        }, []);
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
                .dataflowNode=${this.dataflowNode}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('hitl_node_editor.queue_slug')}</label>
                        <flows-searchable-combobox
                            class="queue-combo"
                            .value=${slug}
                            .options=${queueOptions}
                            placeholder=${this.t('hitl_node_editor.queue_picker')}
                            emptyLabel=${this.t('hitl_node_editor.queue_clear')}
                            ariaLabel=${this.t('hitl_node_editor.queue_aria')}
                            @change=${this._onQueueCombobox}
                        ></flows-searchable-combobox>
                    </div>
                    <div class="hitl-handoff-task-stack">
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
                    </div>
                    <div class="field">
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
