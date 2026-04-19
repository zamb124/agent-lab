/**
 * flows-raw-json-modal — fullscreen JSON viewer.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';

export class FlowsRawJsonModal extends PlatformLightModal {
    static modalKind = 'flows.raw_json';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        value: { type: Object },
    };

    constructor() {
        super();
        this.value = null;
    }

    render() {
        const json = this.value === null ? '' : JSON.stringify(this.value, null, 2);
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container raw-shell">
                <style>
                    .raw-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .raw-header { display: flex; align-items: center; justify-content: space-between; }
                    flows-code-editor { flex: 1; min-height: 0; }
                </style>
                <div class="raw-header">
                    <h2>${this.t('raw_json_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                <flows-code-editor language="json" readonly .value=${json}></flows-code-editor>
            </div>
        `;
    }
}

customElements.define('flows-raw-json-modal', FlowsRawJsonModal);
registerModalKind(FlowsRawJsonModal.modalKind, 'flows-raw-json-modal');
