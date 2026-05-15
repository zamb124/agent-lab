/**
 * Человекочитаемый просмотр span.attributes с raw JSON внизу.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import {
    buildSpanAttributeViewModel,
    isTracePlainObject,
    prettyTraceJsonText,
    traceScalarText,
} from '../utils/trace-attribute-view-model.js';

export class PlatformSpanAttributesViewer extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        span: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .trace-attrs {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                min-width: 0;
            }
            .summary-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: var(--space-2);
            }
            .fact,
            .metric {
                min-width: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                padding: var(--space-2);
            }
            .label {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.2;
                margin-bottom: 2px;
            }
            .value {
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.35;
                overflow-wrap: anywhere;
            }
            .value.mono {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }
            .metrics {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                gap: var(--space-2);
            }
            .section {
                min-width: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .section-title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .section-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                min-width: 0;
            }
            .field-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: var(--space-2);
            }
            .message-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .message {
                min-width: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--bg-primary);
                padding: var(--space-2);
            }
            .message-head {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-1);
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .badge {
                display: inline-flex;
                align-items: center;
                min-height: 18px;
                padding: 1px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                line-height: 1.2;
            }
            .badge.accent {
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                color: var(--accent);
            }
            .text-block,
            .json-block {
                margin: 0;
                padding: var(--space-3);
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
                background: var(--bg-primary);
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                line-height: 1.5;
                white-space: pre-wrap;
                overflow: auto;
                max-height: 320px;
                overflow-wrap: anywhere;
            }
            .text-block {
                font-family: inherit;
                font-size: var(--text-sm);
            }
            .subheading {
                margin: 0 0 var(--space-1);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .list {
                margin: 0;
                padding-left: var(--space-4);
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.45;
            }
            .kv {
                display: grid;
                grid-template-columns: max-content minmax(0, 1fr);
                gap: var(--space-1) var(--space-3);
                font-size: var(--text-sm);
            }
            .kv dt {
                color: var(--text-tertiary);
            }
            .kv dd {
                margin: 0;
                color: var(--text-primary);
                overflow-wrap: anywhere;
            }
            details.raw-details {
                min-width: 0;
            }
            details.raw-details summary {
                cursor: pointer;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                user-select: none;
            }
            .parse-error {
                color: var(--warning);
                font-size: var(--text-xs);
            }
            @media (max-width: 720px) {
                .summary-grid,
                .metrics,
                .field-grid {
                    grid-template-columns: 1fr;
                }
                .kv {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.span = null;
    }

    _label(key) {
        return this.t(`span_attributes.fields.${key}`);
    }

    _sectionTitle(key) {
        return this.t(`span_attributes.sections.${key}`);
    }

    _isMonoKey(key) {
        return key.endsWith('_id') || key === 'span_id' || key === 'trace_id' || key === 'task' || key === 'context';
    }

    _formatValue(key, value) {
        const durationKeys = new Set(['duration', 'llm_duration', 'tool_duration']);
        if (durationKeys.has(key)) {
            const num = Number(value);
            if (Number.isFinite(num)) {
                return `${Math.round(num)} ms`;
            }
        }
        const costKeys = new Set(['provider_cost', 'upstream_cost']);
        if (costKeys.has(key)) {
            const num = Number(value);
            if (Number.isFinite(num)) {
                return `$${num.toFixed(6)}`;
            }
        }
        return value;
    }

    _renderField(item, compact = false) {
        const key = typeof item.key === 'string' ? item.key : '';
        const value = this._formatValue(key, traceScalarText(item.value));
        return html`
            <div class=${compact ? 'metric' : 'fact'}>
                <div class="label">${this._label(key)}</div>
                <div class="value ${this._isMonoKey(key) ? 'mono' : ''}">${value}</div>
            </div>
        `;
    }

    _renderFieldGrid(fields) {
        if (!Array.isArray(fields) || fields.length === 0) {
            return nothing;
        }
        return html`<div class="field-grid">${fields.map((item) => this._renderField(item))}</div>`;
    }

    _renderJsonBlock(value) {
        const text = isTracePlainObject(value) || Array.isArray(value)
            ? JSON.stringify(value, null, 2)
            : traceScalarText(value);
        if (text.length === 0) {
            return nothing;
        }
        return html`<pre class="json-block">${text}</pre>`;
    }

    _renderParsedBlock(parsed, raw) {
        if (parsed && parsed.ok) {
            return this._renderJsonBlock(parsed.value);
        }
        const err = parsed && typeof parsed.error === 'string' ? parsed.error : '';
        const shouldShowError = err.length > 0 && err !== 'not_json' && err !== 'empty' && err !== 'not_string';
        const pretty = prettyTraceJsonText(raw);
        return html`
            ${shouldShowError ? html`<div class="parse-error">${this.t('span_attributes.parse_error')}: ${err}</div>` : nothing}
            ${pretty.length > 0 ? html`<pre class="json-block">${pretty}</pre>` : nothing}
        `;
    }

    _renderSection(titleKey, body) {
        return html`
            <section class="section">
                <div class="section-header">
                    <h3 class="section-title">${this._sectionTitle(titleKey)}</h3>
                </div>
                <div class="section-body">${body}</div>
            </section>
        `;
    }

    _renderMessages(messages) {
        if (!Array.isArray(messages) || messages.length === 0) {
            return nothing;
        }
        return html`
            <div>
                <div class="subheading">${this.t('span_attributes.messages')}</div>
                <div class="message-list">
                    ${messages.map((message) => html`
                        <article class="message">
                            <div class="message-head">
                                <span class="badge">${message.role.length > 0 ? message.role : this.t('span_attributes.message')}</span>
                                ${message.system ? html`<span class="badge accent">system</span>` : nothing}
                                ${message.id.length > 0 ? html`<span class="value mono">${message.id}</span>` : nothing}
                            </div>
                            <pre class="text-block">${message.text}</pre>
                        </article>
                    `)}
                </div>
            </div>
        `;
    }

    _renderPills(titleKey, items) {
        if (!Array.isArray(items) || items.length === 0) {
            return nothing;
        }
        return html`
            <div>
                <div class="subheading">${this.t(titleKey)}</div>
                <div class="chips">
                    ${items.map((item) => html`<span class="badge">${item}</span>`)}
                </div>
            </div>
        `;
    }

    _renderList(titleKey, items) {
        if (!Array.isArray(items) || items.length === 0) {
            return nothing;
        }
        return html`
            <div>
                <div class="subheading">${this.t(titleKey)}</div>
                <ul class="list">
                    ${items.map((item) => html`<li>${item}</li>`)}
                </ul>
            </div>
        `;
    }

    _renderStatistics(statistics) {
        if (!isTracePlainObject(statistics) || Object.keys(statistics).length === 0) {
            return nothing;
        }
        return html`
            <div>
                <div class="subheading">${this.t('span_attributes.statistics')}</div>
                <dl class="kv">
                    ${Object.entries(statistics).map(([key, value]) => html`
                        <dt>${key}</dt>
                        <dd>${traceScalarText(value)}</dd>
                    `)}
                </dl>
            </div>
        `;
    }

    _renderStructuredContent(response) {
        const structured = response.structuredContent;
        const hasSummary = structured.summary.length > 0;
        const hasParsedBlocks = hasSummary
            || structured.entities.length > 0
            || structured.highlights.length > 0
            || structured.keyEvents.length > 0
            || (isTracePlainObject(structured.statistics) && Object.keys(structured.statistics).length > 0);
        if (hasParsedBlocks) {
            return html`
                ${hasSummary ? html`
                    <div>
                        <div class="subheading">${this.t('span_attributes.summary')}</div>
                        <pre class="text-block">${structured.summary}</pre>
                    </div>
                ` : nothing}
                ${this._renderPills('span_attributes.entities', structured.entities)}
                ${this._renderList('span_attributes.highlights', structured.highlights)}
                ${this._renderList('span_attributes.key_events', structured.keyEvents)}
                ${this._renderStatistics(structured.statistics)}
            `;
        }
        if (structured.parsed.ok) {
            return this._renderJsonBlock(structured.parsed.value);
        }
        if (response.contentText.length > 0) {
            return html`<pre class="text-block">${response.contentText}</pre>`;
        }
        return nothing;
    }

    _renderLlmRequest(request) {
        if (request === null) {
            return nothing;
        }
        const body = request.parsed.ok
            ? html`
                ${this._renderMessages(request.messages)}
                ${Array.isArray(request.tools) && request.tools.length > 0
                    ? html`
                        <details class="raw-details">
                            <summary>${this.t('span_attributes.tools_count', { count: request.tools.length })}</summary>
                            ${this._renderJsonBlock(request.tools)}
                        </details>
                    `
                    : nothing}
                ${request.responseFormat !== undefined
                    ? html`
                        <details class="raw-details">
                            <summary>${this.t('span_attributes.response_format')}</summary>
                            ${this._renderJsonBlock(request.responseFormat)}
                        </details>
                    `
                    : nothing}
                <details class="raw-details">
                    <summary>${this.t('span_attributes.raw_field')}</summary>
                    <pre class="json-block">${request.prettyRaw}</pre>
                </details>
            `
            : this._renderParsedBlock(request.parsed, request.raw);
        return this._renderSection('llm_request', body);
    }

    _renderLlmResponse(response) {
        if (response === null) {
            return nothing;
        }
        const body = response.parsed.ok || response.recovered
            ? html`
                ${this._renderStructuredContent(response)}
                ${Array.isArray(response.toolCalls) && response.toolCalls.length > 0
                    ? html`
                        <details class="raw-details" open>
                            <summary>${this.t('span_attributes.tool_calls', { count: response.toolCalls.length })}</summary>
                            ${this._renderJsonBlock(response.toolCalls)}
                        </details>
                    `
                    : nothing}
                <details class="raw-details">
                    <summary>${this.t('span_attributes.raw_field')}</summary>
                    <pre class="json-block">${response.prettyRaw}</pre>
                </details>
            `
            : this._renderParsedBlock(response.parsed, response.raw);
        return this._renderSection('llm_response', body);
    }

    _renderTool(tool) {
        if (tool === null) {
            return nothing;
        }
        return this._renderSection('tool', html`
            ${this._renderFieldGrid(tool.fields)}
            ${tool.args.raw.length > 0 ? html`
                <div>
                    <div class="subheading">${this.t('span_attributes.arguments')}</div>
                    ${this._renderParsedBlock(tool.args.parsed, tool.args.raw)}
                </div>
            ` : nothing}
            ${tool.result.raw.length > 0 ? html`
                <div>
                    <div class="subheading">${this.t('span_attributes.result')}</div>
                    ${this._renderParsedBlock(tool.result.parsed, tool.result.raw)}
                </div>
            ` : nothing}
            ${tool.mcpPreview.length > 0 ? html`
                <div>
                    <div class="subheading">${this.t('span_attributes.mcp_preview')}</div>
                    <pre class="text-block">${tool.mcpPreview}</pre>
                </div>
            ` : nothing}
        `);
    }

    _renderPrompt(prompt) {
        if (prompt === null) {
            return nothing;
        }
        return this._renderSection('prompt', html`
            ${this._renderFieldGrid(prompt.fields)}
            ${prompt.variables.raw.length > 0 ? html`
                <div>
                    <div class="subheading">${this.t('span_attributes.variables')}</div>
                    ${this._renderParsedBlock(prompt.variables.parsed, prompt.variables.raw)}
                </div>
            ` : nothing}
        `);
    }

    _renderState(state) {
        if (state === null) {
            return nothing;
        }
        return this._renderSection('state', html`${this._renderParsedBlock(state.parsed, state.raw)}`);
    }

    _renderSimpleFieldSection(key, view) {
        if (view === null) {
            return nothing;
        }
        return this._renderSection(key, this._renderFieldGrid(view.fields));
    }

    _renderRaw(attrs) {
        return this._renderSection('raw', html`
            <details class="raw-details" open>
                <summary>${this.t('span_attributes.raw_attributes')}</summary>
                <pre class="json-block">${JSON.stringify(attrs, null, 2)}</pre>
            </details>
        `);
    }

    render() {
        const vm = buildSpanAttributeViewModel(this.span);
        return html`
            <div class="trace-attrs">
                ${vm.quickFacts.length > 0
                    ? html`<div class="summary-grid">${vm.quickFacts.map((item) => this._renderField(item))}</div>`
                    : nothing}
                ${vm.metrics.length > 0
                    ? html`<div class="metrics">${vm.metrics.map((item) => this._renderField(item, true))}</div>`
                    : nothing}
                ${this._renderSimpleFieldSection('error', vm.error)}
                ${this._renderSimpleFieldSection('interrupt', vm.interrupt)}
                ${this._renderLlmRequest(vm.llmRequest)}
                ${this._renderLlmResponse(vm.llmResponse)}
                ${this._renderTool(vm.tool)}
                ${this._renderPrompt(vm.prompt)}
                ${this._renderState(vm.state)}
                ${this._renderRaw(vm.attrs)}
            </div>
        `;
    }
}

customElements.define('platform-span-attributes-viewer', PlatformSpanAttributesViewer);
