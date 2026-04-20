/**
 * flows-mocks-modal — редактор mock-ответов LLM для тестового запуска flow.
 *
 * Хранит/читает строки моков через slice `flows/execution_ui`. Конкретный
 * UI редактирования вынесен в `<flows-llm-mocks-editor>`.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '../components/editors/flows-llm-mocks-editor.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';

export class FlowsMocksModal extends PlatformModal {
    static modalKind = 'flows.mocks';
    static i18nNamespace = 'flows';

    static styles = [
        ...PlatformModal.styles,
        css`
            flows-llm-mocks-editor { display: block; }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this._ui = this.useSlice('flows/execution_ui');
    }

    _onChange(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const mocks = Array.isArray(detail.mocks) ? detail.mocks : [];
        this._ui.setMocks({ mocks });
    }

    renderHeader() {
        return this.t('mocks_modal.title');
    }

    renderBody() {
        const ui = this._ui.value;
        return html`
            <flows-llm-mocks-editor
                .mocks=${ui.mockResponses}
                @change=${this._onChange}
            ></flows-llm-mocks-editor>
        `;
    }
}

customElements.define('flows-mocks-modal', FlowsMocksModal);
registerModalKind(FlowsMocksModal.modalKind, 'flows-mocks-modal');
