import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-empty-state.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function asArray(value: unknown) {
    return Array.isArray(value) ? value : [];
}

function stringValue(record: any, field: any) {
    if (!record || typeof record !== 'object') {
        return '';
    }
    const value = record[field];
    return typeof value === 'string' ? value : '';
}

function numberOrNull(record: any, field: any) {
    if (!record || typeof record !== 'object') {
        return null;
    }
    const value = record[field];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function objectText(value: unknown) {
    if (value === null || value === undefined) {
        return '';
    }
    return formatJsonPretty(value);
}

export class FlowsEvaluationTracePanel extends PlatformElement {
    static override properties: PropertyDeclarations = {
        trace: { type: Object },
        caseRun: { type: Object },
        annotations: { type: Array },
        busy: { type: Boolean },
    }
    declare trace: Record<string, unknown> | null;
    declare caseRun: Record<string, unknown> | null;
    declare annotations: any[];
    declare busy: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        panelShellStyles,
        css`
            :host {
                display: flex;
                flex: 1;
                width: 100%;
                min-width: 0;
                min-height: 0;
                color: var(--text-primary);
            }

            .title {
                min-width: 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .title platform-help-hint {
                flex: 0 0 auto;
            }

            .trace-id {
                max-width: 220px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }

            .body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-4);
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-4);
            }

            .section {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .section.full {
                grid-column: 1 / -1;
            }

            .section-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .span-list,
            .annotation-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .span-row,
            .annotation-row,
            .kv {
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--bg-surface), transparent 16%);
                padding: var(--space-3);
            }

            .span-row {
                display: grid;
                grid-template-columns: auto 1fr auto;
                gap: var(--space-2);
                align-items: center;
            }

            .span-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .span-name {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-weight: var(--font-medium);
            }

            .span-meta,
            .annotation-meta {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .duration {
                color: var(--text-secondary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }

            pre {
                margin: 0;
                min-height: 140px;
                max-height: 320px;
                overflow: auto;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                color: var(--text-secondary);
                font: 12px/1.45 var(--font-mono);
            }

            .empty {
                min-height: 180px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                text-align: center;
                grid-column: 1 / -1;
            }

            @media (max-width: 920px) {
                .body {
                    grid-template-columns: 1fr;
                }

                .section.full {
                    grid-column: auto;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.trace = null;
        this.caseRun = null;
        this.annotations = [];
        this.busy = false;
    }

    override render(): TemplateResult {
        const traceId = stringValue(this.caseRun, 'trace_id');
        const spans = this.trace && typeof this.trace === 'object' ? asArray(this.trace.spans) : [];
        const workflowRecords = this.trace && typeof this.trace === 'object' ? asArray(this.trace.workflow_records) : [];
        const stateHistory = this.trace && typeof this.trace === 'object' ? asArray(this.trace.state_history) : [];
        const caseRunId = stringValue(this.caseRun, 'case_run_id');
        return html`
            <section class="content-panel">
                <div class="content-panel-head">
                    <div class="title">
                        <platform-icon name="activity" size="16"></platform-icon>
                        ${this.t('evaluation.trace.title')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.trace')}
                            .label=${this.t('evaluation.hints.trace_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                    <span class="trace-id">${traceId}</span>
                </div>
                <div class="body">
                    ${caseRunId.length > 0 ? html`
                        <section class="section">
                            <div class="section-title"><platform-icon name="route" size="14"></platform-icon>${this.t('evaluation.trace.spans')}</div>
                            <div class="span-list">
                                ${spans.length > 0 ? spans.map((span) => this._renderSpan(span)) : html`<div class="kv">${this.t('evaluation.trace.no_spans')}</div>`}
                            </div>
                        </section>
                        <section class="section">
                            <div class="section-title"><platform-icon name="message-square-plus" size="14"></platform-icon>${this.t('evaluation.trace.annotations')}</div>
                            <div class="annotation-list">
                                ${asArray(this.annotations).length > 0 ? asArray(this.annotations).map((annotation) => this._renderAnnotation(annotation)) : html`<div class="kv">${this.t('evaluation.trace.no_annotations')}</div>`}
                            </div>
                        </section>
                        <section class="section full">
                            <div class="section-title"><platform-icon name="workflow" size="14"></platform-icon>${this.t('evaluation.trace.workflow_records')}</div>
                            <div class="kv"><pre>${objectText(workflowRecords)}</pre></div>
                        </section>
                        <section class="section full">
                            <div class="section-title"><platform-icon name="braces" size="14"></platform-icon>${this.t('evaluation.trace.state_history')}</div>
                            <div class="kv"><pre>${objectText(stateHistory)}</pre></div>
                        </section>
                    ` : html`<platform-empty-state icon="trace-timeline" title=${this.t('evaluation.trace.empty')}></platform-empty-state>`}
                </div>
            </section>
        `;
    }

    _renderSpan(span: any) {
        const duration = numberOrNull(span, 'duration_ms');
        return html`
            <div class="span-row">
                <platform-icon name="circle-dot" size="14"></platform-icon>
                <div class="span-main">
                    <span class="span-name">${stringValue(span, 'operation_name')}</span>
                    <span class="span-meta">${stringValue(span, 'service_name')} · ${stringValue(span, 'status')}</span>
                </div>
                <span class="duration">${duration === null ? '·' : `${duration}ms`}</span>
            </div>
        `;
    }

    _renderAnnotation(annotation: any) {
        return html`
            <div class="annotation-row">
                <div class="span-name">${stringValue(annotation, 'annotation_type')}</div>
                <div class="annotation-meta">${stringValue(annotation, 'created_at')}</div>
                <div>${stringValue(annotation, 'comment')}</div>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-trace-panel', FlowsEvaluationTracePanel);
