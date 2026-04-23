/**
 * Лента событий исполнения flow (A2A run trace), общая для execution panel и чата.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { asArray, asString } from '../../_helpers/flows-resolvers.js';

export class FlowsChatRunTrace extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        entries: { type: Array },
        compact: { type: Boolean },
        showSectionHeader: { type: Boolean, attribute: 'show-section-header' },
        fillAvailable: { type: Boolean, attribute: 'fill-available', reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            :host([fill-available]) {
                height: 100%;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .wrap {
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            :host([fill-available]) .wrap {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .wrap.compact {
                border-radius: var(--radius-xl);
            }
            .wrap.no-head .list {
                border-radius: var(--radius-xl);
            }
            .head {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
            }
            .list {
                max-height: min(220px, 40vh);
                overflow-y: auto;
                padding: var(--space-3);
            }
            .list.compact {
                max-height: min(260px, 38vh);
            }
            :host([fill-available]) .list {
                flex: 1;
                min-height: 0;
                max-height: none;
                overflow-y: auto;
            }
            :host([fill-available]) .list.compact {
                max-height: none;
            }
            .timeline {
                position: relative;
                padding-left: 20px;
            }
            .timeline::before {
                content: '';
                position: absolute;
                left: 10px;
                top: 6px;
                bottom: 6px;
                width: 2px;
                background: var(--glass-border-medium);
                border-radius: 1px;
            }
            .card {
                position: relative;
                margin-bottom: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-strong);
                transition: border-color var(--duration-fast), box-shadow var(--duration-fast),
                    transform var(--duration-fast);
            }
            .card:last-child {
                margin-bottom: 0;
            }
            .card:hover {
                border-color: var(--glass-border-medium);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }
            .card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .card-interactive {
                cursor: pointer;
            }
            .card::before {
                content: '';
                position: absolute;
                left: -15px;
                top: 14px;
                width: 10px;
                height: 10px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong);
                border: 2px solid var(--glass-border-medium);
                z-index: 1;
            }
            .card.ok::before {
                border-color: var(--success, #22c55e);
            }
            .card.err::before {
                border-color: var(--error);
            }
            .card-inner {
                display: grid;
                grid-template-columns: 28px 1fr;
                gap: var(--space-2);
                align-items: flex-start;
            }
            .icon-cell {
                width: 28px;
                height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                flex-shrink: 0;
            }
            .card.ok .icon-cell {
                color: var(--success, #22c55e);
            }
            .card.err .icon-cell {
                color: var(--error);
            }
            .main {
                min-width: 0;
            }
            .title-line {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                line-height: 1.35;
                color: var(--text-primary);
                flex: 1;
                min-width: 0;
            }
            .expando-chevron {
                flex-shrink: 0;
                color: var(--text-tertiary);
                margin-top: 1px;
            }
            .meta {
                font-size: 10px;
                color: var(--text-tertiary);
                margin-top: 4px;
                line-height: 1.35;
            }
            .detail {
                margin-top: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                font-family: var(--font-mono);
                font-size: 10px;
                line-height: 1.4;
                white-space: pre-wrap;
                word-break: break-word;
                max-height: min(320px, 42vh);
                overflow-y: auto;
                user-select: text;
                cursor: auto;
            }
            .empty {
                padding: var(--space-3);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .empty--fill {
                flex: 1;
                min-height: 0;
                display: flex;
                align-items: center;
                justify-content: center;
            }
        `,
    ];

    constructor() {
        super();
        this.entries = [];
        this.compact = false;
        this.showSectionHeader = true;
        this.fillAvailable = false;
        /** @type {Set<string>} */
        this._open = new Set();
    }

    _toggle(id) {
        if (this._open.has(id)) {
            this._open.delete(id);
        } else {
            this._open.add(id);
        }
        this._open = new Set(this._open);
        this.requestUpdate();
    }

    /**
     * @param {MouseEvent} e
     * @param {string} id
     */
    _onCardClick(e, id) {
        const t = e.target;
        if (t && typeof t.closest === 'function' && t.closest('.detail')) {
            return;
        }
        this._toggle(id);
    }

    /**
     * @param {KeyboardEvent} e
     * @param {string} id
     */
    _onCardKeydown(e, id) {
        if (e.key !== 'Enter' && e.key !== ' ') {
            return;
        }
        e.preventDefault();
        this._toggle(id);
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    _inspectBody(entry) {
        const detail = this._detailText(entry);
        const json = JSON.stringify(entry, null, 2);
        if (typeof json !== 'string') {
            throw new Error('flows-chat-run-trace: stringify failed');
        }
        if (detail.length > 0) {
            return `${detail}\n\n---\n\n${json}`;
        }
        return json;
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    _cardClass(entry) {
        const k = asString(entry.kind);
        if (k === 'node_error' || k === 'status_terminal') {
            const st = asString(entry.terminal_state);
            if (st === 'failed' || st === 'error') return 'card err';
        }
        if (k === 'node_complete' || k === 'tool_result') return 'card ok';
        return 'card';
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    _iconName(entry) {
        const k = asString(entry.kind);
        if (k === 'node_start') return 'play';
        if (k === 'node_complete') return 'check';
        if (k === 'node_error') return 'close';
        if (k === 'tool_call') return 'zap';
        if (k === 'tool_result') return 'check';
        if (k === 'reasoning_chunk') return 'chat';
        if (k === 'operator_files') return 'paperclip';
        if (k === 'ui_event') return 'bell';
        if (k === 'flow_artifact') return 'code';
        if (k === 'status_terminal') {
            const st = asString(entry.terminal_state);
            if (st === 'failed' || st === 'error') return 'close';
            return 'check';
        }
        if (k === 'breakpoint') return 'pause';
        if (k === 'input_required') return 'help';
        return 'chart';
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    _title(entry) {
        const k = asString(entry.kind);
        const nid = asString(entry.node_id);
        const tool = asString(entry.tool);
        if (k === 'node_start') {
            const nt = asString(entry.node_type);
            const suffix = nt.length > 0 ? ` (${nt})` : '';
            return this.t('run_trace.node_start', { node: nid, suffix });
        }
        if (k === 'node_complete') {
            return this.t('run_trace.node_complete', { node: nid });
        }
        if (k === 'node_error') {
            return this.t('run_trace.node_error', { node: nid });
        }
        if (k === 'tool_call') {
            return this.t('run_trace.tool_call', { tool });
        }
        if (k === 'tool_result') {
            return this.t('run_trace.tool_result', { tool });
        }
        if (k === 'reasoning_chunk') {
            const n = entry.char_count;
            const c = typeof n === 'number' ? n : 0;
            return this.t('run_trace.reasoning_chunk', { chars: String(c) });
        }
        if (k === 'operator_files') {
            const n = entry.file_count;
            const c = typeof n === 'number' ? n : 0;
            return this.t('run_trace.operator_files', { count: String(c) });
        }
        if (k === 'ui_event') {
            return this.t('run_trace.ui_event', { type: asString(entry.event_type) });
        }
        if (k === 'flow_artifact') {
            return this.t('run_trace.flow_artifact');
        }
        if (k === 'status_terminal') {
            return this.t('run_trace.status_terminal', { state: asString(entry.terminal_state) });
        }
        if (k === 'breakpoint') {
            return this.t('run_trace.breakpoint', { node: nid });
        }
        if (k === 'input_required') {
            return this.t('run_trace.input_required');
        }
        return k;
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    _detailText(entry) {
        const k = asString(entry.kind);
        if (k === 'node_error') {
            return asString(entry.error);
        }
        if (k === 'node_complete') {
            return asString(entry.result_preview);
        }
        if (k === 'status_terminal') {
            return asString(entry.message_preview);
        }
        if (k === 'flow_artifact') {
            return asString(entry.preview);
        }
        if (k === 'ui_event') {
            return asString(entry.payload_preview);
        }
        return '';
    }

    /**
     * @param {Record<string, unknown>} entry
     */
    /**
     * @param {Record<string, unknown>} entry
     */
    _metaLine(entry) {
        const bits = [];
        const d = entry.duration_ms;
        if (typeof d === 'number' && Number.isFinite(d)) {
            bits.push(this.t('run_trace.meta_duration', { ms: String(Math.round(d)) }));
        }
        const tok = entry.total_tokens;
        if (typeof tok === 'number' && Number.isFinite(tok)) {
            bits.push(this.t('run_trace.meta_tokens', { n: String(Math.round(tok)) }));
        }
        if (bits.length === 0) {
            return '';
        }
        return bits.join(' · ');
    }

    render() {
        const entries = asArray(this.entries);
        if (entries.length === 0) {
            const fill = Boolean(this.fillAvailable);
            return html`<div class="empty ${fill ? 'empty--fill' : ''}">${this.t('run_trace.empty')}</div>`;
        }
        const compact = Boolean(this.compact);
        const showHead = Boolean(this.showSectionHeader);
        return html`
            <div class="wrap ${compact ? 'compact' : ''} ${showHead ? '' : 'no-head'}">
                ${showHead ? html`
                    <div class="head">
                        <platform-icon name="chart" size="14"></platform-icon>
                        ${this.t('run_trace.section_title')}
                    </div>
                ` : nothing}
                <div class="list ${compact ? 'compact' : ''}">
                    <div class="timeline">
                        ${entries.map((entry) => {
                            if (!entry || typeof entry !== 'object') return nothing;
                            const id = asString(entry.id);
                            if (id.length === 0) return nothing;
                            const show = this._open.has(id);
                            const meta = this._metaLine(entry);
                            const inspect = this._inspectBody(entry);
                            const ariaLabel = show
                                ? this.t('run_trace.step_collapse_aria')
                                : this.t('run_trace.step_expand_aria');
                            return html`
                                <div
                                    class="${this._cardClass(entry)} card-interactive"
                                    role="button"
                                    tabindex="0"
                                    aria-expanded=${show ? 'true' : 'false'}
                                    aria-label=${ariaLabel}
                                    @click=${(e) => this._onCardClick(e, id)}
                                    @keydown=${(e) => this._onCardKeydown(e, id)}
                                >
                                    <div class="card-inner">
                                        <div class="icon-cell">
                                            <platform-icon name=${this._iconName(entry)} size="14"></platform-icon>
                                        </div>
                                        <div class="main">
                                            <div class="title-line">
                                                <div class="title">${this._title(entry)}</div>
                                                <platform-icon
                                                    class="expando-chevron"
                                                    name=${show ? 'chevron-up' : 'chevron-down'}
                                                    size="14"
                                                ></platform-icon>
                                            </div>
                                            ${meta.length > 0 ? html`<div class="meta">${meta}</div>` : nothing}
                                            ${show ? html`<div class="detail">${inspect}</div>` : nothing}
                                        </div>
                                    </div>
                                </div>
                            `;
                        })}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-chat-run-trace', FlowsChatRunTrace);
