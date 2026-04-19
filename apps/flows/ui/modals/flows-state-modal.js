/**
 * flows-state-modal — viewer для state сессии.
 *
 * useOp('flows/session_state') по props.sessionId. Отображает state в JSON-эдиторе.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/editors/flows-code-editor.js';

export class FlowsStateModal extends PlatformLightModal {
    static modalKind = 'flows.state';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        sessionId: { type: String },
    };

    constructor() {
        super();
        this.sessionId = '';
        this._stateOp = this.useOp('flows/session_state');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('sessionId') && this.sessionId) {
            void this._stateOp.run({ session_id: this.sessionId });
        }
    }

    render() {
        const result = this._stateOp.lastResult;
        const json = result ? JSON.stringify(result, null, 2) : '';
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container state-shell">
                <style>
                    .state-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .state-header { display: flex; align-items: center; justify-content: space-between; }
                    flows-code-editor { flex: 1; min-height: 0; }
                </style>
                <div class="state-header">
                    <h2>${this.t('state_modal.modal_title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                ${this._stateOp.busy && !result
                    ? html`<glass-spinner></glass-spinner>`
                    : html`<flows-code-editor language="json" readonly .value=${json}></flows-code-editor>`}
            </div>
        `;
    }
}

customElements.define('flows-state-modal', FlowsStateModal);
registerModalKind(FlowsStateModal.modalKind, 'flows-state-modal');
