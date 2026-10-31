/**
 * flows-tracing-modal — viewer для дерева trace.
 *
 * При открытии вызывает useOp('flows/traces_by_session' | 'by_task' | 'by_trace')
 * по переданным props.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-trace-viewer.js';
import '@platform/lib/components/platform-empty-state.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

export class FlowsTracingModal extends PlatformModal {
    static modalKind = 'flows.tracing';
    static i18nNamespace = 'flows';
    static pollIntervalMs = 500;
    static pollMaxAttempts = 6;

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        taskId: { type: String },
        traceId: { type: String },
        _pollAttempt: { type: Number, state: true },
        _pollExhausted: { type: Boolean, state: true },
    }
    declare sessionId: string;
    declare taskId: string;
    declare traceId: string;
    declare _pollAttempt: number;
    declare _pollExhausted: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .tracing-empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); }
            .tracing-loading {
                min-height: 240px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];
    private _bySession: OpController;
    private _byTask: OpController;
    private _byTrace: OpController;
    private _pollTimer: any;

    constructor() {
        super();
        this.size = 'full';
        this.sessionId = '';
        this.taskId = '';
        this.traceId = '';
        this._bySession = this.useOp('flows/traces_by_session');
        this._byTask = this.useOp('flows/traces_by_task');
        this._byTrace = this.useOp('flows/traces_by_trace');
        this._pollAttempt = 0;
        this._pollExhausted = false;
        this._pollTimer = null;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('open') && !this.open) {
            this._clearPollTimer();
            return;
        }
        if (
            changed.has('open')
            || changed.has('sessionId')
            || changed.has('taskId')
            || changed.has('traceId')
        ) {
            if (this.open) {
                this._restartPolling();
            }
            return;
        }
        this._syncPollingAfterRender();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this._clearPollTimer();
    }

    _clearPollTimer() {
        if (this._pollTimer !== null) {
            clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }
    }

    _spansFromData(data: any) {
        if (Array.isArray(data)) {
            return data;
        }
        if (data !== null && typeof data === 'object' && Array.isArray(data.spans)) {
            return data.spans;
        }
        return [];
    }

    _activeData() {
        const traceId = typeof this.traceId === 'string' ? this.traceId : '';
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        let candidates: any[] = [];
        if (traceId.length > 0) {
            candidates = [this._byTrace.lastResult];
        } else if (taskId.length > 0 && sessionId.length > 0) {
            candidates = [this._byTask.lastResult, this._bySession.lastResult];
        } else if (taskId.length > 0) {
            candidates = [this._byTask.lastResult];
        } else if (sessionId.length > 0) {
            candidates = [this._bySession.lastResult];
        } else {
            candidates = [];
        }
        for (const data of candidates) {
            if (this._spansFromData(data).length > 0) {
                return data;
            }
        }
        for (const data of candidates) {
            if (data !== null && data !== undefined) {
                return data;
            }
        }
        return null;
    }

    _activeSpans() {
        return this._spansFromData(this._activeData());
    }

    _hasLoadTarget() {
        const traceId = typeof this.traceId === 'string' ? this.traceId : '';
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        return traceId.length > 0 || taskId.length > 0 || sessionId.length > 0;
    }

    _busy() {
        return this._bySession.busy || this._byTask.busy || this._byTrace.busy;
    }

    _loadOnce() {
        const traceId = typeof this.traceId === 'string' ? this.traceId : '';
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        const runs = [];
        if (traceId.length > 0) {
            runs.push(this._byTrace.run({ trace_id: traceId }));
            return runs;
        }
        if (taskId.length > 0) {
            runs.push(this._byTask.run({ task_id: taskId }));
        }
        if (sessionId.length > 0) {
            runs.push(this._bySession.run({ session_id: sessionId }));
        }
        return runs;
    }

    _restartPolling() {
        this._clearPollTimer();
        this._pollAttempt = 0;
        this._pollExhausted = false;
        this._loadForPoll();
        this.requestUpdate();
    }

    _loadForPoll() {
        this._clearPollTimer();
        if (!this.open || !this._hasLoadTarget()) {
            return;
        }
        if (this._activeSpans().length > 0) {
            return;
        }
        if (this._busy()) {
            this._scheduleNextPoll();
            return;
        }
        if (this._pollAttempt >= FlowsTracingModal.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollAttempt += 1;
        this.requestUpdate();
        const runs = this._loadOnce();
        if (runs.length === 0) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        Promise.all(runs)
            .catch(() => null)
            .finally(() => this._syncPollingAfterRender());
    }

    _scheduleNextPoll() {
        if (!this.open || this._pollTimer !== null) {
            return;
        }
        if (!this._hasLoadTarget() || this._pollExhausted || this._activeSpans().length > 0) {
            return;
        }
        if (this._pollAttempt >= FlowsTracingModal.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollTimer = setTimeout(() => {
            this._pollTimer = null;
            this._loadForPoll();
        }, FlowsTracingModal.pollIntervalMs);
        this.requestUpdate();
    }

    _syncPollingAfterRender() {
        if (!this.open) {
            this._clearPollTimer();
            return;
        }
        if (this._activeSpans().length > 0) {
            this._clearPollTimer();
            return;
        }
        if (this._busy()) {
            return;
        }
        this._scheduleNextPoll();
    }

    _waitingForTrace(spans: any, busy: any) {
        if (spans.length > 0 || !this._hasLoadTarget()) {
            return false;
        }
        if (busy) {
            return true;
        }
        return !this._pollExhausted && this._pollAttempt < FlowsTracingModal.pollMaxAttempts;
    }

    /** @param {CustomEvent<{ span?: unknown }>} e */
    _onTraceSpanSelect(e: CustomEvent) {
        const d = e.detail;
        if (d == null || typeof d !== 'object' || !('span' in d)) {
            throw new Error('flows-tracing-modal: trace-span-select requires detail.span');
        }
        this.openModal('flows.span_details', { span: d.span });
    }

    override renderHeader() {
        return this.t('tracing_modal.title');
    }

    override renderBody() {
        const spans = this._activeSpans();
        const busy = this._busy();
        if (this._waitingForTrace(spans, busy)) {
            return html`
                <div class="tracing-loading">
                    <platform-spinner></platform-spinner>
                    <div>${this.t('tracing_modal.waiting')}</div>
                </div>
            `;
        }
        if (spans.length === 0) {
            return html`<platform-empty-state icon="trace-timeline" title=${this.t('tracing_modal.empty')}></platform-empty-state>`;
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
