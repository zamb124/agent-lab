/**
 * flows-code-docs-modal — markdown documentation viewer.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsCodeDocsModal extends PlatformLightModal {
    static modalKind = 'flows.code_docs';
    static i18nNamespace = 'flows';

    constructor() {
        super();
        this._docsOp = this.useOp('flows/code_documentation');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._docsOp.run({});
    }

    render() {
        const result = this._docsOp.lastResult;
        const docs = typeof result === 'string'
            ? result
            : typeof result?.markdown === 'string'
                ? result.markdown
                : JSON.stringify(result || {}, null, 2);
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container docs-shell">
                <style>
                    .docs-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .docs-header { display: flex; align-items: center; justify-content: space-between; }
                    .docs-body { flex: 1; min-height: 0; overflow: auto; padding: var(--space-3);
                        background: var(--glass-solid-subtle); border-radius: var(--radius-md);
                        white-space: pre-wrap; font-family: var(--font-mono); font-size: var(--text-sm);
                        color: var(--text-primary); }
                </style>
                <div class="docs-header">
                    <h2>${this.t('code_docs_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                ${this._docsOp.busy && !result
                    ? html`<glass-spinner></glass-spinner>`
                    : html`<div class="docs-body">${docs}</div>`}
            </div>
        `;
    }
}

customElements.define('flows-code-docs-modal', FlowsCodeDocsModal);
registerModalKind(FlowsCodeDocsModal.modalKind, 'flows-code-docs-modal');
