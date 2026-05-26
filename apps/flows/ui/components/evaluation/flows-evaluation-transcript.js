import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';

function asArray(value) {
    return Array.isArray(value) ? value : [];
}

function stringValue(record, field) {
    if (!record || typeof record !== 'object') {
        return '';
    }
    const value = record[field];
    return typeof value === 'string' ? value : '';
}

function objectValue(record, field) {
    if (!record || typeof record !== 'object') {
        return null;
    }
    const value = record[field];
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

function findCaseRun(caseRuns, selectedCaseRunId) {
    const runs = asArray(caseRuns);
    if (selectedCaseRunId.length > 0) {
        const found = runs.find((item) => stringValue(item, 'case_run_id') === selectedCaseRunId);
        if (found) {
            return found;
        }
    }
    return runs.length > 0 ? runs[0] : null;
}

function messageContent(message) {
    if (!message || typeof message !== 'object') {
        return '';
    }
    const content = message.content;
    if (typeof content === 'string') {
        return content;
    }
    if (content === null || content === undefined) {
        return '';
    }
    return JSON.stringify(content);
}

function eventSequence(event) {
    if (!event || typeof event !== 'object') {
        return '·';
    }
    const value = event.sequence;
    if (typeof value === 'number' || typeof value === 'string') {
        return value;
    }
    return '·';
}

function isScalar(value) {
    return value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
}

function scalarText(value) {
    if (value === null) {
        return 'null';
    }
    if (typeof value === 'string' && value.length === 0) {
        return '""';
    }
    return String(value);
}

function prettyJson(value) {
    return JSON.stringify(value, null, 2);
}

function eventTone(eventType, payload) {
    if (eventType.includes('failed') || eventType.includes('error') || eventType.includes('cancelled')) {
        return 'danger';
    }
    if (payload !== null && stringValue(payload, 'error').length > 0) {
        return 'danger';
    }
    if (eventType.includes('score') || eventType.includes('checker')) {
        return 'score';
    }
    if (eventType.includes('finished') || eventType.includes('passed')) {
        return 'success';
    }
    if (eventType.includes('started') || eventType.includes('created')) {
        return 'info';
    }
    if (eventType.includes('message')) {
        return 'message';
    }
    return 'neutral';
}

function eventIcon(eventType) {
    if (eventType.includes('failed') || eventType.includes('error') || eventType.includes('cancelled')) {
        return 'alert-triangle';
    }
    if (eventType.includes('score') || eventType.includes('checker')) {
        return 'badge-check';
    }
    if (eventType.includes('finished') || eventType.includes('passed')) {
        return 'check-circle';
    }
    if (eventType.includes('started') || eventType.includes('created')) {
        return 'play';
    }
    if (eventType.includes('message')) {
        return 'messages-square';
    }
    return 'circle-dot';
}

export class FlowsEvaluationTranscript extends PlatformElement {
    static properties = {
        run: { type: Object },
        caseRuns: { type: Array },
        events: { type: Array },
        selectedCaseRunId: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                min-width: 0;
                min-height: 0;
                color: var(--text-primary);
            }

            .panel {
                flex: 1;
                min-width: 0;
                min-height: 0;
                display: flex;
                flex-direction: column;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }

            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: linear-gradient(180deg, color-mix(in srgb, var(--glass-solid-medium), transparent 8%), transparent);
            }

            .title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .title platform-help-hint {
                flex: 0 0 auto;
            }

            .run-state {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 5px 9px;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            .message {
                display: flex;
                gap: var(--space-3);
                max-width: 860px;
            }

            .message[data-role="user"] {
                align-self: flex-end;
                flex-direction: row-reverse;
            }

            .avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex: 0 0 auto;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-tertiary);
            }

            .bubble {
                min-width: 0;
                padding: var(--space-3);
                border-radius: 18px;
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-solid-medium), transparent 6%);
                box-shadow: 0 8px 28px color-mix(in srgb, var(--shadow-color), transparent 82%);
            }

            .message[data-role="user"] .bubble {
                background: color-mix(in srgb, var(--accent), transparent 84%);
                border-color: color-mix(in srgb, var(--accent), transparent 58%);
            }

            .role {
                display: block;
                margin-bottom: 4px;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .content {
                color: var(--text-primary);
                white-space: pre-wrap;
                line-height: 1.45;
                overflow-wrap: anywhere;
            }

            .events {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding-top: var(--space-2);
                border-top: 1px solid var(--border-subtle);
            }

            .event-empty {
                padding: var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .event-card {
                display: grid;
                grid-template-columns: 28px minmax(0, 1fr);
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--glass-solid-medium), transparent 12%);
                box-shadow: 0 10px 34px color-mix(in srgb, var(--shadow-color), transparent 88%);
            }

            .event-card[data-tone="danger"] {
                border-color: color-mix(in srgb, var(--error), transparent 44%);
                background: color-mix(in srgb, var(--error), transparent 92%);
            }

            .event-card[data-tone="success"] {
                border-color: color-mix(in srgb, var(--success), transparent 56%);
                background: color-mix(in srgb, var(--success), transparent 94%);
            }

            .event-card[data-tone="score"] {
                border-color: color-mix(in srgb, var(--accent), transparent 58%);
                background: color-mix(in srgb, var(--accent), transparent 94%);
            }

            .event-card[data-tone="info"],
            .event-card[data-tone="message"] {
                border-color: color-mix(in srgb, var(--info), transparent 60%);
                background: color-mix(in srgb, var(--info), transparent 95%);
            }

            .event-marker {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-tertiary);
            }

            .event-card[data-tone="danger"] .event-marker {
                color: var(--error);
                border-color: color-mix(in srgb, var(--error), transparent 46%);
                background: color-mix(in srgb, var(--error), transparent 88%);
            }

            .event-card[data-tone="success"] .event-marker {
                color: var(--success);
                border-color: color-mix(in srgb, var(--success), transparent 56%);
                background: color-mix(in srgb, var(--success), transparent 90%);
            }

            .event-card[data-tone="score"] .event-marker {
                color: var(--accent);
            }

            .event-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .event-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                min-width: 0;
            }

            .event-type {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                overflow-wrap: anywhere;
            }

            .event-sequence {
                flex: 0 0 auto;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-variant-numeric: tabular-nums;
            }

            .error-box {
                display: flex;
                flex-direction: column;
                gap: 6px;
                padding: var(--space-3);
                border: 1px solid color-mix(in srgb, var(--error), transparent 52%);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--error), transparent 90%);
            }

            .error-label {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                color: var(--error);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .error-message {
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.45;
                overflow-wrap: anywhere;
            }

            .payload-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: var(--space-2);
            }

            .payload-row {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 5px;
                padding: 9px 10px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--surface-1), transparent 8%);
            }

            .payload-row-wide {
                grid-column: 1 / -1;
            }

            .payload-key {
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
                overflow-wrap: anywhere;
            }

            .payload-value {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.45;
                overflow-wrap: anywhere;
            }

            .payload-json {
                margin: 0;
                max-height: 240px;
                overflow: auto;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                color: var(--text-secondary);
                font-size: 12px;
                line-height: 1.45;
                font-family: var(--font-mono);
            }

            .payload-empty {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .empty {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                text-align: center;
                padding: var(--space-6);
            }
        `,
    ];

    constructor() {
        super();
        this.run = null;
        this.caseRuns = [];
        this.events = [];
        this.selectedCaseRunId = '';
    }

    render() {
        const runState = stringValue(this.run, 'state');
        const caseRun = findCaseRun(this.caseRuns, this.selectedCaseRunId);
        const caseRunId = stringValue(caseRun, 'case_run_id');
        const dialog = asArray(caseRun && caseRun.dialog);
        const events = asArray(this.events).filter((event) => {
            const eventCaseRunId = stringValue(event, 'case_run_id');
            return caseRunId.length === 0 || eventCaseRunId.length === 0 || eventCaseRunId === caseRunId;
        });
        return html`
            <section class="panel">
                <div class="head">
                    <div class="title">
                        <platform-icon name="messages-square" size="16"></platform-icon>
                        ${this.t('evaluation.transcript.title')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.transcript')}
                            .label=${this.t('evaluation.hints.transcript_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                    ${runState.length > 0 ? html`<span class="run-state"><platform-icon name="activity" size="13"></platform-icon>${runState}</span>` : ''}
                </div>
                <div class="body">
                    ${caseRun ? html`
                        ${dialog.length > 0 ? dialog.map((message) => this._renderMessage(message)) : this._renderSyntheticDialog(caseRun)}
                        <div class="events">
                            ${events.length > 0 ? events.map((event) => this._renderEvent(event)) : html`<div class="event-empty">${this.t('evaluation.transcript.no_events')}</div>`}
                        </div>
                    ` : html`<div class="empty">${this.t('evaluation.transcript.empty')}</div>`}
                </div>
            </section>
        `;
    }

    _renderSyntheticDialog(caseRun) {
        const error = stringValue(caseRun, 'error');
        const feedback = stringValue(caseRun, 'judge_feedback');
        if (error.length > 0) {
            return this._renderMessage({ role: 'system', content: error });
        }
        if (feedback.length > 0) {
            return this._renderMessage({ role: 'judge', content: feedback });
        }
        return html`<div class="empty">${this.t('evaluation.transcript.no_dialog')}</div>`;
    }

    _renderMessage(message) {
        const role = stringValue(message, 'role');
        const visualRole = role.length > 0 ? role : 'assistant';
        const icon = visualRole === 'user' ? 'user' : 'bot';
        return html`
            <article class="message" data-role=${visualRole}>
                <span class="avatar"><platform-icon name=${icon} size="14"></platform-icon></span>
                <div class="bubble">
                    <span class="role">${visualRole}</span>
                    <div class="content">${messageContent(message)}</div>
                </div>
            </article>
        `;
    }

    _renderEvent(event) {
        const eventType = stringValue(event, 'event_type');
        const payload = objectValue(event, 'payload');
        const tone = eventTone(eventType, payload);
        return html`
            <article class="event-card" data-tone=${tone}>
                <span class="event-marker"><platform-icon name=${eventIcon(eventType)} size="14"></platform-icon></span>
                <div class="event-main">
                    <div class="event-header">
                        <span class="event-type">${eventType}</span>
                        <span class="event-sequence">#${eventSequence(event)}</span>
                    </div>
                    ${this._renderPayload(eventType, payload)}
                </div>
            </article>
        `;
    }

    _renderPayload(eventType, payload) {
        if (payload === null) {
            return html`<div class="payload-empty">${this.t('evaluation.transcript.payload_empty')}</div>`;
        }
        const error = stringValue(payload, 'error');
        const isError = eventTone(eventType, payload) === 'danger' && error.length > 0;
        const entries = Object.entries(payload).filter(([key]) => key !== 'error' || !isError);
        return html`
            ${isError ? html`
                <div class="error-box">
                    <span class="error-label"><platform-icon name="alert-triangle" size="13"></platform-icon>${this.t('evaluation.transcript.error_title')}</span>
                    <div class="error-message">${error}</div>
                </div>
            ` : ''}
            ${entries.length > 0 ? this._renderPayloadGrid(entries) : ''}
        `;
    }

    _renderPayloadGrid(entries) {
        return html`
            <div class="payload-grid">
                ${entries.map(([key, value]) => this._renderPayloadItem(key, value))}
            </div>
        `;
    }

    _renderPayloadItem(key, value) {
        const isWide = !isScalar(value);
        const rowClass = isWide ? 'payload-row payload-row-wide' : 'payload-row';
        return html`
            <div class=${rowClass}>
                <span class="payload-key">${key}</span>
                ${isWide
                    ? html`<pre class="payload-json">${prettyJson(value)}</pre>`
                    : html`<span class="payload-value">${scalarText(value)}</span>`}
            </div>
        `;
    }
}

customElements.define('flows-evaluation-transcript', FlowsEvaluationTranscript);
