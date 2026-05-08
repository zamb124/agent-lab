/**
 * flows-remote-flow-editor — редактор внешнего A2A flow (RemoteFlowNode).
 *
 * Поля точно по `RemoteFlowNode` (apps/flows/src/runtime/nodes.py):
 *   - url (direct URL) ИЛИ flow_id (внешний реестр)
 *   - branch_id (default 'default')
 *   - headers (dict<str, str>, @state: / @var: в строках)
 *
 * Toggle режима: direct URL ↔ by flow_id.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import { asObject } from '../../_helpers/flows-resolvers.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';

export class FlowsRemoteFlowEditor extends PlatformElement {
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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .toggle button {
                padding: 4px 12px;
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .toggle button[active] { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent-subtle); }
            .row { display: flex; gap: var(--space-2); margin-bottom: var(--space-2); }
            .remote-flow-endpoint-stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                margin-bottom: var(--space-5);
            }
            .field-auth-headers {
                margin-bottom: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'remote_flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.expanded = false;
        this.embedded = false;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _mode() {
        const cfg = asObject(this.nodeConfig);
        if (typeof cfg.url === 'string' && cfg.url.length > 0) return 'url';
        if (typeof cfg.flow_id === 'string' && cfg.flow_id.length > 0) return 'flow_id';
        return 'url';
    }

    _setMode(mode) {
        if (mode === 'url') {
            this._emitPatch({ url: '', flow_id: null });
        } else {
            this._emitPatch({ flow_id: '', url: null });
        }
    }

    _onUrl(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-remote-flow-editor: url change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-remote-flow-editor: url detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-remote-flow-editor: url string required');
        }
        this._emitPatch({ url: v });
    }

    _onFlowId(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-remote-flow-editor: flow_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-remote-flow-editor: flow_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-remote-flow-editor: flow_id string required');
        }
        this._emitPatch({ flow_id: v });
    }

    _onBranchId(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-remote-flow-editor: branch_id change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-remote-flow-editor: branch_id detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-remote-flow-editor: branch_id string required');
        }
        this._emitPatch({ branch_id: v });
    }

    _onHeaders(parsed) {
        this._emitPatch({ headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    render() {
        const cfg = asObject(this.nodeConfig);
        const mode = this._mode();
        const url = typeof cfg.url === 'string' ? cfg.url : '';
        const flowIdValue = typeof cfg.flow_id === 'string' ? cfg.flow_id : '';
        const branchId = typeof cfg.branch_id === 'string' ? cfg.branch_id : 'default';
        const headersJson = cfg.headers && typeof cfg.headers === 'object'
            ? JSON.stringify(cfg.headers, null, 2) : '{}';
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'remote_flow'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                ?expanded=${this.expanded}
                ?embedded=${this.embedded}
            >
                <div slot="settings">
                    <div class="row toggle">
                        <button ?active=${mode === 'url'} @click=${() => this._setMode('url')}>
                            ${this.t('remote_flow_editor.mode_url')}
                        </button>
                        <button ?active=${mode === 'flow_id'} @click=${() => this._setMode('flow_id')}>
                            ${this.t('remote_flow_editor.mode_id')}
                        </button>
                    </div>
                    <div class="remote-flow-endpoint-stack">
                        ${mode === 'url'
                            ? html`
                                <platform-field
                                    mode="edit"
                                    type="string"
                                    input-type="url"
                                    .label=${this.t('remote_flow_editor.url')}
                                    .placeholder=${'https://api.example.com/a2a'}
                                    .value=${url}
                                    @change=${this._onUrl}
                                ></platform-field>
                            `
                            : html`
                                <platform-field
                                    mode="edit"
                                    type="string"
                                    .label=${this.t('remote_flow_editor.flow_id')}
                                    .value=${flowIdValue}
                                    @change=${this._onFlowId}
                                ></platform-field>
                            `}
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('remote_flow_editor.branch_id')}
                            .placeholder=${'default'}
                            .value=${branchId}
                            @change=${this._onBranchId}
                        ></platform-field>
                    </div>
                    <div class="field-auth-headers">
                        <flows-json-field-editor
                            .value=${headersJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onHeaders(e.detail.parsed); }}
                        >
                            <span slot="toolbar-start">${this.t('remote_flow_editor.headers')}</span>
                        </flows-json-field-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-remote-flow-editor', FlowsRemoteFlowEditor);
