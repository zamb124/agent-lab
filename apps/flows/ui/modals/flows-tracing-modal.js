/**
 * flows-tracing-modal — viewer для дерева trace.
 *
 * При открытии вызывает useOp('flows/traces_by_session' | 'by_task' | 'by_trace')
 * по переданным props.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-trace-viewer.js';

export class FlowsTracingModal extends PlatformModal {
    static modalKind = 'flows.tracing';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        taskId: { type: String },
        traceId: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .tracing-empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this.sessionId = '';
        this.taskId = '';
        this.traceId = '';
        this._bySession = this.useOp('flows/traces_by_session');
        this._byTask = this.useOp('flows/traces_by_task');
        this._byTrace = this.useOp('flows/traces_by_trace');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('sessionId') && this.sessionId) {
            void this._bySession.run({ session_id: this.sessionId });
        }
        if (changed.has('taskId') && this.taskId) {
            void this._byTask.run({ task_id: this.taskId });
        }
        if (changed.has('traceId') && this.traceId) {
            void this._byTrace.run({ trace_id: this.traceId });
        }
    }

    _activeData() {
        return this._bySession.lastResult || this._byTask.lastResult || this._byTrace.lastResult;
    }

    /** @param {CustomEvent<{ span?: unknown }>} e */
    _onTraceSpanSelect(e) {
        const d = e.detail;
        if (d == null || typeof d !== 'object' || !('span' in d)) {
            throw new Error('flows-tracing-modal: trace-span-select requires detail.span');
        }
        this.openModal('flows.span_details', { span: d.span });
    }

    renderHeader() {
        return this.t('tracing_modal.title');
    }

    renderBody() {
        const data = this._activeData();
        const spans = Array.isArray(data?.spans) ? data.spans : Array.isArray(data) ? data : [];
        const busy = this._bySession.busy || this._byTask.busy || this._byTrace.busy;
        if (busy && spans.length === 0) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (spans.length === 0) {
            return html`<div class="tracing-empty">${this.t('tracing_modal.empty')}</div>`;
        }
        return html`
            <platform-trace-viewer
                .roots=${spans}
                @trace-span-select=${this._onTraceSpanSelect}
            ></platform-trace-viewer>
        `;
    }
}

customElements.define('flows-tracing-modal', FlowsTracingModal);
registerModalKind(FlowsTracingModal.modalKind, 'flows-tracing-modal');
