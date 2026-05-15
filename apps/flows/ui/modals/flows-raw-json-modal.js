/**
 * flows-raw-json-modal — полноэкранный просмотр JSON (редактирование с бэка не меняет flow).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';

export class FlowsRawJsonModal extends PlatformModal {
    static modalKind = 'flows.raw_json';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        value: { type: Object },
        downloadFileName: { type: String, attribute: 'download-file-name' },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .modal.full .modal-content:has(.raw-json-body) {
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }
            .raw-json-body {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.value = null;
        this.downloadFileName = '';
    }

    _downloadJson() {
        if (this.value === null || this.value === undefined) {
            throw new Error('flows-raw-json-modal: value is required for download');
        }
        const text = JSON.stringify(this.value, null, 2);
        const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const name = typeof this.downloadFileName === 'string' && this.downloadFileName.length > 0
            ? this.downloadFileName
            : 'flow.json';
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
    }

    renderHeader() {
        return this.t('raw_json_modal.title');
    }

    renderHeaderActions() {
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('raw_json_modal.action_download')}
                aria-label=${this.t('raw_json_modal.download_aria')}
                @click=${() => this._downloadJson()}
            >
                <platform-icon name="download" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        const json = this.value === null ? '' : JSON.stringify(this.value, null, 2);
        return html`
            <div class="raw-json-body">
                <flows-code-editor
                    .fillParent=${true}
                    .showToolbar=${false}
                    language="json"
                    readonly
                    .value=${json}
                ></flows-code-editor>
            </div>
        `;
    }
}

customElements.define('flows-raw-json-modal', FlowsRawJsonModal);
registerModalKind(FlowsRawJsonModal.modalKind, 'flows-raw-json-modal');
