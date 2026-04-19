/**
 * flows-execution-panel — панель тестового запуска flow.
 *
 * Видна только при `state.flowsEditor.executionPanelOpen`. Submit → useOp('flows/chat_send').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/glass-input.js';

export class FlowsExecutionPanel extends PlatformElement {
    static properties = {
        flowId: { type: String },
        skillId: { type: String },
        _input: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); border-top: 1px solid var(--border-subtle); }
            .row { display: flex; gap: var(--space-2); }
            .row glass-input { flex: 1; }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._input = '';
        this._editor = this.useOp('flows/editor');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
    }

    async _onSend() {
        if (!this.flowId || !this._input.trim()) return;
        const params = {
            message: {
                messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
                role: 'user',
                parts: [{ kind: 'text', text: this._input }],
                contextId: `editor_${Date.now()}`,
            },
            metadata: {},
        };
        if (this.skillId && this.skillId !== 'base') params.metadata.skill = this.skillId;
        const editorState = this._editor.state || {};
        const preview = editorState.previewExecutionState;
        const bps = preview?.breakpoints;
        if (Array.isArray(bps) && bps.length > 0) params.metadata.breakpoints = bps;
        this._editor.setAgentExecutionRunning({ running: true });
        await this._send.run({ flow_id: this.flowId, params });
        this._editor.setAgentExecutionRunning({ running: false });
        this._input = '';
    }

    render() {
        const state = this._editor.state || {};
        if (!state.executionPanelOpen) return html``;
        return html`
            <div class="row">
                <glass-input
                    .value=${this._input}
                    placeholder=${this.t('execution_panel.placeholder')}
                    @input=${(e) => { this._input = e.target.value || ''; }}
                ></glass-input>
                <platform-button variant="primary" ?disabled=${this._send.busy} @click=${this._onSend}>
                    ${state.agentExecutionRunning
                        ? this.t('execution_panel.run_running')
                        : this.t('execution_panel.run_start')}
                </platform-button>
                <platform-button @click=${() => this._editor.setExecutionPanelOpen({ open: false })}>
                    ${this.t('execution_panel.close')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);
