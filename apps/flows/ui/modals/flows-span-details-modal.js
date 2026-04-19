/**
 * flows-span-details-modal — детали выбранного span'а.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';

export class FlowsSpanDetailsModal extends PlatformLightModal {
    static modalKind = 'flows.span_details';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        span: { type: Object },
    };

    constructor() {
        super();
        this.span = null;
    }

    _openRaw() {
        this.openModal('flows.raw_json', { value: this.span });
    }

    render() {
        const span = this.span || {};
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container span-shell">
                <style>
                    .span-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .span-header { display: flex; align-items: center; justify-content: space-between; }
                    .span-meta { display: grid; grid-template-columns: max-content 1fr; gap: var(--space-1) var(--space-3); font-size: var(--text-sm); color: var(--text-secondary); }
                    .span-meta dt { color: var(--text-tertiary); }
                    flows-code-editor { flex: 1; min-height: 0; }
                </style>
                <div class="span-header">
                    <h2>${span.name || span.span_id || this.t('span_details_modal.title')}</h2>
                    <div>
                        <platform-button @click=${this._openRaw}>${this.t('span_details_modal.action_raw')}</platform-button>
                        <platform-button @click=${() => this.close()}>
                            <platform-icon name="close" size="14"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <dl class="span-meta">
                    <dt>span_id</dt><dd><code>${span.span_id || ''}</code></dd>
                    <dt>trace_id</dt><dd><code>${span.trace_id || ''}</code></dd>
                    <dt>duration</dt><dd>${span.duration_ms != null ? `${span.duration_ms} ms` : ''}</dd>
                    <dt>status</dt><dd>${span.status_code || ''}</dd>
                </dl>
                <flows-code-editor
                    language="json"
                    readonly
                    .value=${JSON.stringify(span.attributes || {}, null, 2)}
                ></flows-code-editor>
            </div>
        `;
    }
}

customElements.define('flows-span-details-modal', FlowsSpanDetailsModal);
registerModalKind(FlowsSpanDetailsModal.modalKind, 'flows-span-details-modal');
