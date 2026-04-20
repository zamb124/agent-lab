/**
 * flows-state-modal — viewer для state сессии.
 *
 * useOp('flows/session_state') по props.sessionId. Отображает state в JSON-эдиторе.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/editors/flows-code-editor.js';

export class FlowsStateModal extends PlatformModal {
    static modalKind = 'flows.state';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        sessionId: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            flows-code-editor { display: block; height: 100%; min-height: 50vh; }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.sessionId = '';
        this._stateOp = this.useOp('flows/session_state');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('sessionId') && this.sessionId) {
            void this._stateOp.run({ session_id: this.sessionId });
        }
    }

    renderHeader() {
        return this.t('state_modal.modal_title');
    }

    renderBody() {
        const result = this._stateOp.lastResult;
        const json = result ? JSON.stringify(result, null, 2) : '';
        if (this._stateOp.busy && !result) {
            return html`<glass-spinner></glass-spinner>`;
        }
        return html`<flows-code-editor language="json" readonly .value=${json}></flows-code-editor>`;
    }
}

customElements.define('flows-state-modal', FlowsStateModal);
registerModalKind(FlowsStateModal.modalKind, 'flows-state-modal');
