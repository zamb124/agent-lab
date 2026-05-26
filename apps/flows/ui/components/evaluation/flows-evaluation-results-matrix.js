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

function numberOrNull(record, field) {
    if (!record || typeof record !== 'object') {
        return null;
    }
    const value = record[field];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatScore(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        return '·';
    }
    return value.toFixed(1);
}

function stateTone(state) {
    if (state === 'passed' || state === 'completed') {
        return 'passed';
    }
    if (state === 'failed' || state === 'error' || state === 'cancelled' || state === 'canceled') {
        return 'failed';
    }
    if (state === 'running' || state === 'queued') {
        return 'running';
    }
    return 'idle';
}

function aggregateCellsTone(cells) {
    const tones = asArray(cells).map((cell) => stateTone(stringValue(cell, 'state')));
    if (tones.includes('failed')) {
        return 'failed';
    }
    if (tones.includes('running')) {
        return 'running';
    }
    if (tones.includes('passed')) {
        return 'passed';
    }
    return 'idle';
}

function groupCells(cells) {
    const map = new Map();
    for (const cell of asArray(cells)) {
        const runId = stringValue(cell, 'run_id');
        const caseId = stringValue(cell, 'case_id');
        if (runId.length === 0 || caseId.length === 0) {
            continue;
        }
        const key = `${runId}::${caseId}`;
        const existing = map.get(key);
        if (Array.isArray(existing)) {
            existing.push(cell);
        } else {
            map.set(key, [cell]);
        }
    }
    return map;
}

export class FlowsEvaluationResultsMatrix extends PlatformElement {
    static properties = {
        matrix: { type: Object },
        selectedRunId: { type: String },
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
                background:
                    linear-gradient(180deg, color-mix(in srgb, var(--glass-solid-medium), transparent 12%), transparent 62%),
                    var(--glass-solid-subtle);
                overflow: hidden;
            }

            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
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

            .legend {
                display: inline-flex;
                align-items: center;
                gap: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .legend span {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }

            .dot {
                display: inline-block;
                flex: 0 0 auto;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--border-strong);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--border-strong), transparent 84%);
            }

            .dot[data-tone="passed"] {
                background: var(--success);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--success), transparent 84%);
            }

            .dot[data-tone="failed"] {
                background: var(--error);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--error), transparent 82%);
            }

            .dot[data-tone="running"] {
                background: var(--warning);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning), transparent 84%);
            }

            .matrix-wrap {
                flex: 1;
                min-height: 0;
                overflow: auto;
            }

            table {
                width: 100%;
                min-width: 760px;
                border-collapse: separate;
                border-spacing: 0;
                font-size: var(--text-sm);
            }

            th,
            td {
                border-bottom: 1px solid color-mix(in srgb, var(--border-subtle), transparent 18%);
                border-right: 1px solid color-mix(in srgb, var(--border-subtle), transparent 32%);
                padding: 0;
                vertical-align: middle;
            }

            th {
                position: sticky;
                top: 0;
                z-index: 2;
                height: 52px;
                background: color-mix(in srgb, var(--bg-surface), transparent 5%);
                color: var(--text-tertiary);
                text-align: left;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }

            th:first-child,
            td:first-child {
                position: sticky;
                left: 0;
                z-index: 1;
                background: color-mix(in srgb, var(--bg-surface), transparent 4%);
                border-right: 1px solid var(--border-subtle);
            }

            th:first-child {
                z-index: 3;
            }

            .case-cell,
            .run-head,
            .cell-button {
                min-height: 52px;
                box-sizing: border-box;
            }

            .case-cell {
                width: 260px;
                min-width: 260px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: 2px;
                padding: 9px var(--space-3);
            }

            .case-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .case-meta,
            .run-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .run-meta {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .run-meta-text {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .run-head {
                width: 128px;
                min-width: 128px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: 2px;
                padding: 8px var(--space-2);
                border: 0;
                background: transparent;
                color: inherit;
                text-align: left;
                cursor: pointer;
            }

            .run-head[data-active="true"] {
                color: var(--accent);
            }

            .cell-button {
                width: 100%;
                min-width: 128px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: 4px;
                padding: 7px var(--space-2);
                border: 0;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .cell-button:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .cell-button[data-tone="passed"] {
                background: color-mix(in srgb, var(--success), transparent 95%);
            }

            .cell-button[data-tone="failed"] {
                background: color-mix(in srgb, var(--error), transparent 92%);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--error), transparent 70%) inset;
            }

            .cell-button[data-tone="running"] {
                background: color-mix(in srgb, var(--warning), transparent 93%);
            }

            .cell-button[data-tone="failed"]:hover {
                background: color-mix(in srgb, var(--error), transparent 88%);
            }

            .cell-button[data-active="true"] {
                background: color-mix(in srgb, var(--accent), transparent 86%);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent), transparent 70%) inset;
            }

            .cell-button[data-active="true"][data-tone="failed"] {
                background: color-mix(in srgb, var(--error), transparent 88%);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--error), transparent 48%) inset;
            }

            .score-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .score {
                font-size: var(--text-base);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }

            .score[data-tone="failed"] {
                color: var(--error);
            }

            .score[data-tone="running"] {
                color: var(--warning);
            }

            .score[data-tone="passed"] {
                color: var(--success);
            }

            .trials {
                display: inline-flex;
                gap: 3px;
                min-width: 0;
            }

            .duration {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .empty {
                flex: 1;
                min-height: 220px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .empty-workbench {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                padding: var(--space-5);
            }

            .empty-stack {
                width: min(620px, 100%);
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
            }

            .empty-stat {
                min-height: 108px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--bg-surface), transparent 10%);
            }

            .empty-stat platform-icon {
                color: var(--accent);
            }

            .empty-stat-value {
                color: var(--text-primary);
                font-size: 24px;
                font-weight: var(--font-semibold);
                line-height: 1;
            }

            .empty-stat-label {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .empty-flow {
                width: min(620px, 100%);
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-2);
            }

            .empty-step {
                min-height: 42px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                padding: 0 var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }

            .empty-step[data-active="true"] {
                color: var(--accent);
                border-color: color-mix(in srgb, var(--accent), transparent 58%);
                background: color-mix(in srgb, var(--accent), transparent 91%);
            }

            .cockpit {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: minmax(220px, 0.95fr) minmax(320px, 1.4fr);
                gap: var(--space-4);
                padding: var(--space-5);
                box-sizing: border-box;
            }

            .cockpit-copy {
                min-width: 0;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: var(--space-3);
            }

            .eyebrow {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                width: fit-content;
                padding: 6px 10px;
                border-radius: var(--radius-full);
                border: 1px solid color-mix(in srgb, var(--accent), transparent 64%);
                color: var(--accent);
                background: color-mix(in srgb, var(--accent), transparent 91%);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }

            .cockpit-title {
                max-width: 440px;
                margin: 0;
                color: var(--text-primary);
                font-size: 30px;
                line-height: 1.06;
                font-weight: var(--font-semibold);
                letter-spacing: 0;
            }

            .cockpit-sub {
                max-width: 460px;
                margin: 0;
                color: var(--text-tertiary);
                line-height: 1.5;
                font-size: var(--text-sm);
            }

            .pipeline {
                min-width: 0;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
                align-content: center;
            }

            .pipeline-card {
                min-height: 112px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--border-subtle);
                background:
                    linear-gradient(180deg, color-mix(in srgb, var(--glass-solid-strong), transparent 10%), color-mix(in srgb, var(--bg-surface), transparent 8%));
                box-shadow: 0 12px 34px color-mix(in srgb, var(--shadow-color), transparent 88%);
            }

            .pipeline-icon {
                width: 34px;
                height: 34px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 10px;
                color: var(--text-primary);
                background: color-mix(in srgb, var(--accent), transparent 86%);
            }

            .pipeline-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }

            .pipeline-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            @media (max-width: 900px) {
                .cockpit {
                    grid-template-columns: 1fr;
                }

                .empty-flow {
                    grid-template-columns: 1fr 1fr;
                }

                .cockpit-title {
                    font-size: 24px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.matrix = null;
        this.selectedRunId = '';
        this.selectedCaseRunId = '';
    }

    _selectRun(runId) {
        this.emit('run-select', { run_id: runId });
    }

    _selectCaseRun(cell) {
        const caseRunId = stringValue(cell, 'case_run_id');
        if (caseRunId.length === 0) {
            return;
        }
        this.emit('case-run-select', { case_run_id: caseRunId, run_id: stringValue(cell, 'run_id') });
    }

    render() {
        const matrix = this.matrix && typeof this.matrix === 'object' ? this.matrix : null;
        if (matrix === null) {
            return html`
                <section class="panel">
                    <div class="cockpit">
                        <div class="cockpit-copy">
                            <span class="eyebrow">
                                <platform-icon name="ai" size="14"></platform-icon>
                                ${this.t('evaluation.matrix.empty')}
                            </span>
                            <h2 class="cockpit-title">${this.t('evaluation.matrix.empty_title')}</h2>
                            <p class="cockpit-sub">${this.t('evaluation.matrix.empty_subtitle')}</p>
                        </div>
                        <div class="pipeline">
                            ${this._renderPipelineCard('database', this.t('evaluation.matrix.empty_suite'), 'Dataset')}
                            ${this._renderPipelineCard('checklist', this.t('evaluation.matrix.empty_cases'), 'Test suite')}
                            ${this._renderPipelineCard('play', this.t('evaluation.matrix.empty_runs'), 'Experiment')}
                            ${this._renderPipelineCard('check-square', this.t('evaluation.matrix.empty_judges'), 'Scorers')}
                        </div>
                    </div>
                </section>
            `;
        }
        const cases = asArray(matrix.cases);
        const runs = asArray(matrix.runs);
        const grouped = groupCells(matrix.cells);
        return html`
            <section class="panel">
                <div class="head">
                    <div class="title">
                        <platform-icon name="table" size="16"></platform-icon>
                        ${this.t('evaluation.matrix.title')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.matrix')}
                            .label=${this.t('evaluation.hints.matrix_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                    <div class="legend">
                        <span><i class="dot" data-tone="passed"></i>${this.t('evaluation.matrix.passed')}</span>
                        <span><i class="dot" data-tone="failed"></i>${this.t('evaluation.matrix.failed')}</span>
                        <span><i class="dot" data-tone="running"></i>${this.t('evaluation.matrix.running')}</span>
                    </div>
                </div>
                ${cases.length > 0 && runs.length > 0 ? html`
                    <div class="matrix-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th><div class="case-cell">${this.t('evaluation.matrix.case')}</div></th>
                                    ${runs.map((run) => this._renderRunHead(run))}
                                </tr>
                            </thead>
                            <tbody>
                                ${cases.map((testCase) => this._renderCaseRow(testCase, runs, grouped))}
                            </tbody>
                        </table>
                    </div>
                ` : this._renderNoRuns(cases.length, runs.length)}
            </section>
        `;
    }

    _renderNoRuns(caseCount, runCount) {
        return html`
            <div class="empty-workbench">
                <div class="empty-stack">
                    <div class="empty-stat">
                        <platform-icon name="checklist" size="18"></platform-icon>
                        <span class="empty-stat-value">${caseCount}</span>
                        <span class="empty-stat-label">${this.t('evaluation.matrix.empty_cases')}</span>
                    </div>
                    <div class="empty-stat">
                        <platform-icon name="play" size="18"></platform-icon>
                        <span class="empty-stat-value">${runCount}</span>
                        <span class="empty-stat-label">${this.t('evaluation.matrix.empty_runs')}</span>
                    </div>
                    <div class="empty-stat">
                        <platform-icon name="chart" size="18"></platform-icon>
                        <span class="empty-stat-value">0%</span>
                        <span class="empty-stat-label">${this.t('evaluation.matrix.score')}</span>
                    </div>
                </div>
                <div class="empty-flow">
                    <span class="empty-step" data-active="true"><platform-icon name="database" size="13"></platform-icon>${this.t('evaluation.matrix.empty_suite')}</span>
                    <span class="empty-step" data-active=${caseCount > 0 ? 'true' : 'false'}><platform-icon name="checklist" size="13"></platform-icon>${this.t('evaluation.matrix.empty_cases')}</span>
                    <span class="empty-step" data-active=${runCount > 0 ? 'true' : 'false'}><platform-icon name="play" size="13"></platform-icon>${this.t('evaluation.matrix.empty_runs')}</span>
                    <span class="empty-step"><platform-icon name="trace-timeline" size="13"></platform-icon>${this.t('evaluation.matrix.empty_results')}</span>
                </div>
            </div>
        `;
    }

    _renderPipelineCard(icon, title, meta) {
        return html`
            <div class="pipeline-card">
                <span class="pipeline-icon"><platform-icon name=${icon} size="17"></platform-icon></span>
                <div>
                    <div class="pipeline-title">${title}</div>
                    <div class="pipeline-meta">${meta}</div>
                </div>
            </div>
        `;
    }

    _renderRunHead(run) {
        const runId = stringValue(run, 'run_id');
        const state = stringValue(run, 'state');
        const tone = stateTone(state);
        const averageScore = numberOrNull(run, 'average_score');
        const active = runId === this.selectedRunId;
        return html`
            <th>
                <button class="run-head" type="button" data-active=${active ? 'true' : 'false'} @click=${() => this._selectRun(runId)}>
                    <span class="case-name">${runId.slice(0, 8)}</span>
                    <span class="run-meta">
                        <i class="dot" data-tone=${tone}></i>
                        <span class="run-meta-text">${state} · ${formatScore(averageScore)}</span>
                    </span>
                </button>
            </th>
        `;
    }

    _renderCaseRow(testCase, runs, grouped) {
        const caseId = stringValue(testCase, 'case_id');
        const name = stringValue(testCase, 'name');
        const tags = asArray(testCase.tags);
        const meta = tags.length > 0 ? tags.join(', ') : this.t('evaluation.matrix.no_tags');
        return html`
            <tr>
                <td>
                    <div class="case-cell">
                        <span class="case-name">${name}</span>
                        <span class="case-meta">${meta}</span>
                    </div>
                </td>
                ${runs.map((run) => {
                    const runId = stringValue(run, 'run_id');
                    const key = `${runId}::${caseId}`;
                    const cells = grouped.get(key);
                    return this._renderMatrixCell(Array.isArray(cells) ? cells : []);
                })}
            </tr>
        `;
    }

    _renderMatrixCell(cells) {
        if (cells.length === 0) {
            return html`<td><div class="cell-button"><span class="duration">·</span></div></td>`;
        }
        const primary = cells[0];
        const score = numberOrNull(primary, 'total_score');
        const duration = numberOrNull(primary, 'duration_ms');
        const active = stringValue(primary, 'case_run_id') === this.selectedCaseRunId;
        const tone = aggregateCellsTone(cells);
        return html`
            <td>
                <button class="cell-button" type="button" data-active=${active ? 'true' : 'false'} data-tone=${tone} @click=${() => this._selectCaseRun(primary)}>
                    <span class="score-row">
                        <span class="score" data-tone=${tone}>${formatScore(score)}</span>
                        <span class="trials">${cells.map((cell) => html`<i class="dot" data-tone=${stateTone(stringValue(cell, 'state'))}></i>`)}</span>
                    </span>
                    <span class="duration">${duration === null ? this.t('evaluation.matrix.no_duration') : `${duration}ms`}</span>
                </button>
            </td>
        `;
    }
}

customElements.define('flows-evaluation-results-matrix', FlowsEvaluationResultsMatrix);
