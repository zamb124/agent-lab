/**
 * flows-hitl-node-editor — редактор HITL-ноды (передача задачи в очередь).
 *
 * Поля точно по `NodeConfig` (apps/flows/src/models/node_config.py):
 *   - work_queue_slug
 *   - handoff_mode: 'single_reply' | 'takeover'
 *   - handoff_task_title — platform-variable-input (@state: / @var:)
 *   - handoff_user_message — markdown variable-syntax=at-ref (@state: / @var:)
 *
 * Очередь — slug WorkQueue. Список и create — фабрика `worktracker/work_queues`
 * (REST /worktracker/api/v1/work-queues, тот же `op_work_queues_*`).
 * Create на лету: пункт в dropdown combobox (`create` event).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-variable-input.js';
import './flows-base-node-editor.js';
import '@platform/lib/components/platform-markdown-editor.js';
import { asObject } from '../../_helpers/flows-resolvers.js';
import { buildPromptVariableContext } from '../../_helpers/prompt-variable-catalog.js';
import {
    buildExecutionStatePreview,
    collectStatePathsFromDataflow,
} from '@platform/lib/variables/variable-refs.js';

const SLUG_PATTERN = /^[a-z][a-z0-9_-]{0,62}$/;

/**
 * @param {string} raw
 * @returns {string}
 */
function slugifyQueueInput(raw) {
    const trimmed = raw.trim().toLowerCase();
    const dashed = trimmed
        .replace(/[\s.]+/g, '-')
        .replace(/[^a-z0-9_-]/g, '')
        .replace(/-+/g, '-')
        .replace(/^[-_]+|[-_]+$/g, '');
    return dashed;
}

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
        embedded: { type: Boolean, reflect: true },
        _showCreate: { state: true },
        _createName: { state: true },
        _createSlug: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .hitl-handoff-task-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                margin-bottom: var(--space-5);
            }
            .queue-picker-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .queue-create-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                margin-bottom: var(--space-3);
            }
            .queue-create-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            }
            .queue-create-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
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
        this.embedded = false;
        this._showCreate = false;
        this._createName = '';
        this._createSlug = '';
        this._queues = this.useResource('worktracker/work_queues');
    }

    connectedCallback() {
        super.connectedCallback();
        this._queues.load({});
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    /**
     * @returns {{ value: string, label: string }[]}
     */
    _queueOptions() {
        const items = this._queues.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-hitl-node-editor: work_queues.items must be array');
        }
        const options = [];
        for (const item of items) {
            if (item === null || typeof item !== 'object') {
                throw new Error('flows-hitl-node-editor: queue item must be object');
            }
            if (typeof item.work_queue_slug !== 'string' || item.work_queue_slug.length === 0) {
                throw new Error('flows-hitl-node-editor: work_queue_slug required');
            }
            if (typeof item.name !== 'string' || item.name.length === 0) {
                throw new Error('flows-hitl-node-editor: queue name required');
            }
            options.push({
                value: item.work_queue_slug,
                label: item.name,
            });
        }
        return options;
    }

    _onQueueSlug(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: queue slug change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-hitl-node-editor: queue slug detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-hitl-node-editor: queue slug string required');
        }
        this._emitPatch({ work_queue_slug: v });
    }

    /**
     * Combobox create row: empty query → form; typed query → create immediately.
     * @param {CustomEvent} e
     */
    _onQueueCreate(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-hitl-node-editor: create detail required');
        }
        if (typeof d.query !== 'string') {
            throw new Error('flows-hitl-node-editor: create detail.query string required');
        }
        const query = d.query.trim();
        if (query.length === 0) {
            this._showCreate = true;
            this._createName = '';
            this._createSlug = '';
            return;
        }
        const slug = slugifyQueueInput(query);
        if (!SLUG_PATTERN.test(slug)) {
            this._showCreate = true;
            this._createName = query;
            this._createSlug = slug;
            return;
        }
        void this._createQueueWith({ name: query, slug });
    }

    _toggleCreate() {
        this._showCreate = !this._showCreate;
        if (!this._showCreate) {
            this._createName = '';
            this._createSlug = '';
        }
    }

    _onCreateName(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-hitl-node-editor: create name detail.value string');
        }
        this._createName = d.value;
        if (this._createSlug.trim().length === 0) {
            this._createSlug = slugifyQueueInput(d.value);
        }
    }

    _onCreateSlug(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.value !== 'string') {
            throw new Error('flows-hitl-node-editor: create slug detail.value string');
        }
        this._createSlug = d.value;
    }

    /**
     * @param {object} controller
     * @param {string} requestedId
     * @returns {Promise<object | null>}
     */
    _waitForQueueCreated(controller, requestedId) {
        const bus = controller.bus;
        const successType = controller.resource.events.CREATED;
        const failedType = controller.resource.events.CREATE_FAILED;
        return new Promise((resolve, reject) => {
            let offSuccess = null;
            let offFailed = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') {
                    offSuccess();
                }
                if (typeof offFailed === 'function') {
                    offFailed();
                }
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const item = event.payload && typeof event.payload.item === 'object'
                    ? event.payload.item
                    : null;
                resolve(item);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) {
                    return;
                }
                cleanup();
                const message = event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'work queue create failed';
                reject(new Error(message));
            });
        });
    }

    /**
     * @param {{ name: string, slug: string }} payload
     */
    async _createQueueWith(payload) {
        const name = payload.name.trim();
        const slug = payload.slug.trim();
        if (name.length === 0 || slug.length === 0) {
            return;
        }
        if (!SLUG_PATTERN.test(slug)) {
            throw new Error(`flows-hitl-node-editor: invalid queue slug ${slug}`);
        }
        if (this._queues.createInFlight) {
            return;
        }
        const requested = this._queues.create({ name, slug });
        if (!requested || typeof requested.id !== 'string') {
            return;
        }
        const item = await this._waitForQueueCreated(this._queues, requested.id);
        if (item === null || typeof item !== 'object') {
            throw new Error('flows-hitl-node-editor: created queue item missing');
        }
        if (typeof item.work_queue_slug !== 'string' || item.work_queue_slug.length === 0) {
            throw new Error('flows-hitl-node-editor: created queue slug missing');
        }
        this._emitPatch({ work_queue_slug: item.work_queue_slug });
        this._createName = '';
        this._createSlug = '';
        this._showCreate = false;
    }

    async _createQueue() {
        await this._createQueueWith({
            name: this._createName,
            slug: this._createSlug,
        });
    }

    _variableContext() {
        const cfg = asObject(this.nodeConfig);
        return buildPromptVariableContext({
            flowVariables: this.flowVariables,
            nodeLocalVariables: cfg.local_variables,
            dataflowNode: this.dataflowNode,
            previewExecutionState: this.previewExecutionState,
        });
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
        this._emitPatch({ handoff_mode: v });
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
        this._emitPatch({ handoff_task_title: v });
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
        this._emitPatch({ handoff_user_message: v });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const slug = typeof cfg.work_queue_slug === 'string' ? cfg.work_queue_slug : '';
        const handoffMode = cfg.handoff_mode === 'takeover' ? 'takeover' : 'single_reply';
        const taskTitle = typeof cfg.handoff_task_title === 'string' ? cfg.handoff_task_title : '';
        const userMessage = typeof cfg.handoff_user_message === 'string' ? cfg.handoff_user_message : '';
        const variableContext = this._variableContext();
        const statePreview = buildExecutionStatePreview(this.previewExecutionState);
        const statePaths = collectStatePathsFromDataflow(this.dataflowNode);
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
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="queue-picker-row">
                        <platform-searchable-combobox
                            .label=${this.t('hitl_node_editor.queue_slug')}
                            .placeholder=${this.t('hitl_node_editor.queue_picker')}
                            .emptyLabel=${this.t('hitl_node_editor.queue_clear')}
                            .createLabel=${this.t('hitl_node_editor.queue_create')}
                            .createQueryLabel=${this.t('hitl_node_editor.queue_create_query')}
                            aria-label=${this.t('hitl_node_editor.queue_aria')}
                            .value=${slug}
                            .options=${this._queueOptions()}
                            @change=${this._onQueueSlug}
                            @create=${this._onQueueCreate}
                        ></platform-searchable-combobox>
                    </div>
                    ${this._showCreate ? html`
                        <section class="queue-create-card">
                            <div class="queue-create-grid">
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    .label=${this.t('hitl_node_editor.queue_create_name')}
                                    .value=${this._createName}
                                    @change=${this._onCreateName}
                                ></platform-field>
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    .label=${this.t('hitl_node_editor.queue_create_slug')}
                                    .value=${this._createSlug}
                                    @change=${this._onCreateSlug}
                                ></platform-field>
                            </div>
                            <div class="queue-create-actions">
                                <platform-button
                                    variant="ghost"
                                    density="compact"
                                    @click=${() => this._toggleCreate()}
                                >
                                    ${this.t('hitl_node_editor.queue_create_cancel')}
                                </platform-button>
                                <platform-button
                                    variant="primary"
                                    density="compact"
                                    ?disabled=${this._queues.createInFlight}
                                    @click=${() => void this._createQueue()}
                                >
                                    ${this.t('hitl_node_editor.queue_create_submit')}
                                </platform-button>
                            </div>
                        </section>
                    ` : nothing}
                    <div class="hitl-handoff-task-stack">
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('hitl_node_editor.handoff_mode')}
                            .value=${handoffMode}
                            .config=${{ values: handoffValues }}
                            @change=${this._onHandoffMode}
                        ></platform-field>
                        <platform-variable-input
                            data-field="handoff_task_title"
                            .label=${this.t('hitl_node_editor.task_title')}
                            .placeholder=${this.t('hitl_node_editor.task_title_placeholder')}
                            .value=${taskTitle}
                            .previewValues=${variableContext.values}
                            .variableCatalog=${variableContext.catalog}
                            .statePreview=${statePreview}
                            .statePaths=${statePaths}
                            @change=${this._onTaskTitle}
                        ></platform-variable-input>
                    </div>
                    <div class="field">
                        <platform-markdown-editor
                            compact
                            .value=${userMessage}
                            .enableVariables=${true}
                            variable-syntax="at-ref"
                            .variables=${variableContext.values}
                            .variableCatalog=${variableContext.catalog}
                            .statePreview=${statePreview}
                            .statePaths=${statePaths}
                            .label=${this.t('hitl_node_editor.user_message')}
                            .hint=${this.t('hitl_node_editor.user_message_hint')}
                            .minHeight=${160}
                            @change=${this._onUserMessage}
                        ></platform-markdown-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-hitl-node-editor', FlowsHitlNodeEditor);
