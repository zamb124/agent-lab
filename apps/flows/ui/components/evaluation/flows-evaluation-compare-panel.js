import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-segmented-control.js';

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

function scoreText(value) {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '·';
}

export class FlowsEvaluationComparePanel extends PlatformElement {
    static properties = {
        runs: { type: Array },
        selectedRunId: { type: String },
        selectedCompareRunId: { type: String },
        compareResult: { type: Object },
        busy: { type: Boolean },
    };

    static styles = [
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
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .title platform-help-hint {
                flex: 0 0 auto;
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

            .run-strip {
                display: flex;
                gap: var(--space-2);
                overflow-x: auto;
                padding-bottom: var(--space-1);
            }

            article.run-chip {
                margin: 0;
            }

            .run-chip {
                min-height: 34px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                white-space: nowrap;
            }

            .run-chip:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .run-chip[data-active="true"] {
                color: var(--text-primary);
                border-color: color-mix(in srgb, var(--accent), transparent 54%);
                background: color-mix(in srgb, var(--accent), transparent 86%);
            }

            .action-row,
            .judge-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }

            .judge-row platform-segmented-control {
                flex: 1 1 100%;
                min-width: 0;
            }

            .diff-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .diff-row {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--bg-surface), transparent 16%);
            }

            .diff-title {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-weight: var(--font-medium);
            }

            .diff-meta {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .delta {
                min-width: 72px;
                text-align: right;
                font-weight: var(--font-semibold);
            }

            .delta[data-tone="positive"] { color: var(--success); }
            .delta[data-tone="negative"] { color: var(--error); }
            .delta[data-tone="neutral"] { color: var(--text-tertiary); }

            .empty {
                min-height: 180px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                text-align: center;
            }
        `,
    ];

    constructor() {
        super();
        this.runs = [];
        this.selectedRunId = '';
        this.selectedCompareRunId = '';
        this.compareResult = null;
        this.busy = false;
    }

    _onSelectableKeydown(event, handler) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    _selectCompareRun(runId) {
        this.emit('compare-run-select', { run_id: runId });
    }

    _compare() {
        this.emit('compare-request', null);
    }

    _setBaseline() {
        this.emit('baseline-set-request', null);
    }

    _pairwise(mode, preference) {
        this.emit('pairwise-judge-request', { mode, preference });
    }

    _judgeItems(compareEnabled) {
        return [
            { value: 'left_wins', label: this.t('evaluation.compare.left_wins'), disabled: !compareEnabled },
            { value: 'tie', label: this.t('evaluation.compare.tie'), disabled: !compareEnabled },
            { value: 'right_wins', label: this.t('evaluation.compare.right_wins'), disabled: !compareEnabled },
            { value: 'llm_pairwise', label: this.t('evaluation.compare.llm_pairwise'), icon: 'sparkles', disabled: !compareEnabled },
        ];
    }

    _onJudgeChange(value) {
        if (value === 'left_wins') {
            this._pairwise('human', 'left');
            return;
        }
        if (value === 'right_wins') {
            this._pairwise('human', 'right');
            return;
        }
        if (value === 'llm_pairwise') {
            this._pairwise('llm', 'tie');
            return;
        }
        if (value === 'tie') {
            this._pairwise('human', 'tie');
        }
    }

    render() {
        const runs = asArray(this.runs);
        const compareEnabled = this.selectedRunId.length > 0 && this.selectedCompareRunId.length > 0 && this.selectedRunId !== this.selectedCompareRunId;
        const cases = this._compareCases();
        return html`
            <section class="content-panel">
                <div class="content-panel-head">
                    <div class="title">
                        <platform-icon name="git-compare" size="16"></platform-icon>
                        ${this.t('evaluation.compare.title')}
                        <platform-help-hint
                            .text=${this.t('evaluation.hints.compare')}
                            .label=${this.t('evaluation.hints.compare_label')}
                            placement="bottom"
                        ></platform-help-hint>
                    </div>
                </div>
                <div class="body">
                    <div class="run-strip">
                        ${runs.length > 0 ? runs.map((run) => this._renderRunChip(run)) : html`<span class="empty">${this.t('evaluation.compare.no_runs')}</span>`}
                    </div>
                    <div class="action-row">
                        <platform-button variant="primary" density="compact" ?disabled=${!compareEnabled || this.busy} @click=${this._compare}>
                            <platform-icon name="git-compare" size="14"></platform-icon>
                            ${this.t('evaluation.compare.compare')}
                        </platform-button>
                        <platform-button variant="secondary" density="compact" ?disabled=${this.selectedRunId.length === 0 || this.busy} @click=${this._setBaseline}>
                            <platform-icon name="flag" size="14"></platform-icon>
                            ${this.t('evaluation.compare.set_baseline')}
                        </platform-button>
                    </div>
                    <div class="judge-row">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .items=${this._judgeItems(compareEnabled)}
                            aria-label=${this.t('evaluation.compare.judge_aria')}
                            @change=${(event) => this._onJudgeChange(event.detail.value)}
                        ></platform-segmented-control>
                    </div>
                    <div class="diff-list">
                        ${cases.length > 0 ? cases.map((item) => this._renderDiff(item)) : html`<div class="content-panel-empty">${this.t('evaluation.compare.empty')}</div>`}
                    </div>
                </div>
            </section>
        `;
    }

    _renderRunChip(run) {
        const runId = stringValue(run, 'run_id');
        const state = stringValue(run, 'state');
        const active = runId === this.selectedCompareRunId;
        return html`
            <article
                class="run-chip"
                tabindex="0"
                role="button"
                data-active=${active ? 'true' : 'false'}
                @click=${() => this._selectCompareRun(runId)}
                @keydown=${(event) => this._onSelectableKeydown(event, () => this._selectCompareRun(runId))}
            >
                <platform-icon name="history" size="14"></platform-icon>
                ${runId.slice(0, 8)} · ${state}
            </article>
        `;
    }

    _compareCases() {
        if (!this.compareResult || typeof this.compareResult !== 'object') {
            return [];
        }
        return asArray(this.compareResult.cases);
    }

    _renderDiff(item) {
        const left = item && typeof item === 'object' ? item.left : null;
        const right = item && typeof item === 'object' ? item.right : null;
        const caseId = stringValue(item, 'case_id');
        const leftScore = numberOrNull(left, 'total_score');
        const rightScore = numberOrNull(right, 'total_score');
        const delta = numberOrNull(item, 'score_delta');
        let tone = 'neutral';
        if (typeof delta === 'number' && delta > 0) {
            tone = 'positive';
        }
        if (typeof delta === 'number' && delta < 0) {
            tone = 'negative';
        }
        return html`
            <div class="diff-row">
                <div>
                    <div class="diff-title">${caseId}</div>
                    <div class="diff-meta">${scoreText(leftScore)} → ${scoreText(rightScore)}</div>
                </div>
                <div class="delta" data-tone=${tone}>${scoreText(delta)}</div>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-compare-panel', FlowsEvaluationComparePanel);
