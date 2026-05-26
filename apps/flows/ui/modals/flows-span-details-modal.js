/**
 * flows-span-details-modal — детали выбранного span'а.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-span-attributes-viewer.js';
import { asObject } from '../_helpers/flows-resolvers.js';

function stringValue(value) {
    return typeof value === 'string' && value.length > 0 ? value : '';
}

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

    _openLogs() {
        const span = asObject(this.span);
        const props = {};
        if (typeof span.span_id === 'string' && span.span_id.length > 0) {
            props.spanId = span.span_id;
        }
        if (typeof span.trace_id === 'string' && span.trace_id.length > 0) {
            props.traceId = span.trace_id;
        }
        if (typeof span.request_id === 'string' && span.request_id.length > 0) {
            props.requestId = span.request_id;
        }
        this.openModal('flows.logs', props);
    }

    _workflowSessionId() {
        const span = asObject(this.span);
        const attrs = asObject(span.attributes);
        const directSession = stringValue(span.session_id);
        if (directSession.length > 0) {
            return directSession;
        }
        const sessionAgent = stringValue(span.session_agent);
        if (sessionAgent.length > 0) {
            return sessionAgent;
        }
        const workflowSession = stringValue(attrs['platform.workflow.session_id']);
        if (workflowSession.length > 0) {
            return workflowSession;
        }
        return stringValue(attrs['platform.session.agent']);
    }

    _openDurableHistory() {
        const sessionId = this._workflowSessionId();
        if (sessionId.length === 0) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    renderHeader() {
        const span = asObject(this.span);
        if (typeof span.operation_name === 'string' && span.operation_name.length > 0) return span.operation_name;
        if (typeof span.name === 'string' && span.name.length > 0) return span.name;
        if (typeof span.span_id === 'string' && span.span_id.length > 0) return span.span_id;
        return this.t('span_details_modal.title');
    }

    renderHeaderActions() {
        const span = asObject(this.span);
        const hasSpanId = typeof span.span_id === 'string' && span.span_id.length > 0;
        const hasWorkflowSession = this._workflowSessionId().length > 0;
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('span_details_modal.action_durable_history')}
                aria-label=${this.t('span_details_modal.action_durable_history')}
                ?disabled=${!hasWorkflowSession}
                @click=${() => this._openDurableHistory()}
            >
                <platform-icon name="trace-timeline" size="18"></platform-icon>
            </button>
            <button
                type="button"
                class="header-btn"
                title=${this.t('span_details_modal.action_logs')}
                aria-label=${this.t('span_details_modal.action_logs')}
                ?disabled=${!hasSpanId}
                @click=${() => this._openLogs()}
            >
                <platform-icon name="logs" size="18"></platform-icon>
            </button>
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
