/**
 * flows-remote-flow-editor — редактор внешнего A2A flow (RemoteFlowNode).
 *
 * Поля точно по `RemoteFlowNode` (apps/flows/src/runtime/nodes.py):
 *   - url (direct URL) ИЛИ flow_id (внешний реестр)
 *   - skill_id (default 'default')
 *   - auth_headers (dict<str, str>)
 *
 * Toggle режима: direct URL ↔ by flow_id.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-node-editor.js';
import '../editors/flows-json-field-editor.js';

export class FlowsRemoteFlowEditor extends PlatformElement {
    static properties = {
        nodeId: { type: String },
        flowId: { type: String },
        skillId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
            }
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
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.skillId = '';
        this.nodeConfig = null;
        this.nodeType = 'remote_flow';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
    }

    _emitPatch(patch) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _mode() {
        const cfg = this.nodeConfig || {};
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
        this._emitPatch({ url: e.target.value });
    }

    _onFlowId(e) {
        this._emitPatch({ flow_id: e.target.value });
    }

    _onSkillId(e) {
        this._emitPatch({ skill_id: e.target.value });
    }

    _onAuthHeaders(parsed) {
        this._emitPatch({ auth_headers: parsed && typeof parsed === 'object' ? parsed : {} });
    }

    render() {
        const cfg = this.nodeConfig || {};
        const mode = this._mode();
        const url = typeof cfg.url === 'string' ? cfg.url : '';
        const flowIdValue = typeof cfg.flow_id === 'string' ? cfg.flow_id : '';
        const skillId = typeof cfg.skill_id === 'string' ? cfg.skill_id : 'default';
        const authHeaders = cfg.auth_headers && typeof cfg.auth_headers === 'object'
            ? JSON.stringify(cfg.auth_headers, null, 2) : '{}';
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .skillId=${this.skillId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${this.nodeType || 'remote_flow'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                @change=${(e) => this.emit('change', e.detail)}
                @rename-node=${(e) => this.emit('rename-node', e.detail)}
                @delete-node=${(e) => this.emit('delete-node', e.detail)}
                @duplicate-node=${(e) => this.emit('duplicate-node', e.detail)}
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
                    ${mode === 'url' ? html`
                        <div class="field">
                            <label>${this.t('remote_flow_editor.url')}</label>
                            <input type="url" placeholder="https://api.example.com/a2a"
                                .value=${url} @input=${this._onUrl} />
                        </div>
                    ` : html`
                        <div class="field">
                            <label>${this.t('remote_flow_editor.flow_id')}</label>
                            <input type="text" .value=${flowIdValue} @input=${this._onFlowId} />
                        </div>
                    `}
                    <div class="field">
                        <label>${this.t('remote_flow_editor.skill_id')}</label>
                        <input type="text" placeholder="default" .value=${skillId} @input=${this._onSkillId} />
                    </div>
                    <div class="field">
                        <label>${this.t('remote_flow_editor.auth_headers')}</label>
                        <flows-json-field-editor
                            .value=${authHeaders}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._onAuthHeaders(e.detail.parsed); }}
                        ></flows-json-field-editor>
                    </div>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-remote-flow-editor', FlowsRemoteFlowEditor);
