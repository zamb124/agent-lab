/**
 * flows-test-panel — мини-плейграунд для исполнения ноды.
 *
 * State JSON + кнопка Run → useOp('flows/code_execute').
 * Результат рендерится через `<flows-code-editor language='json' readonly>`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-code-editor.js';
import './flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsTestPanel extends PlatformElement {
    static properties = {
        nodeType: { type: String },
        nodeConfig: { type: Object },
        flowId: { type: String },
        skillId: { type: String },
        _stateJson: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .row { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
            .label { font-size: var(--text-sm); color: var(--text-secondary); }
            .result { margin-top: var(--space-2); }
            .error { color: var(--error); font-size: var(--text-xs); }
        `,
    ];

    constructor() {
        super();
        this.nodeType = 'code';
        this.nodeConfig = {};
        this.flowId = '';
        this.skillId = '';
        this._stateJson = '{}';
        this._executeOp = this.useOp('flows/code_execute');
    }

    _onStateChange(e) {
        this._stateJson = e.detail?.value || '{}';
    }

    async _run() {
        let state;
        try {
            state = JSON.parse(this._stateJson);
        } catch {
            return;
        }
        await this._executeOp.run({
            node_type: this.nodeType,
            node_config: this.nodeConfig,
            state,
            flow_id: this.flowId,
            skill_id: this.skillId,
        });
    }

    render() {
        const result = this._executeOp.lastResult;
        const error = this._executeOp.error;
        return html`
            <div class="label">${this.t('test_panel.input_state')}</div>
            <flows-json-field-editor
                .value=${this._stateJson}
                @change=${this._onStateChange}
            ></flows-json-field-editor>
            <div class="row">
                <glass-button variant="primary" ?disabled=${this._executeOp.busy} @click=${this._run}>
                    ${this.t('test_panel.action_run')}
                </glass-button>
                ${this._executeOp.busy ? html`<glass-spinner></glass-spinner>` : ''}
            </div>
            ${error
                ? html`<div class="error">${error.message || error}</div>`
                : ''}
            ${result
                ? html`
                    <div class="result">
                        <div class="label">${this.t('test_panel.result')}</div>
                        <flows-code-editor
                            language="json"
                            readonly
                            .value=${JSON.stringify(result, null, 2)}
                        ></flows-code-editor>
                    </div>
                `
                : ''}
        `;
    }
}

customElements.define('flows-test-panel', FlowsTestPanel);
