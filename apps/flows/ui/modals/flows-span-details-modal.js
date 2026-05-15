/**
 * flows-span-details-modal — детали выбранного span'а.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-span-attributes-viewer.js';
import { asObject } from '../_helpers/flows-resolvers.js';

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
            .span-details-body {
                min-width: 0;
            }
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
        if (typeof span.operation_name === 'string' && span.operation_name.length > 0) return span.operation_name;
        if (typeof span.name === 'string' && span.name.length > 0) return span.name;
        if (typeof span.span_id === 'string' && span.span_id.length > 0) return span.span_id;
        return this.t('span_details_modal.title');
    }

    renderHeaderActions() {
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('span_details_modal.action_raw')}
                aria-label=${this.t('span_details_modal.action_raw')}
                @click=${() => this._openRaw()}
            >
                <platform-icon name="trace-json" size="18"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        const span = asObject(this.span);
        return html`
            <div class="span-details-body">
                <platform-span-attributes-viewer .span=${span}></platform-span-attributes-viewer>
            </div>
        `;
    }
}

customElements.define('flows-span-details-modal', FlowsSpanDetailsModal);
registerModalKind(FlowsSpanDetailsModal.modalKind, 'flows-span-details-modal');
