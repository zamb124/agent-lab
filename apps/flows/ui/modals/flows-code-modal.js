/**
 * flows-code-modal — fullscreen viewer/editor для кода (read-only по умолчанию).
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';

export class FlowsCodeModal extends PlatformLightModal {
    static modalKind = 'flows.code';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        title: { type: String },
        code: { type: String },
        language: { type: String },
        readonly: { type: Boolean },
    };

    constructor() {
        super();
        this.title = '';
        this.code = '';
        this.language = 'python';
        this.readonly = true;
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container code-modal-shell">
                <style>
                    .code-modal-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .code-modal-shell .header {
                        display: flex; align-items: center; justify-content: space-between;
                    }
                    .code-modal-shell flows-code-editor { flex: 1; min-height: 0; }
                </style>
                <div class="header">
                    <h2>${this.title || this.t('code_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                <flows-code-editor
                    .language=${this.language}
                    .value=${this.code}
                    ?readonly=${this.readonly}
                ></flows-code-editor>
            </div>
        `;
    }
}

customElements.define('flows-code-modal', FlowsCodeModal);
registerModalKind(FlowsCodeModal.modalKind, 'flows-code-modal');
