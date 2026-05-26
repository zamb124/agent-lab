import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import { evaluationCatalogCategoryKey, evaluationCatalogNameKey } from '../../_helpers/evaluation-catalog-labels.js';

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

function lower(value) {
    return value.toLocaleLowerCase();
}

function enabledCount(cases) {
    return asArray(cases).filter((item) => item && item.enabled === true).length;
}

export class FlowsEvaluationSuiteSidebar extends PlatformElement {
    static properties = {
        suites: { type: Array },
        cases: { type: Array },
        catalog: { type: Array },
        selectedSuiteId: { type: String },
        selectedCaseId: { type: String },
        activePanel: { type: String },
        _query: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                min-width: 0;
                min-height: 0;
                height: 100%;
                color: var(--text-primary);
            }

            .rail {
                width: 286px;
                min-width: 260px;
                max-width: 320px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                padding: 12px;
                border-right: 1px solid color-mix(in srgb, var(--border-subtle), transparent 12%);
                background: color-mix(in srgb, var(--bg-surface), transparent 4%);
                box-sizing: border-box;
            }

            .section-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .section-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0;
                font-weight: var(--font-semibold);
            }

            .section-title platform-help-hint {
                text-transform: none;
            }

            .icon-btn {
                width: 30px;
                height: 30px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .search {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 38px;
                padding: 0 var(--space-3);
                border-radius: 18px;
                border: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-solid-strong), transparent 16%);
                box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-inverse), transparent 94%);
            }

            .search platform-icon {
                color: var(--text-tertiary);
                flex: 0 0 auto;
            }

            .search input {
                flex: 1;
                min-width: 0;
                border: 0;
                outline: 0;
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
            }

            .search input::placeholder {
                color: var(--text-tertiary);
            }

            .scroll {
                flex: 1;
                min-height: 0;
                overflow: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding-right: 2px;
            }

            .suite-list,
            .case-list,
            .panel-list,
            .catalog-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .row {
                width: 100%;
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: var(--space-2);
                min-height: 36px;
                padding: var(--space-2);
                border-radius: 12px;
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                text-align: left;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .row:hover {
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
            }

            .row[data-active="true"] {
                color: var(--text-primary);
                border-color: color-mix(in srgb, var(--accent), transparent 58%);
                background: color-mix(in srgb, var(--accent), transparent 90%);
                box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent), transparent 86%) inset;
            }

            .row-main {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }

            .row-title {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .row-sub {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 22px;
                height: 22px;
                padding: 0 7px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }

            .catalog-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .catalog-chip {
                min-width: 0;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 7px 9px;
                border-radius: 10px;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                overflow: hidden;
            }

            .catalog-chip span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .empty {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-height: 42px;
                justify-content: center;
                padding: 0 var(--space-3);
                border: 1px solid color-mix(in srgb, var(--border-subtle), transparent 34%);
                border-radius: 12px;
                background: color-mix(in srgb, var(--bg-surface), transparent 24%);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .empty-action {
                width: 100%;
                align-items: center;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .empty-action:hover {
                color: var(--text-primary);
                border-color: color-mix(in srgb, var(--accent), transparent 58%);
                background: color-mix(in srgb, var(--accent), transparent 91%);
            }

            .empty-action span:last-child {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            @media (max-width: 1024px) {
                .rail {
                    width: 260px;
                    padding: var(--space-3);
                }
            }

            @media (max-width: 767px) {
                .rail {
                    width: 100%;
                    max-width: none;
                    border-right: 0;
                    border-bottom: 1px solid var(--border-subtle);
                    max-height: 42vh;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.suites = [];
        this.cases = [];
        this.catalog = [];
        this.selectedSuiteId = '';
        this.selectedCaseId = '';
        this.activePanel = 'case';
        this._query = '';
    }

    _filteredCases() {
        const query = lower(this._query.trim());
        if (query.length === 0) {
            return asArray(this.cases);
        }
        return asArray(this.cases).filter((item) => {
            const name = lower(stringValue(item, 'name'));
            const description = lower(stringValue(item, 'description'));
            return name.includes(query) || description.includes(query);
        });
    }

    _selectSuite(suiteId) {
        this.emit('suite-select', { suite_id: suiteId });
    }

    _selectCase(caseId) {
        this.emit('case-select', { case_id: caseId });
    }

    _selectPanel(panel) {
        this.emit('panel-select', { panel });
    }

    _createSuite() {
        this.emit('suite-create', null);
    }

    _createCase() {
        this.emit('case-create', null);
    }

    _onSearch(event) {
        const target = event.target;
        this._query = target && typeof target.value === 'string' ? target.value : '';
    }

    render() {
        const suites = asArray(this.suites);
        const cases = this._filteredCases();
        const catalog = asArray(this.catalog).slice(0, 6);
        return html`
            <aside class="rail">
                <div class="search">
                    <platform-icon name="search" size="16"></platform-icon>
                    <input
                        type="search"
                        data-canon="search"
                        .value=${this._query}
                        placeholder=${this.t('evaluation.sidebar.search')}
                        @input=${this._onSearch}
                    />
                </div>

                <div class="scroll">
                    <section>
                        <div class="section-head">
                            <div class="section-title">
                                <platform-icon name="database" size="14"></platform-icon>
                                ${this.t('evaluation.sidebar.suites')}
                                <platform-help-hint
                                    .text=${this.t('evaluation.hints.sidebar_suites')}
                                    .label=${this.t('evaluation.hints.sidebar_suites_label')}
                                    placement="bottom"
                                ></platform-help-hint>
                            </div>
                            <button class="icon-btn" type="button" title=${this.t('evaluation.sidebar.new_suite')} @click=${this._createSuite}>
                                <platform-icon name="plus" size="15"></platform-icon>
                            </button>
                        </div>
                        <div class="suite-list">
                            ${suites.length > 0 ? suites.map((suite) => this._renderSuite(suite)) : this._renderEmptyAction(this.t('evaluation.sidebar.empty_suites'), this.t('evaluation.sidebar.new_suite'), this._createSuite)}
                        </div>
                    </section>

                    <section>
                        <div class="section-head">
                            <div class="section-title">
                                <platform-icon name="list-checks" size="14"></platform-icon>
                                ${this.t('evaluation.sidebar.cases')}
                                <platform-help-hint
                                    .text=${this.t('evaluation.hints.sidebar_cases')}
                                    .label=${this.t('evaluation.hints.sidebar_cases_label')}
                                    placement="bottom"
                                ></platform-help-hint>
                            </div>
                            <button class="icon-btn" type="button" title=${this.t('evaluation.sidebar.new_case')} @click=${this._createCase}>
                                <platform-icon name="plus" size="15"></platform-icon>
                            </button>
                        </div>
                        <div class="case-list">
                            ${cases.length > 0 ? cases.map((testCase) => this._renderCase(testCase)) : this._renderEmptyAction(this.t('evaluation.sidebar.empty_cases'), this.t('evaluation.sidebar.new_case'), this._createCase)}
                        </div>
                    </section>

                    <section>
                        <div class="section-head">
                            <div class="section-title">
                                <platform-icon name="layers" size="14"></platform-icon>
                                ${this.t('evaluation.sidebar.workspace')}
                                <platform-help-hint
                                    .text=${this.t('evaluation.hints.sidebar_workspace')}
                                    .label=${this.t('evaluation.hints.sidebar_workspace_label')}
                                    placement="bottom"
                                ></platform-help-hint>
                            </div>
                        </div>
                        <div class="panel-list">
                            ${this._renderPanel('case', 'edit', this.t('evaluation.panels.case'))}
                            ${this._renderPanel('compare', 'git-compare', this.t('evaluation.panels.compare'))}
                            ${this._renderPanel('trace', 'activity', this.t('evaluation.panels.trace'))}
                            ${this._renderPanel('monitoring', 'shield', this.t('evaluation.panels.monitoring'))}
                        </div>
                    </section>

                    <section>
                        <div class="section-head">
                            <div class="section-title">
                                <platform-icon name="sparkles" size="14"></platform-icon>
                                ${this.t('evaluation.sidebar.evaluator_pack')}
                                <platform-help-hint
                                    .text=${this.t('evaluation.hints.sidebar_evaluators')}
                                    .label=${this.t('evaluation.hints.sidebar_evaluators_label')}
                                    placement="bottom"
                                ></platform-help-hint>
                            </div>
                            <span class="badge">${asArray(this.catalog).length}</span>
                        </div>
                        <div class="catalog-list">
                            ${catalog.length > 0 ? catalog.map((item) => this._renderCatalogChip(item)) : this._renderEmpty(this.t('evaluation.sidebar.empty_catalog'))}
                        </div>
                    </section>
                </div>
            </aside>
        `;
    }

    _renderSuite(suite) {
        const suiteId = stringValue(suite, 'suite_id');
        const name = stringValue(suite, 'name');
        const description = stringValue(suite, 'description');
        const active = suiteId === this.selectedSuiteId;
        return html`
            <button class="row" type="button" data-active=${active ? 'true' : 'false'} @click=${() => this._selectSuite(suiteId)}>
                <platform-icon name="folder" size="15"></platform-icon>
                <span class="row-main">
                    <span class="row-title">${name}</span>
                    <span class="row-sub">${description}</span>
                </span>
                <span class="badge">${enabledCount(this.cases)}</span>
            </button>
        `;
    }

    _renderCase(testCase) {
        const caseId = stringValue(testCase, 'case_id');
        const name = stringValue(testCase, 'name');
        const tags = asArray(testCase.tags);
        const subtitle = tags.length > 0 ? tags.join(', ') : this.t('evaluation.sidebar.case_no_tags');
        const active = caseId === this.selectedCaseId;
        return html`
            <button class="row" type="button" data-active=${active ? 'true' : 'false'} @click=${() => this._selectCase(caseId)}>
                <platform-icon name=${testCase.enabled === true ? 'check-circle' : 'circle'} size="15"></platform-icon>
                <span class="row-main">
                    <span class="row-title">${name}</span>
                    <span class="row-sub">${subtitle}</span>
                </span>
                <span class="badge">${asArray(testCase.turns).length}</span>
            </button>
        `;
    }

    _renderPanel(panel, icon, label) {
        const active = panel === this.activePanel;
        return html`
            <button class="row" type="button" data-active=${active ? 'true' : 'false'} @click=${() => this._selectPanel(panel)}>
                <platform-icon name=${icon} size="15"></platform-icon>
                <span class="row-main">
                    <span class="row-title">${label}</span>
                </span>
                <platform-icon name="chevron-right" size="14"></platform-icon>
            </button>
        `;
    }

    _renderCatalogChip(item) {
        const evaluatorId = stringValue(item, 'evaluator_id');
        const category = stringValue(item, 'category');
        const name = this.t(evaluationCatalogNameKey(evaluatorId));
        return html`
            <span class="catalog-chip" title=${name}>
                <platform-icon name="badge-check" size="13"></platform-icon>
                <span>${this.t(evaluationCatalogCategoryKey(category))}: ${name}</span>
            </span>
        `;
    }

    _renderEmpty(message) {
        return html`<div class="empty">${message}</div>`;
    }

    _renderEmptyAction(message, label, handler) {
        return html`
            <button class="empty empty-action" type="button" @click=${() => handler.call(this)}>
                <span>${message}</span>
                <span><platform-icon name="plus" size="13"></platform-icon>${label}</span>
            </button>
        `;
    }
}

customElements.define('flows-evaluation-suite-sidebar', FlowsEvaluationSuiteSidebar);
