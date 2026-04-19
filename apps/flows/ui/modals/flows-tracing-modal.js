/**
 * flows-tracing-modal — viewer для дерева trace.
 *
 * При открытии вызывает useOp('flows/traces_by_session' | 'by_task' | 'by_trace')
 * по переданным props.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsTracingModal extends PlatformLightModal {
    static modalKind = 'flows.tracing';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        sessionId: { type: String },
        taskId: { type: String },
        traceId: { type: String },
    };

    constructor() {
        super();
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

    _renderSpan(span, depth = 0) {
        const children = Array.isArray(span.children) ? span.children : [];
        return html`
            <div style="margin-left:${depth * 16}px; padding: var(--space-1) 0; border-bottom: 1px solid var(--border-subtle)">
                <div style="font-weight: var(--font-medium)" @click=${() => this.openModal('flows.span_details', { span })}>
                    ${span.name || span.span_id}
                </div>
                <div style="font-size: var(--text-xs); color: var(--text-tertiary)">
                    ${span.duration_ms != null ? `${span.duration_ms} ms` : ''}
                    ${span.status_code ? ` · ${span.status_code}` : ''}
                </div>
            </div>
            ${children.map((c) => this._renderSpan(c, depth + 1))}
        `;
    }

    render() {
        const data = this._activeData();
        const spans = Array.isArray(data?.spans) ? data.spans : Array.isArray(data) ? data : [];
        const busy = this._bySession.busy || this._byTask.busy || this._byTrace.busy;
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container tracing-shell">
                <style>
                    .tracing-shell { padding: var(--space-4); gap: var(--space-3); height: 90vh; }
                    .tracing-header { display: flex; align-items: center; justify-content: space-between; }
                    .tracing-body { flex: 1; min-height: 0; overflow: auto; }
                </style>
                <div class="tracing-header">
                    <h2>${this.t('tracing_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                ${busy && spans.length === 0
                    ? html`<glass-spinner></glass-spinner>`
                    : spans.length === 0
                        ? html`<div>${this.t('tracing_modal.empty')}</div>`
                        : html`<div class="tracing-body">${spans.map((s) => this._renderSpan(s))}</div>`}
            </div>
        `;
    }
}

customElements.define('flows-tracing-modal', FlowsTracingModal);
registerModalKind(FlowsTracingModal.modalKind, 'flows-tracing-modal');
