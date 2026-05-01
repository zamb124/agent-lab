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
            :host .modal.full .modal-content,
            :host .modal.fullscreen .modal-content {
                display: flex;
                flex-direction: column;
                min-height: 0;
            }
            /* Цепочка flex + fill-parent: иначе CM растягивается по документу, :host режет overflow:hidden без скролла. */
            .state-modal-editor-wrap {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                min-height: 0;
                max-height: 100%;
            }
            flows-code-editor[fill-parent] {
                min-height: 0;
            }
            .state-load-error {
                margin: 0;
                font-family: var(--font-sans);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                white-space: pre-wrap;
                word-break: break-word;
            }
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
        const err = this._stateOp.error;
        const json = result ? JSON.stringify(result, null, 2) : '';
        if (this._stateOp.busy && !result && !err) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (err) {
            return html`<p class="state-load-error">
                ${this.t('state_modal.load_failed', { detail: String(err) })}
            </p>`;
        }
        return html`
            <div class="state-modal-editor-wrap">
                <flows-code-editor
                    language="json"
                    readonly
                    fill-parent
                    .value=${json}
                ></flows-code-editor>
            </div>
        `;
    }
}

customElements.define('flows-state-modal', FlowsStateModal);
registerModalKind(FlowsStateModal.modalKind, 'flows-state-modal');
