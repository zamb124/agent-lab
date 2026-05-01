/**
 * platform-log-viewer — презентационный список записей логов платформы (форма записей из Loki-клиента).
 * Данные передаёт родитель (`entries`, `loading`); загрузки и bus-событий нет.
 * Копирование: `this.emit('copy-request', { text })`.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const LEVEL_COLORS = Object.freeze({
    error: 'var(--color-error, #e53e3e)',
    warning: 'var(--color-warning, #d69e2e)',
    warn: 'var(--color-warning, #d69e2e)',
    info: 'var(--text-primary)',
    debug: 'var(--text-tertiary)',
});

function _entryRowKey(entry, idx) {
    const ts = typeof entry.timestamp === 'string' ? entry.timestamp : '';
    return `${idx}:${ts}`;
}

export class PlatformLogViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        entries: { type: Array },
        loading: { type: Boolean },
        emptyLabel: { type: String },
        _expandedKey: { type: String, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .log-viewer-root {
                display: flex;
                flex-direction: column;
                min-height: 0;
            }
            .log-viewer-loading {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 200px;
            }
            .log-viewer-empty {
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
                grid-template-columns: 22px 160px 52px 1fr auto minmax(0, auto);
                gap: var(--space-2);
                padding: 5px var(--space-4);
                border-bottom: 1px solid var(--glass-border-secondary, rgba(255, 255, 255, 0.06));
                align-items: start;
                line-height: 1.4;
                cursor: pointer;
            }
            .log-entry[data-expanded] {
                background: var(--glass-solid-secondary);
            }
            .log-entry:hover {
                background: var(--glass-solid-secondary);
            }
            .log-expand {
                display: flex;
                align-items: flex-start;
                padding-top: 2px;
                color: var(--text-tertiary);
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
            .log-actions {
                display: flex;
                align-items: flex-start;
                gap: 2px;
                padding-top: 0;
            }
            .log-copy-btn {
                background: transparent;
                border: none;
                cursor: pointer;
                color: var(--text-tertiary);
                padding: 2px;
                border-radius: 4px;
                opacity: 0;
                transition: opacity 0.1s;
            }
            .log-entry:hover .log-copy-btn {
                opacity: 1;
            }
            .log-copy-btn:focus-visible {
                opacity: 1;
                outline: 2px solid var(--accent);
            }
            .log-raw-wrap {
                grid-column: 1 / -1;
                margin: var(--space-2) 0 0 0;
                padding: var(--space-3);
                background: var(--glass-solid-primary);
                border-radius: 6px;
                overflow-x: auto;
            }
            .log-raw-pre {
                margin: 0;
                white-space: pre-wrap;
                word-break: break-word;
                font-family: var(--font-mono, monospace);
                font-size: 11px;
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.entries = [];
        this.loading = false;
        this.emptyLabel = '';
        this._expandedKey = '';
    }

    _levelColor(level) {
        const key = typeof level === 'string' ? level.toLowerCase() : '';
        const c = LEVEL_COLORS[key];
        if (typeof c === 'string' && c.length > 0) {
            return c;
        }
        return 'var(--text-primary)';
    }

    _formatTs(ts) {
        if (typeof ts !== 'string' || ts.length === 0) {
            return '';
        }
        try {
            const d = new Date(ts);
            return d.toISOString().replace('T', ' ').replace('Z', '').slice(0, 23);
        } catch {
            return ts;
        }
    }

    _messageLine(entry) {
        if (typeof entry.message === 'string' && entry.message.length > 0) {
            return entry.message;
        }
        const raw = entry.raw;
        if (raw && typeof raw === 'object' && typeof raw.message === 'string') {
            return raw.message;
        }
        return '';
    }

    _levelLine(entry) {
        if (typeof entry.level === 'string' && entry.level.length > 0) {
            return entry.level;
        }
        return '—';
    }

    _serviceLine(entry) {
        if (typeof entry.service === 'string' && entry.service.length > 0) {
            return entry.service;
        }
        return '';
    }

    _toggleRow(key) {
        if (this._expandedKey === key) {
            this._expandedKey = '';
        } else {
            this._expandedKey = key;
        }
    }

    _stopRowClick(ev) {
        ev.stopPropagation();
    }

    _copyLine(entry) {
        const raw = entry.raw;
        let text;
        if (raw !== undefined && raw !== null && typeof raw === 'object') {
            text = JSON.stringify(raw, null, 2);
        } else {
            text = JSON.stringify(entry, null, 2);
        }
        this.emit('copy-request', { text });
    }

    _rawBlock(entry) {
        const raw = entry.raw;
        if (raw !== undefined && raw !== null && typeof raw === 'object') {
            return JSON.stringify(raw, null, 2);
        }
        return JSON.stringify(entry, null, 2);
    }

    _emptyText() {
        if (typeof this.emptyLabel === 'string' && this.emptyLabel.length > 0) {
            return this.emptyLabel;
        }
        return this.t('log_viewer.empty');
    }

    render() {
        const list = Array.isArray(this.entries) ? this.entries : [];
        if (this.loading && list.length === 0) {
            return html`
                <div class="log-viewer-root">
                    <div class="log-viewer-loading"><glass-spinner></glass-spinner></div>
                </div>
            `;
        }
        if (list.length === 0) {
            return html`
                <div class="log-viewer-root">
                    <div class="log-viewer-empty">${this._emptyText()}</div>
                </div>
            `;
        }
        return html`
            <div class="log-viewer-root">
                <div class="log-list" role="list">
                    ${list.map((entry, idx) => {
                        const key = _entryRowKey(entry, idx);
                        const expanded = this._expandedKey === key;
                        const chevron = expanded ? 'chevron-down' : 'chevron-right';
                        return html`
                            <div
                                class="log-entry"
                                role="listitem"
                                ?data-expanded=${expanded}
                                @click=${() => this._toggleRow(key)}
                            >
                                <span class="log-expand" aria-hidden="true">
                                    <platform-icon name=${chevron} size="14"></platform-icon>
                                </span>
                                <span class="log-ts">${this._formatTs(entry.timestamp)}</span>
                                <span
                                    class="log-level"
                                    style="color:${this._levelColor(entry.level)}"
                                    >${this._levelLine(entry)}</span
                                >
                                <span class="log-message">${this._messageLine(entry)}</span>
                                <span class="log-service">${this._serviceLine(entry)}</span>
                                <span class="log-actions" @click=${this._stopRowClick}>
                                    <button
                                        type="button"
                                        class="log-copy-btn"
                                        title=${this.t('log_viewer.copy_aria')}
                                        aria-label=${this.t('log_viewer.copy_aria')}
                                        @click=${() => this._copyLine(entry)}
                                    >
                                        <platform-icon name="copy" size="14"></platform-icon>
                                    </button>
                                </span>
                                ${expanded
                                    ? html`
                                          <div class="log-raw-wrap">
                                              <pre class="log-raw-pre">${this._rawBlock(entry)}</pre>
                                          </div>
                                      `
                                    : nothing}
                            </div>
                        `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('platform-log-viewer', PlatformLogViewer);
