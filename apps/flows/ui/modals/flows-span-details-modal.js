/**
 * flows-span-details-modal — детали выбранного span'а.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/editors/flows-code-editor.js';
import { asObject, asString, isPlainObject } from '../_helpers/flows-resolvers.js';

export class FlowsSpanDetailsModal extends PlatformModal {
    static modalKind = 'flows.span_details';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        span: { type: Object },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .span-meta {
                display: grid;
                grid-template-columns: max-content 1fr;
                gap: var(--space-1) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-3);
            }
            .span-meta dt { color: var(--text-tertiary); }
            flows-code-editor { display: block; min-height: 40vh; }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.span = null;
    }

    _openRaw() {
        this.openModal('flows.raw_json', { value: this.span });
    }

    renderHeader() {
        const span = asObject(this.span);
        if (typeof span.name === 'string' && span.name.length > 0) return span.name;
        if (typeof span.span_id === 'string' && span.span_id.length > 0) return span.span_id;
        return this.t('span_details_modal.title');
    }

    renderHeaderActions() {
        return html`
            <platform-button @click=${() => this._openRaw()}>
                ${this.t('span_details_modal.action_raw')}
            </platform-button>
        `;
    }

    renderBody() {
        const span = asObject(this.span);
        const attrs = isPlainObject(span.attributes) ? span.attributes : {};
        return html`
            <dl class="span-meta">
                <dt>span_id</dt><dd><code>${asString(span.span_id)}</code></dd>
                <dt>trace_id</dt><dd><code>${asString(span.trace_id)}</code></dd>
                <dt>duration</dt><dd>${span.duration_ms != null ? `${span.duration_ms} ms` : ''}</dd>
                <dt>status</dt><dd>${asString(span.status_code)}</dd>
            </dl>
            <flows-code-editor
                language="json"
                readonly
                .value=${JSON.stringify(attrs, null, 2)}
            ></flows-code-editor>
        `;
    }
}

customElements.define('flows-span-details-modal', FlowsSpanDetailsModal);
registerModalKind(FlowsSpanDetailsModal.modalKind, 'flows-span-details-modal');
