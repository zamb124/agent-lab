/**
 * flows-raw-json-modal — fullscreen JSON viewer.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';

export class FlowsRawJsonModal extends PlatformModal {
    static modalKind = 'flows.raw_json';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        value: { type: Object },
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
        this.value = null;
    }

    renderHeader() {
        return this.t('raw_json_modal.title');
    }

    renderBody() {
        const json = this.value === null ? '' : JSON.stringify(this.value, null, 2);
        return html`<flows-code-editor language="json" readonly .value=${json}></flows-code-editor>`;
    }
}

customElements.define('flows-raw-json-modal', FlowsRawJsonModal);
registerModalKind(FlowsRawJsonModal.modalKind, 'flows-raw-json-modal');
