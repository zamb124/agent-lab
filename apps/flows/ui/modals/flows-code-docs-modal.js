/**
 * flows-code-docs-modal — markdown documentation viewer.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { asObject } from '../_helpers/flows-resolvers.js';

export class FlowsCodeDocsModal extends PlatformModal {
    static modalKind = 'flows.code_docs';
    static i18nNamespace = 'flows';

    static styles = [
        ...PlatformModal.styles,
        css`
            .docs-body {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                white-space: pre-wrap;
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this._docsOp = this.useOp('flows/code_documentation');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._docsOp.run({});
    }

    renderHeader() {
        return this.t('code_docs_modal.title');
    }

    renderBody() {
        const result = this._docsOp.lastResult;
        if (this._docsOp.busy && !result) {
            return html`<glass-spinner></glass-spinner>`;
        }
        let docs;
        if (typeof result === 'string') {
            docs = result;
        } else if (typeof result?.markdown === 'string') {
            docs = result.markdown;
        } else {
            docs = JSON.stringify(asObject(result), null, 2);
        }
        return html`<div class="docs-body">${docs}</div>`;
    }
}

customElements.define('flows-code-docs-modal', FlowsCodeDocsModal);
registerModalKind(FlowsCodeDocsModal.modalKind, 'flows-code-docs-modal');
