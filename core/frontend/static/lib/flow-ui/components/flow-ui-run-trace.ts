/**
 * Таймлайн выполнения: записи ``{id, kind, node_id?, tool?, ...}``. Даются явно (``entries`` —
 * панель выполнения редактора) или выводятся из платформенных data-артефактов Tasks (``tasks`` —
 * блок ``run_trace``). Автономен от i18n-шины (embed): подписи — ``flowUIText``.
 */

import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { isPlainRecord } from '../../events/payload.js';
import type { FlowUiTask } from '../runtime/conversation.js';
import type { FlowUiRecord } from '../runtime/flow-ui-store.js';
import { firstDataFromParts, textFromParts } from '../../a2a/parts.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';

const GLYPH_BY_KIND: Readonly<Record<string, string>> = Object.freeze({
    node_start: 'play', node_complete: 'check', node_error: 'alert-triangle', tool_call: 'refresh', tool_result: 'check',
    edge_executed: 'chevron-right', edge_error: 'alert-triangle', breakpoint: 'pause', input_required: 'info', status_terminal: 'check',
});

function glyphName(kind: unknown): string {
    if (typeof kind !== 'string') return 'info';
    const glyph = GLYPH_BY_KIND[kind];
    return glyph === undefined ? 'info' : glyph;
}

function taskArtifacts(task: FlowUiTask): FlowUiRecord[] {
    if (!Array.isArray(task.artifacts)) return [];
    const artifacts: FlowUiRecord[] = [];
    for (const artifact of task.artifacts) {
        if (!isPlainRecord(artifact)) throw new Error('flow-ui: run trace artifact must be an object');
        artifacts.push(artifact);
    }
    return artifacts;
}

/** Записи таймлайна из артефактов Tasks (тот же формат, что у панели выполнения редактора). */
export function runTraceEntriesFromTasks(tasks: FlowUiTask[]): FlowUiRecord[] {
    const entries: FlowUiRecord[] = [];
    for (const task of tasks) {
        for (const artifact of taskArtifacts(task)) {
            const data = firstDataFromParts(artifact.parts);
            if (!isPlainRecord(data)) continue;
            const base = { id: `${task.id}:${artifact.artifactId}`, task_id: task.id };
            if (typeof data.tool === 'string' && typeof data.tool_call_id === 'string') {
                const isResult = Object.prototype.hasOwnProperty.call(data, 'result');
                entries.push({ ...base, kind: isResult ? 'tool_result' : 'tool_call', tool: data.tool });
            } else if (data.event === 'node_start' || data.event === 'node_complete' || data.event === 'node_error') {
                entries.push({ ...base, kind: data.event, ...data });
            } else if (data.event === 'edge_executed' || data.event === 'edge_error') {
                entries.push({ ...base, kind: data.event, ...data });
            }
        }
        const status = task.status;
        if (!isPlainRecord(status)) continue;
        const state = status.state;
        if (state === 'TASK_STATE_COMPLETED' || state === 'TASK_STATE_FAILED' || state === 'TASK_STATE_CANCELED') {
            const message = status.message;
            const parts = isPlainRecord(message) ? message.parts : undefined;
            entries.push({
                id: `${task.id}:status`, task_id: task.id, kind: 'status_terminal',
                terminal_state: String(state).replace('TASK_STATE_', '').toLowerCase(),
                message_preview: textFromParts(parts).slice(0, 160),
            });
        }
    }
    return entries;
}

export class FlowUIRunTrace extends LitElement {
    declare entries: FlowUiRecord[] | null;
    declare tasks: FlowUiTask[] | null;
    declare locale: string;
    declare compact: boolean;
    declare showSectionHeader: boolean;
    declare fillAvailable: boolean;
    declare _open: Set<unknown>;

    static override properties = {
        entries: { attribute: false },
        tasks: { attribute: false },
        locale: { type: String },
        compact: { type: Boolean },
        showSectionHeader: { type: Boolean, attribute: 'show-section-header' },
        fillAvailable: { type: Boolean, attribute: 'fill-available' },
        _open: { state: true },
    };

    static override styles = css`
        :host { display: block; color: var(--flow-ui-text, var(--text-primary)); font-size: 13px; }
        :host([fill-available]) { height: 100%; }
        .head { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .02em; color: var(--flow-ui-muted, var(--text-tertiary)); margin-bottom: 8px; }
        .empty { padding: 14px; text-align: center; color: var(--flow-ui-muted, var(--text-tertiary)); font-size: 12.5px; }
        .empty.fill { height: 100%; display: grid; place-items: center; }
        ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
        .compact ol { gap: 3px; }
        li { display: grid; grid-template-columns: 22px 1fr; gap: 8px; align-items: start; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--flow-ui-border, var(--border-default)); background: var(--flow-ui-surface-subtle, transparent); cursor: pointer; }
        .compact li { padding: 5px 8px; }
        li[data-tone='error'] { border-color: color-mix(in srgb, var(--error, #ff718d) 45%, transparent); }
        li[data-tone='ok'] .glyph { opacity: .8; }
        .glyph { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 6px; background: var(--flow-ui-chip, var(--accent-subtle)); color: var(--flow-ui-text, var(--text-primary)); }
        .glyph img { width: 12px; height: 12px; filter: var(--flow-ui-glyph-filter, brightness(0) saturate(100%) invert(88%) opacity(.92)); }
        .glyph svg.fu-glyph { width: 12px; height: 12px; }
        .title { display: flex; justify-content: space-between; gap: 8px; font-weight: 500; }
        .kind { font-family: var(--font-mono); font-size: 11px; color: var(--flow-ui-muted, var(--text-tertiary)); }
        .meta { font-size: 11.5px; color: var(--flow-ui-muted, var(--text-tertiary)); margin-top: 2px; }
        pre { margin: 6px 0 0; padding: 8px; border-radius: 8px; background: var(--flow-ui-input, rgba(0,0,0,.2)); font: 11.5px/1.45 var(--font-mono); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 260px; overflow: auto; }
    `;

    constructor() {
        super();
        this.entries = null;
        this.tasks = null;
        this.locale = 'auto';
        this.compact = false;
        this.showSectionHeader = false;
        this.fillAvailable = false;
        this._open = new Set();
    }

    _entries() {
        if (Array.isArray(this.entries)) return this.entries;
        if (Array.isArray(this.tasks)) return runTraceEntriesFromTasks(this.tasks);
        return [];
    }

    private _toggle(id: unknown) {
        const open = new Set(this._open);
        if (open.has(id)) open.delete(id); else open.add(id);
        this._open = open;
    }

    private _title(entry: FlowUiRecord, locale: string): string {
        const node = typeof entry.node_id === 'string' ? entry.node_id : '';
        if (entry.kind === 'node_start') return `${node} · ${flowUIText(locale, 'node_start')}${typeof entry.node_type === 'string' && entry.node_type !== '' ? ` (${entry.node_type})` : ''}`;
        if (entry.kind === 'node_complete') return `${node} · ${flowUIText(locale, 'node_complete')}`;
        if (entry.kind === 'node_error') return `${node} · ${flowUIText(locale, 'node_error')}`;
        if (entry.kind === 'tool_call' || entry.kind === 'tool_result') return String(entry.tool);
        if (entry.kind === 'edge_executed' || entry.kind === 'edge_error') return `${entry.from_node} → ${entry.to_node}`;
        if (entry.kind === 'status_terminal') return String(entry.terminal_state);
        if (entry.kind === 'breakpoint') return `${node} · breakpoint`;
        return String(entry.kind);
    }

    private _detail(entry: FlowUiRecord): string {
        if (entry.kind === 'node_error' || entry.kind === 'edge_error') return typeof entry.error === 'string' ? entry.error : '';
        if (entry.kind === 'node_complete') return typeof entry.result_preview === 'string' ? entry.result_preview : '';
        if (entry.kind === 'status_terminal') return typeof entry.message_preview === 'string' ? entry.message_preview : '';
        return '';
    }

    private _tone(entry: FlowUiRecord): 'error' | 'ok' | 'neutral' {
        if (entry.kind === 'node_error' || entry.kind === 'edge_error') return 'error';
        if (entry.kind === 'status_terminal') return entry.terminal_state === 'failed' ? 'error' : 'ok';
        if (entry.kind === 'node_complete' || entry.kind === 'tool_result') return 'ok';
        return 'neutral';
    }

    override render() {
        const locale = resolveFlowUILocale(this.locale);
        const entries = this._entries();
        if (entries.length === 0) {
            return html`<div class="empty ${this.fillAvailable ? 'fill' : ''}">${flowUIText(locale, 'run_trace_empty')}</div>`;
        }
        return html`<div class=${this.compact ? 'compact' : ''}>
            ${this.showSectionHeader ? html`<div class="head">${flowUIText(locale, 'run_trace')}</div>` : nothing}
            <ol>${entries.map((entry) => {
                const open = this._open.has(entry.id);
                const detail = this._detail(entry);
                const duration = typeof entry.duration_ms === 'number' ? `${Math.round(entry.duration_ms)} ms` : '';
                return html`<li data-kind=${entry.kind} data-tone=${this._tone(entry)} role="button" tabindex="0" aria-expanded=${open ? 'true' : 'false'}
                    @click=${() => this._toggle(entry.id)}
                    @keydown=${(event: KeyboardEvent) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this._toggle(entry.id); } }}>
                    <span class="glyph">${flowUIGlyph(glyphName(entry.kind), 12)}</span>
                    <span>
                        <span class="title"><span>${this._title(entry, locale)}</span><span class="kind">${entry.kind}</span></span>
                        ${duration !== '' ? html`<div class="meta">${duration}</div>` : nothing}
                        ${open ? html`<pre>${detail !== '' ? `${detail}\n\n` : ''}${JSON.stringify(entry, null, 2)}</pre>` : nothing}
                    </span>
                </li>`;
            })}</ol>
        </div>`;
    }
}

if (!customElements.get('flow-ui-run-trace')) customElements.define('flow-ui-run-trace', FlowUIRunTrace);
