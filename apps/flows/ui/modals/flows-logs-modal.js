/**
 * flows-logs-modal — встроенный просмотр логов flows из Loki.
 *
 * Открывается по sessionId (логи сессии агента в Loki) и опционально taskId —
 * тогда trace_id подставляется из Tempo (GET traces/task) и вкладка «По trace_id»
 * активна; если по task пусто — fallback GET traces/session. Несколько трейсов в одном
 * дереве: сначала trace_id у span с task_id как у A2A (обход дерева), иначе — корень с
 * максимальным start_time. Явный props.traceId отключает запрос по task.
 * Данные: flows/logs_by_session, flows/logs_by_trace; резолв: flows/traces_by_task,
 * flows/traces_by_session. Если Tempo пуст или недоступен — trace_id из уже полученных
 * записей Loki «по сессии» (поле trace_id в JSON строки).
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-log-viewer.js';

/**
 * Первый корень — как раньше для ответа traces/task.
 * @param {unknown[]} roots
 * @returns {string}
 */
function _traceIdFromFirstRoot(roots) {
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
function _traceIdFromLatestRoot(roots) {
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
function _traceIdFromTreeMatchingTask(roots, taskId) {
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
function _traceIdFromSessionTreeForLogs(roots, preferredTaskId) {
    const byTask = _traceIdFromTreeMatchingTask(roots, preferredTaskId);
    if (byTask.length > 0) {
        return byTask;
    }
    return _traceIdFromLatestRoot(roots);
}

/**
 * Когда Tempo не дал trace_id: из ответа Loki by-session (список по времени по возрастанию).
 * @param {unknown[]} entries
 * @returns {string}
 */
function _traceIdFromSessionLokiEntries(entries) {
    if (!Array.isArray(entries) || entries.length === 0) {
        return '';
    }
    for (let i = entries.length - 1; i >= 0; i -= 1) {
        const e = entries[i];
        if (e === null || typeof e !== 'object') {
            continue;
        }
        const top = e.trace_id;
        if (typeof top === 'string' && top.length > 0) {
            return top;
        }
        const raw = e.raw;
        if (
            raw !== null
            && typeof raw === 'object'
            && typeof raw.trace_id === 'string'
            && raw.trace_id.length > 0
        ) {
            return raw.trace_id;
        }
    }
    return '';
}

export class FlowsLogsModal extends PlatformModal {
    static modalKind = 'flows.logs';
    static i18nNamespace = 'flows';
    static pollIntervalMs = 3000;
    static pollMaxAttempts = 20;

    static properties = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        traceId: { type: String },
        taskId: { type: String },
        _mode: { type: String, state: true },
        _pollAttempt: { type: Number, state: true },
        _pollExhausted: { type: Boolean, state: true },
    };

    static styles = [
        ...PlatformModal.styles,
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
            .mode-tabs {
                display: flex;
                gap: var(--space-1);
                background: var(--glass-solid-secondary);
                border-radius: 8px;
                padding: 2px;
            }
            .mode-tab {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                border-radius: 6px;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition:
                    background 0.15s,
                    color 0.15s;
            }
            .mode-tab[data-active] {
                background: var(--glass-solid-primary);
                color: var(--text-primary);
            }
            .mode-tab:disabled {
                opacity: 0.4;
                cursor: default;
            }
            .count-badge {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-solid-secondary);
                padding: 2px 8px;
                border-radius: 12px;
                white-space: nowrap;
            }
            .tab-inline-spin {
                display: inline-flex;
                vertical-align: middle;
                --spinner-size: 12px;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.sessionId = '';
        this.traceId = '';
        this.taskId = '';
        this._mode = 'session';
        this._lastLogsLoadKey = '';
        this._pollAttempt = 0;
        this._pollExhausted = false;
        this._pollTimer = null;
        this._byTrace = this.useOp('flows/logs_by_trace');
        this._bySession = this.useOp('flows/logs_by_session');
        this._byTaskTraces = this.useOp('flows/traces_by_task');
        this._bySessionTraces = this.useOp('flows/traces_by_session');
    }

    _traceIdFromTaskOp() {
        const data = this._byTaskTraces.lastResult;
        if (data === null || typeof data !== 'object') {
            return '';
        }
        const roots = Array.isArray(data.spans) ? data.spans : [];
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
        if (data === null || typeof data !== 'object') {
            return '';
        }
        const roots = Array.isArray(data.spans) ? data.spans : [];
        const preferredTaskId =
            typeof this.taskId === 'string' && this.taskId.length > 0 ? this.taskId : '';
        return _traceIdFromSessionTreeForLogs(roots, preferredTaskId);
    }

    _traceIdFromSessionLogEntries() {
        const data = this._bySession.lastResult;
        if (data === null || typeof data !== 'object') {
            return '';
        }
        const entries = Array.isArray(data.entries) ? data.entries : [];
        return _traceIdFromSessionLokiEntries(entries);
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
        return this._traceIdFromSessionLogEntries();
    }

    _logsLoadKey() {
        const taskId = typeof this.taskId === 'string' ? this.taskId : '';
        const sessionId = typeof this.sessionId === 'string' ? this.sessionId : '';
        const traceId = typeof this.traceId === 'string' ? this.traceId : '';
        if (this._mode === 'trace') {
            return `trace|${this._effectiveTraceId()}|task|${taskId}|session|${sessionId}|prop|${traceId}`;
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

    updated(changed) {
        super.updated?.(changed);

        if (changed.has('open') && !this.open) {
            this._clearPollTimer();
            return;
        }

        if (changed.has('open') && this.open) {
            this._lastLogsLoadKey = '';
        }

        if (changed.has('sessionId') || changed.has('traceId')) {
            if (this.traceId && !this.sessionId) {
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

    disconnectedCallback() {
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
        if (this._mode === 'trace') {
            const tid = this._effectiveTraceId();
            if (tid.length > 0) {
                runs.push(this._byTrace.run({ trace_id: tid }));
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

    _setMode(mode) {
        if (mode !== 'trace' && mode !== 'session') {
            throw new Error('flows-logs-modal: invalid mode');
        }
        if (this._mode === mode) {
            return;
        }
        this._mode = mode;
    }

    _activeData() {
        return this._mode === 'trace' ? this._byTrace.lastResult : this._bySession.lastResult;
    }

    _activeEntries() {
        const data = this._activeData();
        if (data !== null && typeof data === 'object' && Array.isArray(data.entries)) {
            return data.entries;
        }
        return [];
    }

    _hasLoadTarget() {
        if (this._mode === 'trace') {
            return this._effectiveTraceId().length > 0
                || (typeof this.taskId === 'string' && this.taskId.length > 0)
                || (typeof this.sessionId === 'string' && this.sessionId.length > 0);
        }
        return typeof this.sessionId === 'string' && this.sessionId.length > 0;
    }

    _busy() {
        return this._byTrace.busy
            || this._bySession.busy
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
        if (this._pollAttempt >= this.constructor.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollAttempt += 1;
        this.requestUpdate();
        const runs = [
            ...this._loadTraceResolutionForPoll(),
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
        if (this._pollAttempt >= this.constructor.pollMaxAttempts) {
            this._pollExhausted = true;
            this.requestUpdate();
            return;
        }
        this._pollTimer = setTimeout(() => {
            this._pollTimer = null;
            this._loadForPoll();
        }, this.constructor.pollIntervalMs);
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

    _waitingForLogs(entries, busy, resolving) {
        if (entries.length > 0 || !this._hasLoadTarget()) {
            return false;
        }
        if (busy || resolving) {
            return true;
        }
        return !this._pollExhausted && this._pollAttempt < this.constructor.pollMaxAttempts;
    }

    /** @param {CustomEvent<{ text: string }>} e */
    _onCopyRequest(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || typeof d.text !== 'string') {
            throw new Error('flows-logs-modal: copy-request requires detail.text string');
        }
        this.copyToClipboard(d.text, {
            success_i18n_key: 'flows:logs_modal.toast_copied',
            error_i18n_key: 'flows:logs_modal.toast_copy_failed',
        });
    }

    renderHeader() {
        return this.t('logs_modal.title');
    }

    renderHeaderActions() {
        const busy =
            this._byTrace.busy
            || this._bySession.busy
            || this._byTaskTraces.busy
            || this._bySessionTraces.busy;
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('logs_modal.reload')}
                aria-label=${this.t('logs_modal.reload')}
                ?disabled=${busy}
                @click=${() => this._manualReload()}
            >
                ${busy
                    ? html`<glass-spinner size="14"></glass-spinner>`
                    : html`<platform-icon name="refresh" size="16"></platform-icon>`}
            </button>
        `;
    }

    renderBody() {
        const data = this._activeData();
        const entries = this._activeEntries();
        const count = typeof data?.count === 'number' ? data.count : entries.length;
        const listBusy = this._byTrace.busy || this._bySession.busy;
        const hasSession = typeof this.sessionId === 'string' && this.sessionId.length > 0;
        const effTrace = this._effectiveTraceId();
        const hasTrace = effTrace.length > 0;
        const resolving = this._traceResolutionBusy();
        const waiting = this._waitingForLogs(entries, listBusy, resolving);
        const traceTitle = hasTrace
            ? ''
            : resolving
              ? this.t('logs_modal.tab_trace_resolving_hint')
              : this.t('logs_modal.tab_trace_disabled_hint');
        const traceAria = hasTrace ? this.t('logs_modal.tab_trace') : traceTitle;

        return html`
            <div class="logs-modal-stack">
                <div class="logs-toolbar">
                    <div class="mode-tabs">
                        <button
                            type="button"
                            class="mode-tab"
                            ?data-active=${this._mode === 'session'}
                            ?disabled=${!hasSession}
                            @click=${() => this._setMode('session')}
                        >
                            ${this.t('logs_modal.tab_session')}</button
                        >
                        <button
                            type="button"
                            class="mode-tab"
                            ?data-active=${this._mode === 'trace'}
                            ?disabled=${!hasTrace}
                            title=${traceTitle}
                            aria-label=${traceAria}
                            @click=${() => this._setMode('trace')}
                        >
                            ${resolving
                                ? html`<span class="tab-inline-spin"><glass-spinner size="sm"></glass-spinner></span>`
                                : nothing}
                            ${this.t('logs_modal.tab_trace')}</button
                        >
                    </div>
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
                                  @copy-request=${(e) => this._onCopyRequest(e)}
                              ></platform-log-viewer>
                          `}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-logs-modal', FlowsLogsModal);
registerModalKind(FlowsLogsModal.modalKind, 'flows-logs-modal');
