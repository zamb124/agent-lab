/**
 * flows-logs-modal — встроенный просмотр логов flows из Loki.
 *
 * Открывается по sessionId, traceId, requestId, spanId или userId.
 * Для taskId trace_id резолвится только через Tempo endpoints traces/task и
 * traces/session, после чего вкладка trace_id становится активной.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-log-viewer.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function arrayField(value: unknown, field: string): unknown[] {
    if (!isPlainRecord(value)) return [];
    const list = value[field];
    return Array.isArray(list) ? list : [];
}

/**
 * Первый корень — как раньше для ответа traces/task.
 * @param {unknown[]} roots
 * @returns {string}
 */
function _traceIdFromFirstRoot(roots: any) {
    if (!Array.isArray(roots) || roots.length === 0) {
        return '';
    }
    const first = roots[0];
    if (first === null || typeof first !== 'object') {
        return '';
    }
    const tid = first.trace_id;
    if (typeof tid === 'string' && tid.length > 0) {
        return tid;
    }
    return '';
}

/**
 * Несколько корней у ответа traces/session: trace_id корня с максимальным start_time.
 * @param {unknown[]} roots
 * @returns {string}
 */
function _traceIdFromLatestRoot(roots: any) {
    if (!Array.isArray(roots) || roots.length === 0) {
        return '';
    }
    let best = '';
    let bestMs = Number.NEGATIVE_INFINITY;
    for (const r of roots) {
        if (r === null || typeof r !== 'object') {
            continue;
        }
        const tid = r.trace_id;
        if (typeof tid !== 'string' || tid.length === 0) {
            continue;
        }
        const st = r.start_time;
        let ms = Number.NEGATIVE_INFINITY;
        if (typeof st === 'string' && st.length > 0) {
            const parsed = Date.parse(st);
            if (!Number.isNaN(parsed)) {
                ms = parsed;
            }
        }
        if (ms >= bestMs) {
            bestMs = ms;
            best = tid;
        }
    }
    return best;
}

/**
 * trace_id у любого узла дерева spans с тем же task_id, что A2A task (атрибут на span).
 * @param {unknown[]} roots
 * @param {string} taskId
 * @returns {string}
 */
function _traceIdFromTreeMatchingTask(roots: any, taskId: any) {
    if (!Array.isArray(roots) || roots.length === 0) {
        return '';
    }
    if (typeof taskId !== 'string' || taskId.length === 0) {
        return '';
    }
    const stack = [...roots];
    while (stack.length > 0) {
        const n = stack.pop();
        if (n === null || typeof n !== 'object') {
            continue;
        }
        if (n.task_id === taskId) {
            const tr = n.trace_id;
            if (typeof tr === 'string' && tr.length > 0) {
                return tr;
            }
        }
        const ch = n.children;
        if (Array.isArray(ch)) {
            for (let i = 0; i < ch.length; i += 1) {
                stack.push(ch[i]);
            }
        }
    }
    return '';
}

/**
 * trace_id для вкладки логов по сессии: приоритет совпадения task_id в дереве, иначе
 * последний по времени корень.
 * @param {unknown[]} roots
 * @param {string} preferredTaskId
 * @returns {string}
 */
function _traceIdFromSessionTreeForLogs(roots: any, preferredTaskId: any) {
    const byTask = _traceIdFromTreeMatchingTask(roots, preferredTaskId);
    if (byTask.length > 0) {
        return byTask;
    }
    return _traceIdFromLatestRoot(roots);
}

export class FlowsLogsModal extends PlatformModal {
    static modalKind = 'flows.logs';
    static i18nNamespace = 'flows';
    static pollIntervalMs = 500;
    static pollMaxAttempts = 6;

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        traceId: { type: String },
        taskId: { type: String },
        requestId: { type: String },
        spanId: { type: String },
        userId: { type: String },
        flowId: { type: String },
        nodeId: { type: String },
        contextId: { type: String },
        _mode: { type: String, state: true },
        _pollAttempt: { type: Number, state: true },
        _pollExhausted: { type: Boolean, state: true },
    }
    declare sessionId: string;
    declare traceId: string;
    declare taskId: string;
    declare requestId: string;
    declare spanId: string;
    declare userId: string;
    declare flowId: string;
    declare nodeId: string;
    declare contextId: string;
    declare _mode: string;
    declare _pollAttempt: number;
    declare _pollExhausted: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            :host {
                --modal-width: min(1100px, calc(100vw - 24px));
            }
            .logs-modal-stack {
                display: flex;
                flex-direction: column;
                min-height: min(400px, calc(72vh - 160px));
            }
            .logs-main {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
            }
            .logs-loading {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                min-height: 240px;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .logs-toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-primary);
                flex-wrap: wrap;
            }
            .mode-segment {
                flex: 1 1 auto;
                min-width: 0;
            }
            .count-badge {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-solid-secondary);
                padding: 2px 8px;
                border-radius: var(--radius-full);
                white-space: nowrap;
            }
        `,
    ];
    private _byTrace: OpController;
    private _bySession: OpController;
    private _byRequest: OpController;
    private _bySpan: OpController;
    private _byUser: OpController;
    private _byTaskTraces: OpController;
    private _bySessionTraces: OpController;
    private _guestLogs: OpController;
    private _lastLogsLoadKey: string;
    private _pollTimer: any;

    constructor() {
        super();
        this.size = 'xl';
        this.sessionId = '';
        this.traceId = '';
        this.taskId = '';
        this.requestId = '';
        this.spanId = '';
        this.userId = '';
        this.flowId = '';
        this.nodeId = '';
        this.contextId = '';
        this._mode = 'session';
        this._lastLogsLoadKey = '';
        this._pollAttempt = 0;
        this._pollExhausted = false;
        this._pollTimer = null;
        this._byTrace = this.useOp('flows/logs_by_trace');
        this._bySession = this.useOp('flows/logs_by_session');
        this._byRequest = this.useOp('flows/logs_by_request');
        this._bySpan = this.useOp('flows/logs_by_span');
        this._byUser = this.useOp('flows/logs_by_user');
        this._byTaskTraces = this.useOp('flows/traces_by_task');
        this._bySessionTraces = this.useOp('flows/traces_by_session');
        this._guestLogs = this.useOp('flows/code_agent_logs');
    }

    _traceIdFromTaskOp() {
        const data = this._byTaskTraces.lastResult;
        if (!isPlainRecord(data)) {
            return '';
        }
        const roots = arrayField(data, 'spans');
        const tid = typeof this.taskId === 'string' && this.taskId.length > 0 ? this.taskId : '';
        if (tid.length > 0) {
            const matched = _traceIdFromTreeMatchingTask(roots, tid);
            if (matched.length > 0) {
                return matched;
            }
        }
        return _traceIdFromFirstRoot(roots);
    }

    _traceIdFromSessionOp() {
        const data = this._bySessionTraces.lastResult;
        if (!isPlainRecord(data)) {
            return '';
        }
        const roots = arrayField(data, 'spans');
        const preferredTaskId =
            typeof this.taskId === 'string' && this.taskId.length > 0 ? this.taskId : '';
        return _traceIdFromSessionTreeForLogs(roots, preferredTaskId);
    }

    /**
     * Итоговый trace_id для вкладки «По trace_id» и загрузки Loki by-trace.
     */
    _effectiveTraceId() {
        if (typeof this.traceId === 'string' && this.traceId.length > 0) {
            return this.traceId;
        }
        const fromTask = this._traceIdFromTaskOp();
        if (fromTask.length > 0) {
            return fromTask;
        }
        const fromSessionTempo = this._traceIdFromSessionOp();
        if (fromSessionTempo.length > 0) {
            return fromSessionTempo;
        }
        return '';
    }

    _isGuestRuntimeMode() {
        return typeof this.flowId === 'string' && this.flowId.length > 0
            && typeof this.nodeId === 'string' && this.nodeId.length > 0;
    }

    _logsLoadKey() {
        if (this._isGuestRuntimeMode()) {
            return `guest|${this.flowId}|${this.nodeId}`;
        }
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        const traceId = typeof this.traceId === 'string' ? this.traceId : '';
        const requestId = typeof this.requestId === 'string' ? this.requestId : '';
        const spanId = typeof this.spanId === 'string' ? this.spanId : '';
        const userId = typeof this.userId === 'string' ? this.userId : '';
        if (this._mode === 'trace') {
            return `trace|${this._effectiveTraceId()}|task|${taskId}|session|${sessionId}|prop|${traceId}`;
        }
        if (this._mode === 'request') {
            return `request|${requestId}`;
        }
        if (this._mode === 'span') {
            return `span|${spanId}`;
        }
        if (this._mode === 'user') {
            return `user|${userId}`;
        }
        if (sessionId.length > 0) {
            return `session|${sessionId}|task|${taskId}`;
        }
        return 'noop|';
    }

    _traceResolutionBusy() {
        if (typeof this.traceId === 'string' && this.traceId.length > 0) {
            return false;
        }
        if (this._effectiveTraceId().length > 0) {
            return false;
        }
        const hasSession = typeof this.sessionId === 'string' && this.sessionId.length > 0;
        const hasTask = typeof this.taskId === 'string' && this.taskId.length > 0;
        if (!hasSession && !hasTask) {
            return false;
        }
        return this._byTaskTraces.busy || this._bySessionTraces.busy;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);

        if (changed.has('open') && !this.open) {
            this._clearPollTimer();
            return;
        }

        if (changed.has('open') && this.open) {
            this._lastLogsLoadKey = '';
        }

        if (this._isGuestRuntimeMode()) {
            this._mode = 'guest_runtime';
        } else if (
            changed.has('sessionId')
            || changed.has('traceId')
            || changed.has('requestId')
            || changed.has('spanId')
            || changed.has('userId')
        ) {
            if (this.spanId) {
                this._mode = 'span';
            } else if (this.requestId) {
                this._mode = 'request';
            } else if (this.userId) {
                this._mode = 'user';
            } else if (this.traceId && !this.sessionId) {
                this._mode = 'trace';
            } else {
                this._mode = 'session';
            }
        }

        const key = this._logsLoadKey();
        if (this._lastLogsLoadKey !== key) {
            this._lastLogsLoadKey = key;
            this._restartPolling();
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

    _load() {
        const runs = [];
        if (this._mode === 'guest_runtime') {
            const flowId = typeof this.flowId === 'string' ? this.flowId : '';
            const nodeId = typeof this.nodeId === 'string' ? this.nodeId : '';
            if (flowId.length === 0 || nodeId.length === 0) {
                throw new Error('flows-logs-modal: flowId and nodeId required for guest_runtime');
            }
            const payload: any = { flow_id: flowId, node_id: nodeId };
            const taskId = typeof this.taskId === 'string' ? this.taskId : '';
            if (taskId.length > 0) {
                payload.task_id = taskId;
            }
            const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
            if (sessionId.length > 0) {
                payload.session_id = sessionId;
            }
            const contextId = typeof this.contextId === 'string' ? this.contextId : '';
            if (contextId.length > 0) {
                payload.context_id = contextId;
            }
            runs.push(this._guestLogs.run(payload));
            return runs;
        }
        if (this._mode === 'trace') {
            const tid = this._effectiveTraceId();
            if (tid.length > 0) {
                runs.push(this._byTrace.run({ trace_id: tid }));
            }
            return runs;
        }
        if (this._mode === 'request') {
            const requestId = typeof this.requestId === 'string' ? this.requestId : '';
            if (requestId.length > 0) {
                runs.push(this._byRequest.run({ request_id: requestId }));
            }
            return runs;
        }
        if (this._mode === 'span') {
            const spanId = typeof this.spanId === 'string' ? this.spanId : '';
            if (spanId.length > 0) {
                runs.push(this._bySpan.run({ span_id: spanId }));
            }
            return runs;
        }
        if (this._mode === 'user') {
            const userId = typeof this.userId === 'string' ? this.userId : '';
            if (userId.length > 0) {
                runs.push(this._byUser.run({ user_id: userId }));
            }
            return runs;
        }
        if (typeof this.sessionId === 'string' && this.sessionId.length > 0) {
            runs.push(this._bySession.run({ session_id: this.sessionId }));
        }
        return runs;
    }

    _loadTraceResolutionForPoll() {
        if (typeof this.traceId === 'string' && this.traceId.length > 0) {
            return [];
        }
        if (this._effectiveTraceId().length > 0) {
            return [];
        }
        const runs = [];
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        if (taskId.length > 0) {
            runs.push(this._byTaskTraces.run({ task_id: taskId }));
        }
        if (sessionId.length > 0) {
            runs.push(this._bySessionTraces.run({ session_id: sessionId }));
        }
        return runs;
    }

    _setMode(mode: string) {
        if (this._isGuestRuntimeMode()) {
            this._mode = 'guest_runtime';
            return;
        }
        if (!['trace', 'session', 'request', 'span', 'user'].includes(mode)) {
            throw new Error('flows-logs-modal: invalid mode');
        }
        if (this._mode === mode) {
            return;
        }
        this._mode = mode;
    }

    _modeSegmentItems({
        hasSession,
        hasTraceResolver,
        hasRequest,
        hasSpan,
        hasUser,
        resolving,
        traceTitle,
    }: any) {
        return [
            {
                value: 'session',
                label: this.t('logs_modal.tab_session'),
                disabled: !hasSession,
            },
            {
                value: 'trace',
                label: this.t('logs_modal.tab_trace'),
                disabled: !hasTraceResolver,
                title: traceTitle,
                indicator: resolving,
            },
            {
                value: 'request',
                label: this.t('logs_modal.tab_request'),
                disabled: !hasRequest,
            },
            {
                value: 'span',
                label: this.t('logs_modal.tab_span'),
                disabled: !hasSpan,
            },
            {
                value: 'user',
                label: this.t('logs_modal.tab_user'),
                disabled: !hasUser,
            },
        ];
    }

    _mapGuestLogEntries(data: any) {
        if (data === null || typeof data !== 'object') {
            throw new Error('flows-logs-modal: guest logs payload required');
        }
        const items = data.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-logs-modal: guest logs items required');
        }
        return items.map((item) => {
            if (item === null || typeof item !== 'object') {
                throw new Error('flows-logs-modal: guest log line must be an object');
            }
            const event = typeof item.event === 'string' && item.event.length > 0 ? item.event : '';
            if (event.length === 0) {
                throw new Error('flows-logs-modal: guest log event required');
            }
            const line = typeof item.line === 'string' ? item.line : '';
            const ts = item.ts;
            const timestamp = typeof ts === 'string' ? ts : '';
            const failed = event.includes('fail') || event.includes('error');
            return {
                timestamp,
                level: failed ? 'error' : 'info',
                message: line.length > 0 ? line : event,
                service: 'guest_runtime',
                raw: item,
            };
        });
    }

    _activeData() {
        if (this._mode === 'guest_runtime') {
            return this._guestLogs.lastResult;
        }
        if (this._mode === 'trace') {
            return this._byTrace.lastResult;
        }
        if (this._mode === 'request') {
            return this._byRequest.lastResult;
        }
        if (this._mode === 'span') {
            return this._bySpan.lastResult;
        }
        if (this._mode === 'user') {
            return this._byUser.lastResult;
        }
        return this._bySession.lastResult;
    }

    _activeEntries() {
        if (this._mode === 'guest_runtime') {
            const data = this._guestLogs.lastResult;
            if (data === null) {
                return [];
            }
            return this._mapGuestLogEntries(data);
        }
        const data = this._activeData();
        if (isPlainRecord(data)) {
            const entries = data.entries;
            if (Array.isArray(entries)) return entries;
        }
        return [];
    }

    _hasLoadTarget() {
        if (this._mode === 'guest_runtime') {
            return this._isGuestRuntimeMode();
        }
        if (this._mode === 'trace') {
            return this._effectiveTraceId().length > 0
                || (typeof this.taskId === 'string' && this.taskId.length > 0)
                || (typeof this.sessionId === 'string' && this.sessionId.length > 0);
        }
        if (this._mode === 'request') {
            return typeof this.requestId === 'string' && this.requestId.length > 0;
        }
        if (this._mode === 'span') {
            return typeof this.spanId === 'string' && this.spanId.length > 0;
        }
        if (this._mode === 'user') {
            return typeof this.userId === 'string' && this.userId.length > 0;
        }
        return typeof this.sessionId === 'string' && this.sessionId.length > 0;
    }

    _busy() {
        return this._guestLogs.busy
            || this._byTrace.busy
            || this._bySession.busy
            || this._byRequest.busy
            || this._bySpan.busy
            || this._byUser.busy
            || this._byTaskTraces.busy
            || this._bySessionTraces.busy;
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
        if (this._activeEntries().length > 0) {
            return;
        }
        if (this._busy()) {
            this._scheduleNextPoll();
            return;
        }
        if (this._pollAttempt >= FlowsLogsModal.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollAttempt += 1;
        this.requestUpdate();
        const runs = [
            ...(this._mode === 'trace' ? this._loadTraceResolutionForPoll() : []),
            ...this._load(),
        ];
        if (runs.length === 0) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        Promise.all(runs)
            .catch(() => null)
            .finally(() => this._loadLogsAfterTraceResolution());
    }

    _loadLogsAfterTraceResolution() {
        if (!this.open) {
            this._clearPollTimer();
            return;
        }
        const key = this._logsLoadKey();
        if (this._lastLogsLoadKey !== key) {
            this._lastLogsLoadKey = key;
            const runs = this._load();
            if (runs.length > 0) {
                Promise.all(runs)
                    .catch(() => null)
                    .finally(() => this._syncPollingAfterRender());
                return;
            }
        }
        this._syncPollingAfterRender();
    }

    _scheduleNextPoll() {
        if (!this.open || this._pollTimer !== null) {
            return;
        }
        if (!this._hasLoadTarget() || this._pollExhausted || this._activeEntries().length > 0) {
            return;
        }
        if (this._pollAttempt >= FlowsLogsModal.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollTimer = setTimeout(() => {
            this._pollTimer = null;
            this._loadForPoll();
        }, FlowsLogsModal.pollIntervalMs);
        this.requestUpdate();
    }

    _syncPollingAfterRender() {
        if (!this.open) {
            this._clearPollTimer();
            return;
        }
        if (this._activeEntries().length > 0) {
            this._clearPollTimer();
            return;
        }
        if (this._busy()) {
            return;
        }
        this._scheduleNextPoll();
    }

    _manualReload() {
        this._lastLogsLoadKey = '';
        this._restartPolling();
    }

    _waitingForLogs(entries: any, busy: any, resolving: any) {
        if (entries.length > 0 || !this._hasLoadTarget()) {
            return false;
        }
        if (busy || resolving) {
            return true;
        }
        return !this._pollExhausted && this._pollAttempt < FlowsLogsModal.pollMaxAttempts;
    }

    /** @param {CustomEvent<{ text: string }>} e */
    _onCopyRequest(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.text !== 'string') {
            throw new Error('flows-logs-modal: copy-request requires detail.text string');
        }
        this.copyToClipboard(d.text, {
            success_i18n_key: 'flows:logs_modal.toast_copied',
            error_i18n_key: 'flows:logs_modal.toast_copy_failed',
        });
    }

    override renderHeader() {
        return this.t('logs_modal.title');
    }

    override renderHeaderActions() {
        const busy =
            this._guestLogs.busy
            || this._byTrace.busy
            || this._bySession.busy
            || this._byRequest.busy
            || this._bySpan.busy
            || this._byUser.busy
            || this._byTaskTraces.busy
            || this._bySessionTraces.busy;
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${this.t('logs_modal.reload')}
                ?disabled=${busy}
                @click=${() => this._manualReload()}
            >
                ${busy
                    ? html`<glass-spinner size="xs"></glass-spinner>`
                    : html`<platform-icon name="refresh" size="16"></platform-icon>`}
            </platform-button>
        `;
    }

    override renderBody() {
        const data = this._activeData();
        const entries = this._activeEntries();
        const countValue = isPlainRecord(data) ? data.count : undefined;
        const count = typeof countValue === 'number' ? countValue : entries.length;
        const listBusy = this._guestLogs.busy
            || this._byTrace.busy
            || this._bySession.busy
            || this._byRequest.busy
            || this._bySpan.busy
            || this._byUser.busy;
        if (this._mode === 'guest_runtime') {
            const waiting = this._waitingForLogs(entries, listBusy, false);
            return html`
                <div class="logs-modal-stack">
                    <div class="logs-toolbar">
                        <span class="count-badge">${this.t('logs_modal.count', { count: entries.length })}</span>
                    </div>
                    <div class="logs-main">
                        ${waiting
                            ? html`
                                  <div class="logs-loading">
                                      <glass-spinner></glass-spinner>
                                      <div>${this.t('logs_modal.waiting')}</div>
                                  </div>
                              `
                            : html`
                                  <platform-log-viewer
                                      .entries=${entries}
                                      ?loading=${listBusy}
                                      .emptyLabel=${this.t('logs_modal.empty')}
                                      @copy-request=${(e: CustomEvent) => this._onCopyRequest(e)}
                                  ></platform-log-viewer>
                              `}
                    </div>
                </div>
            `;
        }
        const hasSession = typeof this.sessionId === 'string' && this.sessionId.length > 0;
        const hasRequest = typeof this.requestId === 'string' && this.requestId.length > 0;
        const hasSpan = typeof this.spanId === 'string' && this.spanId.length > 0;
        const hasUser = typeof this.userId === 'string' && this.userId.length > 0;
        const effTrace = this._effectiveTraceId();
        const hasTrace = effTrace.length > 0;
        const hasTraceResolver = hasTrace
            || (typeof this.taskId === 'string' && this.taskId.length > 0)
            || (typeof this.sessionId === 'string' && this.sessionId.length > 0);
        const resolving = this._mode === 'trace' ? this._traceResolutionBusy() : false;
        const waiting = this._waitingForLogs(entries, listBusy, resolving);
        const traceTitle = hasTrace
            ? ''
            : resolving
              ? this.t('logs_modal.tab_trace_resolving_hint')
              : this.t('logs_modal.tab_trace_disabled_hint');
        const modeItems = this._modeSegmentItems({
            hasSession,
            hasTraceResolver,
            hasRequest,
            hasSpan,
            hasUser,
            resolving,
            traceTitle,
        });

        return html`
            <div class="logs-modal-stack">
                <div class="logs-toolbar">
                    <platform-segmented-control
                        class="mode-segment"
                        density="compact"
                        .value=${this._mode}
                        .items=${modeItems}
                        aria-label=${this.t('logs_modal.mode_aria')}
                        @change=${(e: CustomEvent) => this._setMode(e.detail.value)}
                    ></platform-segmented-control>
                    ${data
                        ? html`<span class="count-badge">${this.t('logs_modal.count', { count })}</span>`
                        : nothing}
                </div>
                <div class="logs-main">
                    ${waiting
                        ? html`
                              <div class="logs-loading">
                                  <glass-spinner></glass-spinner>
                                  <div>${this.t('logs_modal.waiting')}</div>
                              </div>
                          `
                        : html`
                              <platform-log-viewer
                                  .entries=${entries}
                                  ?loading=${listBusy}
                                  .emptyLabel=${this.t('logs_modal.empty')}
                                  @copy-request=${(e: CustomEvent) => this._onCopyRequest(e)}
                              ></platform-log-viewer>
                          `}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-logs-modal', FlowsLogsModal);
registerModalKind(FlowsLogsModal.modalKind, 'flows-logs-modal');
