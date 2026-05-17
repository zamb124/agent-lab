/**
 * flows-code-modal — fullscreen viewer/editor для кода (read-only по умолчанию).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';
import { normalizeFlowCodeLanguage } from '../_helpers/flows-code-languages.js';

export class FlowsCodeModal extends PlatformModal {
    static modalKind = 'flows.code';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        title: { type: String },
        code: { type: String },
        language: { type: String },
        readonly: { type: Boolean },
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
        this.title = '';
        this.code = '';
        this.language = 'python';
        this.readonly = true;
    }

    renderHeader() {
        return this.title || this.t('code_modal.title');
    }

    renderBody() {
        return html`
            <flows-code-editor
                .language=${normalizeFlowCodeLanguage(this.language)}
                .value=${this.code}
                ?readonly=${this.readonly}
            ></flows-code-editor>
        `;
    }
}

customElements.define('flows-code-modal', FlowsCodeModal);
registerModalKind(FlowsCodeModal.modalKind, 'flows-code-modal');
