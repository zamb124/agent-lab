/**
 * FlowEditModal - fullscreen модалка-контейнер для редактора flow
 * Использует Light DOM для совместимости с Drawflow
 * Наследуется от PlatformLightModal (DRY)
 */
import { html } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';

export class FlowEditModal extends PlatformLightModal {
    static properties = {
        ...PlatformLightModal.properties,
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
    };

    constructor() {
        super();
        this.flowId = '';
        this.skillId = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this.setAttribute('extends-platform-light-modal', '');
    }

    _onEditorClose() {
        this.close();
    }

    _onFlowSaved(e) {
        this.emit('flow-saved', e.detail);
    }

    render() {
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container">
                <flow-editor-page
                    flow-id=${this.flowId}
                    skill-id=${this.skillId || ''}
                    @editor-close=${this._onEditorClose}
                    @flow-saved=${this._onFlowSaved}
                ></flow-editor-page>
            </div>
        `;
    }
}

customElements.define('flow-edit-modal', FlowEditModal);
