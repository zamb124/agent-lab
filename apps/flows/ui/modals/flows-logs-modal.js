/**
 * flows-logs-modal — встроенный просмотр логов flows из Loki.
 *
 * Открывается по trace_id (из конкретного span трейса) или по sessionId
 * (все логи сессии). Два режима переключаются кнопками-вкладками.
 * Данные загружаются через ops flows/logs_by_trace и flows/logs_by_session.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const _LEVEL_COLORS = {
    error: 'var(--color-error, #e53e3e)',
    warning: 'var(--color-warning, #d69e2e)',
    warn: 'var(--color-warning, #d69e2e)',
    info: 'var(--text-primary)',
    debug: 'var(--text-tertiary)',
};

export class FlowsLogsModal extends PlatformModal {
    static modalKind = 'flows.logs';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        sessionId: { type: String },
        traceId: { type: String },
        _mode: { type: String, state: true },
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
                align-items: center;
                justify-content: center;
                min-height: 240px;
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
                padding: 4px 12px;
                border-radius: 6px;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background 0.15s, color 0.15s;
            }
            .mode-tab[data-active] {
                background: var(--glass-solid-primary);
                color: var(--text-primary);
            }
            .mode-tab:disabled {
                opacity: 0.4;
                cursor: default;
            }
            .logs-empty {
                padding: var(--space-8) var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .logs-unavailable {
                padding: var(--space-8) var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .log-list {
                display: flex;
                flex-direction: column;
                gap: 0;
                font-family: var(--font-mono, monospace);
                font-size: 12px;
                overflow-y: auto;
                max-height: calc(100vh - 260px);
            }
            .log-entry {
                display: grid;
                grid-template-columns: 160px 52px 1fr auto;
                gap: var(--space-2);
                padding: 5px var(--space-4);
                border-bottom: 1px solid var(--glass-border-secondary, rgba(255,255,255,0.06));
                align-items: start;
                line-height: 1.4;
            }
            .log-entry:hover {
                background: var(--glass-solid-secondary);
            }
            .log-ts {
                color: var(--text-tertiary);
                white-space: nowrap;
                font-size: 11px;
                padding-top: 1px;
            }
            .log-level {
                font-weight: 600;
                text-transform: uppercase;
                font-size: 11px;
                padding-top: 1px;
                white-space: nowrap;
            }
            .log-message {
                word-break: break-word;
                color: var(--text-primary);
            }
            .log-service {
                font-size: 10px;
                color: var(--text-tertiary);
                white-space: nowrap;
                padding-top: 2px;
            }
            .log-copy-btn {
                background: transparent;
                border: none;
                cursor: pointer;
                color: var(--text-tertiary);
                padding: 0 2px;
                opacity: 0;
                transition: opacity 0.1s;
            }
            .log-entry:hover .log-copy-btn {
                opacity: 1;
            }
            .count-badge {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-solid-secondary);
                padding: 2px 8px;
                border-radius: 12px;
                white-space: nowrap;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.sessionId = '';
        this.traceId = '';
        this._mode = 'session';
        this._byTrace = this.useOp('flows/logs_by_trace');
        this._bySession = this.useOp('flows/logs_by_session');
    }

    updated(changed) {
        super.updated?.(changed);
        const sessionChanged = changed.has('sessionId') && this.sessionId;
        const traceChanged = changed.has('traceId') && this.traceId;
        const modeChanged = changed.has('_mode');

        if (changed.has('sessionId') || changed.has('traceId')) {
            if (this.traceId && !this.sessionId) {
                this._mode = 'trace';
            } else {
                this._mode = 'session';
            }
        }

        if (sessionChanged || traceChanged || modeChanged) {
            this._load();
        }
    }

    _load() {
        if (this._mode === 'trace' && this.traceId) {
            void this._byTrace.run({ trace_id: this.traceId });
        } else if (this._mode === 'session' && this.sessionId) {
            void this._bySession.run({ session_id: this.sessionId });
        }
    }

    _setMode(mode) {
        if (mode !== 'trace' && mode !== 'session') {
            throw new Error('flows-logs-modal: invalid mode');
        }
        this._mode = mode;
    }

    _activeData() {
        return this._mode === 'trace' ? this._byTrace.lastResult : this._bySession.lastResult;
    }

    _levelColor(level) {
        const key = typeof level === 'string' ? level.toLowerCase() : '';
        return _LEVEL_COLORS[key] || 'var(--text-primary)';
    }

    _formatTs(ts) {
        if (!ts) return '';
        try {
            const d = new Date(ts);
            return d.toISOString().replace('T', ' ').replace('Z', '').slice(0, 23);
        } catch {
            return ts;
        }
    }

    _copyEntry(entry) {
        const text = JSON.stringify(entry.raw || entry, null, 2);
        this.copyToClipboard(text, {
            success_i18n_key: 'flows:logs_modal.toast_copied',
            error_i18n_key: 'flows:logs_modal.toast_copy_failed',
        });
    }

    renderHeader() {
        return this.t('logs_modal.title');
    }

    renderHeaderActions() {
        const busy = this._byTrace.busy || this._bySession.busy;
        return html`
            <button
                type="button"
                class="header-btn"
                title=${this.t('logs_modal.reload')}
                aria-label=${this.t('logs_modal.reload')}
                ?disabled=${busy}
                @click=${() => this._load()}
            >
                ${busy
                    ? html`<glass-spinner size="14"></glass-spinner>`
                    : html`<platform-icon name="refresh" size="16"></platform-icon>`}
            </button>
        `;
    }

    renderBody() {
        const data = this._activeData();
        const entries = Array.isArray(data?.entries) ? data.entries : [];
        const count = typeof data?.count === 'number' ? data.count : entries.length;
        const busy = this._byTrace.busy || this._bySession.busy;
        const hasSession = typeof this.sessionId === 'string' && this.sessionId.length > 0;
        const hasTrace = typeof this.traceId === 'string' && this.traceId.length > 0;

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
                        >${this.t('logs_modal.tab_session')}</button>
                        <button
                            type="button"
                            class="mode-tab"
                            ?data-active=${this._mode === 'trace'}
                            ?disabled=${!hasTrace}
                            @click=${() => this._setMode('trace')}
                        >${this.t('logs_modal.tab_trace')}</button>
                    </div>
                    ${data ? html`<span class="count-badge">${this.t('logs_modal.count', { count })}</span>` : nothing}
                </div>
                <div class="logs-main">
                    ${busy && entries.length === 0
                        ? html`<div class="logs-loading"><glass-spinner></glass-spinner></div>`
                        : entries.length === 0
                            ? html`<div class="logs-empty">${this.t('logs_modal.empty')}</div>`
                            : html`
                                <div class="log-list">
                                    ${entries.map((entry) => html`
                                        <div class="log-entry">
                                            <span class="log-ts">${this._formatTs(entry.timestamp)}</span>
                                            <span class="log-level" style="color:${this._levelColor(entry.level)}">${entry.level || '—'}</span>
                                            <span class="log-message">${entry.message || entry.raw?.message || ''}</span>
                                            <span class="log-service">${entry.service || ''}</span>
                                        </div>
                                    `)}
                                </div>
                            `
                    }
                </div>
            </div>
        `;
    }
}

customElements.define('flows-logs-modal', FlowsLogsModal);
registerModalKind(FlowsLogsModal.modalKind, 'flows-logs-modal');
