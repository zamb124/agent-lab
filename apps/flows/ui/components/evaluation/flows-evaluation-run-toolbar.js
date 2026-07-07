import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { toolbarShellStyles } from '@platform/lib/styles/shared/toolbar-shell.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-segmented-control.js';

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
        toolbarShellStyles,
        css`
            :host {
                display: block;
                color: var(--text-primary);
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

            .scope-segment {
                flex: 1 1 180px;
                min-width: 0;
            }

            .docs-link,
            .template-item,
            .step-btn {
                min-height: var(--flows-chrome-control-size);
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

            .template-item:hover,
            .step-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .numbers {
                padding: 0;
            }

            .stepper {
                height: var(--flows-chrome-control-size);
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

    _scopeItems(caseScopeDisabled) {
        return [
            {
                value: 'suite',
                label: this.t('evaluation.toolbar.scope_suite'),
                icon: 'database',
            },
            {
                value: 'selected_case',
                label: this.t('evaluation.toolbar.scope_case'),
                icon: 'target',
                disabled: caseScopeDisabled,
            },
        ];
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
            <div class="toolbar-shell">
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
                    <platform-button variant="secondary" density="compact" ?disabled=${suiteDisabled || this.busy} @click=${this._toggleTemplates}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('evaluation.templates.button')}
                    </platform-button>
                    <platform-help-hint
                        .text=${this.t('evaluation.hints.templates')}
                        .label=${this.t('evaluation.hints.templates_label')}
                        placement="bottom"
                    ></platform-help-hint>
                    ${this._templatesOpen ? this._renderTemplatesMenu() : ''}
                </div>

                <div class="scope">
                    <div class="scope-segment">
                        <platform-segmented-control
                            full-width
                            density="compact"
                            .value=${this.runScope}
                            .items=${this._scopeItems(caseScopeDisabled)}
                            aria-label=${this.t('evaluation.toolbar.scope_aria')}
                            @change=${(event) => this._setScope(event.detail.value)}
                        ></platform-segmented-control>
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
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="compact"
                        aria-label=${this.t('evaluation.toolbar.reload')}
                        @click=${this._reload}
                    >
                        <platform-icon name="refresh" size="14"></platform-icon>
                    </platform-button>
                    ${runActive ? html`
                        <platform-button variant="danger" density="compact" ?disabled=${this.busy} @click=${this._cancel}>
                            <platform-icon name="square" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.cancel')}
                        </platform-button>
                    ` : html`
                        <platform-button variant="primary" density="compact" ?disabled=${suiteDisabled || this.busy} @click=${this._run}>
                            <platform-icon name="play" size="14"></platform-icon>
                            ${this.t('evaluation.toolbar.run')}
                        </platform-button>
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
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="compact"
                        title=${this.t('evaluation.templates.close')}
                        aria-label=${this.t('evaluation.templates.close')}
                        @click=${this._closeTemplates}
                    >
                        <platform-icon name="close" size="12"></platform-icon>
                    </platform-button>
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

    _onSelectableKeydown(e, handler) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handler.call(this);
        }
    }

    _renderTemplateItem(template) {
        return html`
            <article
                class="template-item"
                tabindex="0"
                role="button"
                @click=${() => this._createFromTemplate(template.id)}
                @keydown=${(e) => this._onSelectableKeydown(e, () => this._createFromTemplate(template.id))}
            >
                <platform-icon name=${template.icon} size="15"></platform-icon>
                <span class="template-copy">
                    <span class="template-name">${template.name}</span>
                    <span class="template-description">${template.description}</span>
                </span>
            </article>
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
                    <platform-button variant="ghost" icon-only density="compact" title=${label} aria-label=${label} @click=${increment}>
                        <platform-icon name="chevron-up" size="10"></platform-icon>
                    </platform-button>
                    <platform-button variant="ghost" icon-only density="compact" title=${label} aria-label=${label} @click=${decrement}>
                        <platform-icon name="chevron-down" size="10"></platform-icon>
                    </platform-button>
                </span>
            </div>
        `;
    }
}

customElements.define('flows-evaluation-run-toolbar', FlowsEvaluationRunToolbar);
