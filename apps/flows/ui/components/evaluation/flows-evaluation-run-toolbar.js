import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';

function stringValue(record, field) {
    if (!record || typeof record !== 'object') {
        return '';
    }
    const value = record[field];
    return typeof value === 'string' ? value : '';
}

function numberValue(record, field) {
    if (!record || typeof record !== 'object') {
        return 0;
    }
    const value = record[field];
    return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function isRunning(run) {
    const state = stringValue(run, 'state');
    return state === 'queued' || state === 'running';
}

const EVALUATION_DOCS_HREF = '/frontend/documentation/scenarios/flows/evaluation-lab/';

export class FlowsEvaluationRunToolbar extends PlatformElement {
    static properties = {
        branchId: { type: String },
        selectedSuite: { type: Object },
        selectedCase: { type: Object },
        selectedRun: { type: Object },
        caseTemplates: { type: Array },
        runScope: { type: String },
        trials: { type: Number },
        maxConcurrency: { type: Number },
        busy: { type: Boolean },
        _templatesOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                color: var(--text-primary);
            }

            .toolbar {
                display: grid;
                grid-template-columns: minmax(220px, 1fr) auto auto auto;
                align-items: center;
                gap: var(--space-2);
                min-height: 54px;
                padding: 7px;
                border: 1px solid color-mix(in srgb, var(--border-subtle), transparent 8%);
                border-radius: 22px;
                background: color-mix(in srgb, var(--bg-surface), transparent 4%);
                box-shadow: 0 10px 30px color-mix(in srgb, var(--shadow-color), transparent 88%);
            }

            .context {
                min-width: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-2);
            }

            .context > platform-icon {
                color: var(--accent);
            }

            .context-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .title {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }

            .sub {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .scope,
            .templates,
            .numbers,
            .actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }

            .templates {
                position: relative;
            }

            .segmented {
                display: inline-flex;
                gap: 2px;
                padding: 3px;
                border-radius: 18px;
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--bg-surface), transparent 18%);
            }

            .segmented button,
            .action-btn,
            .template-btn,
            .docs-link,
            .template-item,
            .step-btn {
                min-height: 34px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                border-radius: var(--radius-full);
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .segmented button {
                padding: 0 var(--space-3);
            }

            .segmented button:hover,
            .action-btn:hover,
            .template-btn:hover,
            .template-item:hover,
            .step-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .segmented button[data-active="true"] {
                color: var(--text-primary);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-subtle);
            }

            .numbers {
                padding: 0;
            }

            .stepper {
                height: 38px;
                min-width: 92px;
                display: grid;
                grid-template-columns: 1fr auto;
                align-items: center;
                gap: 6px;
                padding: 0 5px 0 10px;
                border-radius: 18px;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                box-sizing: border-box;
            }

            .step-copy {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 1px;
            }

            .step-label {
                color: var(--text-tertiary);
                font-size: 9px;
                line-height: 1;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .step-value {
                color: var(--text-primary);
                font-size: var(--text-base);
                line-height: 1.05;
                font-weight: var(--font-semibold);
            }

            .step-actions {
                display: grid;
                grid-template-rows: 1fr 1fr;
                gap: 2px;
            }

            .step-btn {
                width: 20px;
                min-height: 14px;
                height: 14px;
                padding: 0;
                border-radius: 7px;
                border-color: transparent;
                color: var(--text-tertiary);
            }

            .action-btn {
                padding: 0 var(--space-3);
                border-color: var(--border-subtle);
                background: var(--glass-solid-subtle);
            }

            .template-btn {
                padding: 0 var(--space-3);
                border-color: var(--border-subtle);
                background: var(--glass-solid-subtle);
            }

            .docs-link {
                padding: 0 var(--space-3);
                border-color: var(--border-subtle);
                background: var(--glass-solid-subtle);
                text-decoration: none;
            }

            .template-menu {
                position: absolute;
                right: 0;
                top: calc(100% + 8px);
                z-index: var(--z-dropdown);
                width: min(420px, calc(100vw - 32px));
                max-height: min(540px, calc(100vh - 128px));
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-strong);
                overflow: auto;
            }

            .template-menu-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-2);
                border-bottom: 1px solid var(--border-subtle);
            }

            .template-menu-title {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }

            .template-menu-title strong {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .template-menu-title span {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.35;
            }

            .template-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .template-section-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px var(--space-2);
                color: var(--text-tertiary);
                font-size: 10px;
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0;
            }

            .template-item {
                width: 100%;
                justify-content: flex-start;
                min-height: 48px;
                padding: var(--space-2);
                border-color: transparent;
                border-radius: var(--radius-lg);
                text-align: left;
            }

            .template-copy {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .template-name {
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .template-description {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.35;
            }

            .action-btn.primary {
                min-width: 104px;
                background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent), var(--success) 28%));
                color: var(--text-inverse);
                border-color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .action-btn.primary:hover {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
                box-shadow: var(--accent-glow);
            }

            .action-btn.danger {
                color: var(--error);
                border-color: color-mix(in srgb, var(--error), transparent 58%);
            }

            .action-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                box-shadow: none;
            }

            .template-btn:disabled,
            .template-item:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                box-shadow: none;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                height: 30px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
            }

            .status-pill[data-state="passed"] {
                color: var(--success);
                border-color: color-mix(in srgb, var(--success), transparent 58%);
            }

            .status-pill[data-state="failed"],
            .status-pill[data-state="cancelled"] {
                color: var(--error);
                border-color: color-mix(in srgb, var(--error), transparent 58%);
            }

            .status-pill[data-state="running"],
            .status-pill[data-state="queued"] {
                color: var(--warning);
                border-color: color-mix(in srgb, var(--warning), transparent 58%);
            }

            @media (max-width: 1180px) {
                .toolbar {
                    grid-template-columns: 1fr;
                    border-radius: var(--radius-xl);
                }

                .scope,
                .templates,
                .numbers,
                .actions {
                    flex-wrap: wrap;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.branchId = 'default';
        this.selectedSuite = null;
        this.selectedCase = null;
        this.selectedRun = null;
        this.caseTemplates = [];
        this.runScope = 'suite';
        this.trials = 1;
        this.maxConcurrency = 1;
        this.busy = false;
        this._templatesOpen = false;
    }

    _setScope(scope) {
        this.emit('scope-change', { scope });
    }

    _stepTrials(delta) {
        const next = Math.max(1, Math.trunc(this.trials) + delta);
        this.emit('options-change', { trials: next, max_concurrency: this.maxConcurrency });
    }

    _stepConcurrency(delta) {
        const next = Math.max(1, Math.trunc(this.maxConcurrency) + delta);
        this.emit('options-change', { trials: this.trials, max_concurrency: next });
    }

    _run() {
        this.emit('run-request', null);
    }

    _cancel() {
        const runId = stringValue(this.selectedRun, 'run_id');
        if (runId.length === 0) {
            return;
        }
        this.emit('cancel-request', { run_id: runId });
    }

    _reload() {
        this.emit('reload-request', null);
    }

    _toggleTemplates() {
        this._templatesOpen = !this._templatesOpen;
    }

    _closeTemplates() {
        this._templatesOpen = false;
    }

    _createFromTemplate(templateId) {
        this._templatesOpen = false;
        this.emit('template-create-request', { template_id: templateId });
    }

    render() {
        const suiteName = stringValue(this.selectedSuite, 'name');
        const caseName = stringValue(this.selectedCase, 'name');
        const runState = stringValue(this.selectedRun, 'state');
        const runActive = isRunning(this.selectedRun);
        const suiteDisabled = !this.selectedSuite || suiteName.length === 0;
        const caseScopeDisabled = !this.selectedCase || caseName.length === 0;
        const total = numberValue(this.selectedRun, 'total_cases');
        const passed = numberValue(this.selectedRun, 'passed_cases');
        const failed = numberValue(this.selectedRun, 'failed_cases');
        return html`
            <div class="toolbar">
                <div class="context">
                    <platform-icon name="science" size="18"></platform-icon>
                    <div class="context-main">
                        <div class="title">${suiteName.length > 0 ? suiteName : this.t('evaluation.toolbar.no_suite')}</div>
                        <div class="sub">
                            ${this.t('evaluation.toolbar.branch')} ${this.branchId}
                            ${caseName.length > 0 ? html` · ${caseName}` : ''}
                        </div>
                    </div>
                </div>

                <div class="templates">
                    <a
                        class="docs-link"
                        href=${EVALUATION_DOCS_HREF}
                        target="_blank"
                        rel="noopener noreferrer"
                        title=${this.t('evaluation.toolbar.docs_title')}
                    >
                        <platform-icon name="book-open" size="14"></platform-icon>
                        ${this.t('evaluation.toolbar.docs')}
                    </a>
                    <button class="template-btn" type="button" ?disabled=${suiteDisabled || this.busy} @click=${this._toggleTemplates}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('evaluation.templates.button')}
                    </button>
                    <platform-help-hint
                        .text=${this.t('evaluation.hints.templates')}
                        .label=${this.t('evaluation.hints.templates_label')}
                        placement="bottom"
                    ></platform-help-hint>
                    ${this._templatesOpen ? this._renderTemplatesMenu() : ''}
                </div>

                <div class="scope">
                    <div class="segmented">
                        <button type="button" data-active=${this.runScope === 'suite' ? 'true' : 'false'} @click=${() => this._setScope('suite')}>
                            <platform-icon name="database" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.scope_suite')}
                        </button>
                        <button
                            type="button"
                            data-active=${this.runScope === 'selected_case' ? 'true' : 'false'}
                            ?disabled=${caseScopeDisabled}
                            @click=${() => this._setScope('selected_case')}
                        >
                            <platform-icon name="target" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.scope_case')}
                        </button>
                    </div>
                    <platform-help-hint
                        .text=${this.t('evaluation.hints.run_scope')}
                        .label=${this.t('evaluation.hints.run_scope_label')}
                        placement="bottom"
                    ></platform-help-hint>
                    <div class="numbers">
                        ${this._renderStepper(this.t('evaluation.toolbar.trials'), this.trials, () => this._stepTrials(1), () => this._stepTrials(-1))}
                        ${this._renderStepper(this.t('evaluation.toolbar.concurrency'), this.maxConcurrency, () => this._stepConcurrency(1), () => this._stepConcurrency(-1))}
                    </div>
                    <platform-help-hint
                        .text=${this.t('evaluation.hints.run_options')}
                        .label=${this.t('evaluation.hints.run_options_label')}
                        placement="bottom"
                    ></platform-help-hint>
                </div>

                <div class="actions">
                    ${runState.length > 0 ? html`
                        <span class="status-pill" data-state=${runState}>
                            <platform-icon name="activity" size="13"></platform-icon>
                            ${runState} · ${passed}/${total} · ${failed}
                        </span>
                    ` : ''}
                    <button class="action-btn" type="button" title=${this.t('evaluation.toolbar.reload')} @click=${this._reload}>
                        <platform-icon name="refresh" size="14"></platform-icon>
                    </button>
                    ${runActive ? html`
                        <button class="action-btn danger" type="button" ?disabled=${this.busy} @click=${this._cancel}>
                            <platform-icon name="square" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.cancel')}
                        </button>
                    ` : html`
                        <button class="action-btn primary" type="button" ?disabled=${suiteDisabled || this.busy} @click=${this._run}>
                            <platform-icon name="play" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.run')}
                        </button>
                    `}
                </div>
            </div>
        `;
    }

    _renderTemplatesMenu() {
        const templates = Array.isArray(this.caseTemplates) ? this.caseTemplates : [];
        const groups = [
            ['deterministic', this.t('evaluation.templates.group_deterministic')],
            ['quality', this.t('evaluation.templates.group_quality')],
            ['safety', this.t('evaluation.templates.group_safety')],
            ['trace', this.t('evaluation.templates.group_trace')],
            ['advanced', this.t('evaluation.templates.group_advanced')],
        ];
        return html`
            <div class="template-menu">
                <div class="template-menu-head">
                    <span class="template-menu-title">
                        <strong>${this.t('evaluation.templates.menu_title')}</strong>
                        <span>${this.t('evaluation.templates.menu_subtitle')}</span>
                    </span>
                    <button class="step-btn" type="button" title=${this.t('evaluation.templates.close')} @click=${this._closeTemplates}>
                        <platform-icon name="close" size="12"></platform-icon>
                    </button>
                </div>
                ${groups.map(([groupId, label]) => this._renderTemplateGroup(groupId, label, templates))}
            </div>
        `;
    }

    _renderTemplateGroup(groupId, label, templates) {
        const items = templates.filter((template) => template.category === groupId);
        if (items.length === 0) {
            return '';
        }
        return html`
            <section class="template-section">
                <div class="template-section-title">
                    <platform-icon name="list" size="12"></platform-icon>
                    ${label}
                </div>
                ${items.map((template) => this._renderTemplateItem(template))}
            </section>
        `;
    }

    _renderTemplateItem(template) {
        return html`
            <button class="template-item" type="button" @click=${() => this._createFromTemplate(template.id)}>
                <platform-icon name=${template.icon} size="15"></platform-icon>
                <span class="template-copy">
                    <span class="template-name">${template.name}</span>
                    <span class="template-description">${template.description}</span>
                </span>
            </button>
        `;
    }

    _renderStepper(label, value, increment, decrement) {
        return html`
            <div class="stepper">
                <span class="step-copy">
                    <span class="step-label">${label}</span>
                    <span class="step-value">${value}</span>
                </span>
                <span class="step-actions">
                    <button class="step-btn" type="button" title=${label} @click=${increment}>
                        <platform-icon name="chevron-up" size="10"></platform-icon>
                    </button>
                    <button class="step-btn" type="button" title=${label} @click=${decrement}>
                        <platform-icon name="chevron-down" size="10"></platform-icon>
                    </button>
                </span>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-run-toolbar', FlowsEvaluationRunToolbar);
