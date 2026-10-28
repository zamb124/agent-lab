/**
 * flows-span-details-modal — детали выбранного span'а.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-span-attributes-viewer.js';
import { asObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

function stringValue(value: unknown) {
    return typeof value === 'string' && value.length > 0 ? value : '';
}

export class FlowsSpanDetailsModal extends PlatformModal {
    static modalKind = 'flows.span_details';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        span: { type: Object },
    }
    declare span: Record<string, any> | null;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
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
        const props: any = {};
        if (typeof (span as any).span_id === 'string' && (span as any).span_id.length > 0) {
            props.spanId = (span as any).span_id;
        }
        if (typeof (span as any).trace_id === 'string' && (span as any).trace_id.length > 0) {
            props.traceId = (span as any).trace_id;
        }
        if (typeof (span as any).request_id === 'string' && (span as any).request_id.length > 0) {
            props.requestId = (span as any).request_id;
        }
        this.openModal('flows.logs', props);
    }

    _workflowSessionId() {
        const span = asObject(this.span);
        const attrs = asObject((span as any).attributes);
        const directSession = stringValue((span as any).session_id);
        if (directSession.length > 0) {
            return directSession;
        }
        const sessionAgent = stringValue((span as any).session_agent);
        if (sessionAgent.length > 0) {
            return sessionAgent;
        }
        const workflowSession = stringValue((attrs as any)['platform.workflow.session_id']);
        if (workflowSession.length > 0) {
            return workflowSession;
        }
        return stringValue((attrs as any)['platform.session.agent']);
    }

    _openDurableHistory() {
        const sessionId = this._workflowSessionId();
        if (sessionId.length === 0) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    override renderHeader() {
        const span = asObject(this.span);
        if (typeof (span as any).operation_name === 'string' && (span as any).operation_name.length > 0) return (span as any).operation_name;
        if (typeof (span as any).name === 'string' && (span as any).name.length > 0) return (span as any).name;
        if (typeof (span as any).span_id === 'string' && (span as any).span_id.length > 0) return (span as any).span_id;
        return this.t('span_details_modal.title');
    }

    override renderHeaderActions() {
        const span = asObject(this.span);
        const hasSpanId = typeof (span as any).span_id === 'string' && (span as any).span_id.length > 0;
        const hasWorkflowSession = this._workflowSessionId().length > 0;
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${this.t('span_details_modal.action_durable_history')}
                ?disabled=${!hasWorkflowSession}
                @click=${() => this._openDurableHistory()}
            >
                <platform-icon name="trace-timeline" size="18"></platform-icon>
            </platform-button>
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${this.t('span_details_modal.action_logs')}
                ?disabled=${!hasSpanId}
                @click=${() => this._openLogs()}
            >
                <platform-icon name="logs" size="18"></platform-icon>
            </platform-button>
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${this.t('span_details_modal.action_raw')}
                @click=${() => this._openRaw()}
            >
                <platform-icon name="trace-json" size="18"></platform-icon>
            </platform-button>
        `;
    }

    override renderBody() {
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
