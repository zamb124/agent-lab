/**
 * Admin billing page (system) — три вкладки: компании, цены/правила, usage.
 *
 * Доступно только при активной компании system. 403 → forbidden state,
 * 503 → unavailable state. Все мутации — через factory-операции.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import { FrontendSystemAccessModal } from '../../modals/system-access-modal.js';

const TABS = Object.freeze(['companies', 'prices_rules', 'usage']);

export class FrontendBillingAdminPage extends PlatformPage {
    static properties = {
        _tab: { state: true },
        _companyId: { state: true },
        _companyQuery: { state: true },
        _facetOpen: { state: true },
        _pricesDraft: { state: true },
        _companyPricesDraft: { state: true },
        _rulesDraft: { state: true },
        _usageFilters: { state: true },
        _usageFacetOpen: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .tabs {
                display: flex;
                gap: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
                margin-bottom: var(--space-4);
            }
            .tab {
                padding: var(--space-2) var(--space-4);
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: var(--text-sm);
                border-bottom: 2px solid transparent;
            }
            .tab[aria-selected="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .scope-banner {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3) var(--space-4);
                margin-bottom: var(--space-4);
                display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center;
            }
            .scope-banner .label { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.05em; }
            .scope-banner .value { color: var(--text-primary); font-weight: var(--font-medium); }
            .scope-banner input {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-3);
                color: var(--text-primary);
                font-size: var(--text-sm);
                min-width: 280px;
                position: relative;
            }
            .scope-banner .input-wrap { position: relative; }
            .suggest {
                position: absolute;
                top: calc(100% + 4px); left: 0; right: 0;
                background: var(--bg-primary);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-xl);
                max-height: 240px;
                overflow-y: auto;
                z-index: 20;
                min-width: 280px;
            }
            .suggest-item {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-primary);
                cursor: pointer;
            }
            .suggest-item:hover { background: var(--glass-solid-medium); }

            section { background: var(--glass-solid-subtle); border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg); padding: var(--space-4); margin-bottom: var(--space-4); }
            .section-title { font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); margin-bottom: var(--space-3); }

            table { width: 100%; border-collapse: collapse; }
            th, td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--glass-border-subtle); text-align: left; font-size: var(--text-sm); }
            th { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.05em; }
            td.mono { font-family: var(--font-mono); color: var(--text-secondary); }

            .row-input {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                padding: var(--space-1) var(--space-2);
                color: var(--text-primary);
                font-size: var(--text-sm);
                width: 100%;
                box-sizing: border-box;
            }

            .actions { display: flex; gap: var(--space-2); margin-top: var(--space-3); flex-wrap: wrap; }
            .btn {
                padding: var(--space-2) var(--space-4);
                background: transparent; color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm);
            }
            .btn:hover { border-color: var(--accent); color: var(--text-primary); }
            .btn.primary { background: var(--accent); color: white; border-color: var(--accent); }
            .btn.danger { background: var(--error); color: white; border-color: var(--error); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .filters { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); margin-bottom: var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); position: relative; }
            .field label { font-size: var(--text-xs); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }

            .state {
                padding: var(--space-8) var(--space-6);
                text-align: center;
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .state.forbidden, .state.unavailable { border-color: var(--warning); }
            .state-title { font-weight: var(--font-semibold); margin-bottom: var(--space-2); }

            textarea {
                width: 100%; min-height: 280px;
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                box-sizing: border-box;
            }
        `,
    ];

    constructor() {
        super();
        this._tab = 'companies';
        this._companyId = '';
        this._companyQuery = '';
        this._facetOpen = false;
        this._pricesDraft = null;
        this._companyPricesDraft = null;
        this._rulesDraft = null;
        this._usageFilters = {};
        this._usageFacetOpen = null;

        this._companies = this.useOp('frontend/admin_billing_companies');
        this._companyResolve = this.useOp('frontend/admin_billing_company_resolve');
        this._pricesGlobal = this.useOp('frontend/admin_billing_prices_global_load');
        this._pricesGlobalSave = this.useOp('frontend/admin_billing_prices_global_update');
        this._companyPrices = this.useOp('frontend/admin_billing_company_prices_load');
        this._companyPricesSave = this.useOp('frontend/admin_billing_company_prices_update');
        this._rules = this.useOp('frontend/admin_billing_rules_load');
        this._rulesSave = this.useOp('frontend/admin_billing_rules_update');
        this._rulesDefault = this.useOp('frontend/admin_billing_rules_default_load');
        this._usage = this.useOp('frontend/admin_billing_usage_load');
        this._facets = this.useFacets('frontend/admin_billing_facets');
        this._systemAccessLeave = this.useOp('frontend/admin_system_access_leave');

        this._loadedTabs = new Set();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (this._tab === 'companies' && !this._loadedTabs.has('companies')) {
            this._loadedTabs.add('companies');
            this._companies.run({ offset: 0, append: false });
        }
        if (this._tab === 'prices_rules' && !this._loadedTabs.has('prices_rules')) {
            this._loadedTabs.add('prices_rules');
            this._pricesGlobal.run(null);
        }
    }

    _selectTab(tab) {
        this._tab = tab;
    }

    _resolveCompany() {
        const q = this._companyQuery.trim();
        if (!q) return;
        this._companyResolve.run({ q });
    }

    _onResolveSuccess() {
        const r = this._companyResolve.lastResult;
        if (r && r.company_id) {
            this._companyId = r.company_id;
            this._companyPrices.run({ company_id: r.company_id });
            this._rules.run({ company_id: r.company_id });
        }
    }

    _onCompanyInput(value) {
        this._companyQuery = value;
        if (value && value.length >= 2) {
            this._facetOpen = true;
            this._facets.search('companies', value);
        } else {
            this._facetOpen = false;
        }
    }

    _selectCompanyFromFacet(item) {
        this._companyId = item.value;
        this._companyQuery = typeof item.label === 'string' && item.label !== '' ? item.label : item.value;
        this._facetOpen = false;
        this._companyPrices.run({ company_id: item.value });
        this._rules.run({ company_id: item.value });
    }

    _renderForbiddenOrUnavailable() {
        const terminal = this._companies.state && this._companies.state.terminal;
        if (terminal === 'forbidden') {
            return html`<div class="state forbidden">
                <div class="state-title">${this.t('platform_billing_page.forbidden')}</div>
            </div>`;
        }
        if (terminal === 'unavailable') {
            return html`<div class="state unavailable">
                <div class="state-title">${this.t('platform_billing_page.forbidden')}</div>
            </div>`;
        }
        return null;
    }

    _renderTabs() {
        return html`
            <div class="tabs" role="tablist" aria-label=${this.t('platform_billing_page.tabs_region_label')}>
                ${TABS.map((tab) => html`
                    <button
                        class="tab"
                        role="tab"
                        aria-selected=${this._tab === tab}
                        @click=${() => this._selectTab(tab)}
                    >${this.t(`platform_billing_page.tab_${tab}`)}</button>
                `)}
            </div>
        `;
    }

    _renderScopeBanner() {
        const items = this._facets.items('companies');
        return html`
            <div class="scope-banner">
                <span class="label">${this.t('platform_billing_page.billing_scope_banner_title')}</span>
                <div class="input-wrap">
                    <input
                        type="text"
                        placeholder=${this.t('platform_billing_page.billing_company_search_placeholder')}
                        .value=${this._companyQuery}
                        @input=${(e) => this._onCompanyInput(e.target.value)}
                        @keydown=${(e) => { if (e.key === 'Enter') this._resolveCompany(); }}
                        @blur=${() => setTimeout(() => { this._facetOpen = false; }, 180)}
                    />
                    ${this._facetOpen && items.length > 0 ? html`
                        <div class="suggest">
                            ${items.map((it) => html`
                                <div class="suggest-item"
                                    @mousedown=${(e) => { e.preventDefault(); this._selectCompanyFromFacet(it); }}>
                                    ${typeof it.label === 'string' && it.label !== '' ? it.label : it.value}
                                </div>
                            `)}
                        </div>
                    ` : null}
                </div>
                <button class="btn primary" @click=${() => this._resolveCompany()}>
                    ${this.t('platform_billing_page.billing_company_apply')}
                </button>
                ${this._companyId ? html`
                    <span class="label">${this.t('platform_billing_page.billing_scope_active_label')}</span>
                    <span class="value">${this._companyId}</span>
                ` : html`
                    <span class="hint">${this.t('platform_billing_page.billing_scope_none_hint')}</span>
                `}
            </div>
        `;
    }

    _onCompanyResolveUpdated() {
        const result = this._companyResolve.lastResult;
        if (result && result.company_id && result.company_id !== this._companyId) {
            this._companyId = result.company_id;
            const subdomain = typeof result.subdomain === 'string' && result.subdomain !== '' ? result.subdomain : result.company_id;
            this._companyQuery = result.name ? `${result.name} (${subdomain})` : result.company_id;
            this._companyPrices.run({ company_id: result.company_id });
            this._rules.run({ company_id: result.company_id });
        }
    }

    _renderCompaniesTab() {
        const records = this._companies.state.items;
        const hasMore = !!(this._companies.state && this._companies.state.hasMore);
        const offset = this._companies.state.offset;
        const busy = this._companies.busy;
        const forbidden = this._renderForbiddenOrUnavailable();
        if (forbidden) return forbidden;
        if (busy && records.length === 0) {
            return html`<div class="state"><glass-spinner></glass-spinner></div>`;
        }
        return html`
            <section>
                <div class="section-title">${this.t('platform_billing_page.companies_overview_heading')}</div>
                ${records.length === 0
                    ? html`<div class="hint">${this.t('platform_billing_page.empty')}</div>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('platform_billing_page.col_company_id')}</th>
                                <th>${this.t('platform_billing_page.col_name')}</th>
                                <th>${this.t('platform_billing_page.col_subdomain')}</th>
                                <th>${this.t('platform_billing_page.col_tariff')}</th>
                                <th>${this.t('platform_billing_page.col_balance')}</th>
                                <th>${this.t('platform_billing_page.col_monthly_budget')}</th>
                                <th>${this.t('platform_billing_page.col_spent_month')}</th>
                                <th>${this.t('platform_billing_page.col_actions')}</th>
                            </tr></thead>
                            <tbody>
                                ${records.map((r) => html`
                                    <tr>
                                        <td class="mono">${r.company_id}</td>
                                        <td>${r.name}</td>
                                        <td>${r.subdomain || ''}</td>
                                        <td>${r.tariff_plan || ''}</td>
                                        <td>${r.balance ?? ''}</td>
                                        <td>${r.monthly_budget ?? ''}</td>
                                        <td>${r.current_month_spent ?? ''}</td>
                                        <td>
                                            <button class="btn" @click=${() => this.openModal(FrontendSystemAccessModal, { company_id: r.company_id })}>
                                                ${this.t('platform_billing_page.system_access_enter')}
                                            </button>
                                            <button class="btn danger" @click=${() => this._systemAccessLeave.run({ company_id: r.company_id })}>
                                                ${this.t('platform_billing_page.system_access_leave')}
                                            </button>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
                <div class="actions">
                    <button class="btn" ?disabled=${busy} @click=${() => this._companies.run({ offset: 0, append: false })}>
                        ${this.t('platform_billing_page.reload')}
                    </button>
                    ${hasMore ? html`
                        <button class="btn primary" ?disabled=${busy}
                            @click=${() => this._companies.run({ offset, append: true })}>
                            ${this.t('platform_billing_page.companies_load_more')}
                        </button>
                    ` : null}
                </div>
            </section>
        `;
    }

    _flattenPrices(catalog) {
        if (!catalog) return [];
        const out = [];
        for (const [category, resources] of Object.entries(catalog)) {
            if (!resources || typeof resources !== 'object') continue;
            for (const [resource_name, price] of Object.entries(resources)) {
                out.push({ category, resource_name, price: String(price) });
            }
        }
        return out;
    }

    _buildCatalog(rows) {
        const catalog = {};
        for (const r of rows) {
            const cat = r.category && r.category.trim();
            const name = r.resource_name && r.resource_name.trim();
            if (!cat || !name) continue;
            if (!catalog[cat]) catalog[cat] = {};
            const price = Number(r.price);
            if (Number.isNaN(price)) throw new Error(`invalid price for ${cat}:${name}`);
            catalog[cat][name] = price;
        }
        return catalog;
    }

    _renderPricesEditor(rows, onChange) {
        return html`
            <table>
                <thead><tr>
                    <th>${this.t('platform_billing_page.price_col_category')}</th>
                    <th>${this.t('platform_billing_page.price_col_resource')}</th>
                    <th>${this.t('platform_billing_page.price_col_price')}</th>
                    <th></th>
                </tr></thead>
                <tbody>
                    ${rows.map((r, idx) => html`
                        <tr>
                            <td><input class="row-input" .value=${r.category}
                                @input=${(e) => { rows[idx].category = e.target.value; onChange([...rows]); }} /></td>
                            <td><input class="row-input" .value=${r.resource_name}
                                @input=${(e) => { rows[idx].resource_name = e.target.value; onChange([...rows]); }} /></td>
                            <td><input class="row-input" type="number" step="0.0001" .value=${r.price}
                                @input=${(e) => { rows[idx].price = e.target.value; onChange([...rows]); }} /></td>
                            <td><button class="btn" @click=${() => { rows.splice(idx, 1); onChange([...rows]); }}>
                                ${this.t('platform_billing_page.price_remove_row')}
                            </button></td>
                        </tr>
                    `)}
                </tbody>
            </table>
            <div class="actions">
                <button class="btn" @click=${() => onChange([...rows, { category: '', resource_name: '', price: '0' }])}>
                    ${this.t('platform_billing_page.price_add_row')}
                </button>
            </div>
        `;
    }

    _renderPricesRulesTab() {
        const pricesData = this._pricesGlobal.lastResult;
        if (!pricesData && this._pricesGlobal.busy) {
            return html`<div class="state"><glass-spinner></glass-spinner></div>`;
        }
        const effective = pricesData && pricesData.effective ? pricesData.effective : null;
        const override = pricesData && pricesData.storage_override ? pricesData.storage_override : null;
        if (this._pricesDraft === null && override !== null) {
            this._pricesDraft = this._flattenPrices(override);
        } else if (this._pricesDraft === null) {
            this._pricesDraft = [];
        }

        const companyPrices = this._companyPrices.lastResult;
        const companyOverride = companyPrices && companyPrices.storage_override ? companyPrices.storage_override : null;
        if (this._companyId && this._companyPricesDraft === null && companyOverride !== null) {
            this._companyPricesDraft = this._flattenPrices(companyOverride);
        } else if (this._companyId && this._companyPricesDraft === null) {
            this._companyPricesDraft = [];
        }

        const rulesData = this._rules.lastResult;
        const rulesDoc = rulesData && rulesData.document ? rulesData.document : null;
        if (this._companyId && this._rulesDraft === null && rulesDoc) {
            this._rulesDraft = JSON.stringify(rulesDoc, null, 2);
        }

        return html`
            <section>
                <div class="section-title">${this.t('platform_billing_page.section_prices')}</div>
                <p class="hint">${this.t('platform_billing_page.hint_prices_global_scope')}</p>
                ${this._renderPricesEditor(this._pricesDraft, (rows) => { this._pricesDraft = rows; })}
                <div class="actions">
                    <button class="btn primary" ?disabled=${this._pricesGlobalSave.busy}
                        @click=${() => this._pricesGlobalSave.run(this._buildCatalog(this._pricesDraft))}>
                        ${this.t('platform_billing_page.save_override')}
                    </button>
                    <button class="btn" ?disabled=${this._pricesGlobal.busy}
                        @click=${() => { this._pricesDraft = null; this._pricesGlobal.run(null); }}>
                        ${this.t('platform_billing_page.reload')}
                    </button>
                </div>

                ${effective ? html`
                    <details style="margin-top:var(--space-4)">
                        <summary>${this.t('platform_billing_page.billing_readonly_catalog_title')}
                            (${this.t('platform_billing_page.billing_readonly_catalog_rows', { count: this._flattenPrices(effective).length })})</summary>
                        <table style="margin-top:var(--space-2)">
                            <thead><tr>
                                <th>${this.t('platform_billing_page.price_col_category')}</th>
                                <th>${this.t('platform_billing_page.price_col_resource')}</th>
                                <th>${this.t('platform_billing_page.price_col_price')}</th>
                            </tr></thead>
                            <tbody>
                                ${this._flattenPrices(effective).map((r) => html`
                                    <tr>
                                        <td>${r.category}</td>
                                        <td>${r.resource_name}</td>
                                        <td>${r.price}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </details>
                ` : null}
            </section>

            ${this._companyId ? html`
                <section>
                    <div class="section-title">${this.t('platform_billing_page.subsection_company_prices_title')}</div>
                    <p class="hint">${this.t('platform_billing_page.hint_company_prices_scope')}</p>
                    ${this._renderPricesEditor(this._companyPricesDraft, (rows) => { this._companyPricesDraft = rows; })}
                    <div class="actions">
                        <button class="btn primary" ?disabled=${this._companyPricesSave.busy}
                            @click=${() => this._companyPricesSave.run({ company_id: this._companyId, body: this._buildCatalog(this._companyPricesDraft) })}>
                            ${this.t('platform_billing_page.save_company_override')}
                        </button>
                    </div>
                </section>

                <section>
                    <div class="section-title">${this.t('platform_billing_page.section_settlement_rules')}</div>
                    <p class="hint">${this.t('platform_billing_page.hint_settlement_company_scope')}</p>
                    <textarea
                        .value=${this._rulesDraft || ''}
                        @input=${(e) => { this._rulesDraft = e.target.value; }}
                    ></textarea>
                    <div class="actions">
                        <button class="btn primary" ?disabled=${this._rulesSave.busy}
                            @click=${() => this._saveRules()}>
                            ${this.t('platform_billing_page.save_rules')}
                        </button>
                        <button class="btn" @click=${() => this._loadRulesDefault()}>
                            ${this.t('platform_billing_page.rules_load_platform_default')}
                        </button>
                    </div>
                </section>
            ` : html`
                <div class="hint">${this.t('platform_billing_page.billing_company_required')}</div>
            `}
        `;
    }

    _saveRules() {
        const draft = typeof this._rulesDraft === 'string' ? this._rulesDraft : '';
        const text = draft.trim();
        if (!text) return;
        const body = JSON.parse(text);
        this._rulesSave.run({ company_id: this._companyId, body });
    }

    _loadRulesDefault() {
        if (!confirm(this.t('platform_billing_page.confirm_replace_rules_default'))) return;
        this._rulesDefault.run(null);
    }

    _onUsageFilter(field, facet, value) {
        this._usageFilters = { ...this._usageFilters, [field]: value };
        if (facet && value && value.length >= 2) {
            this._usageFacetOpen = facet;
            this._facets.search(facet, value);
        } else {
            this._usageFacetOpen = null;
        }
    }

    _selectUsageFacet(field, value) {
        this._usageFilters = { ...this._usageFilters, [field]: value };
        this._usageFacetOpen = null;
    }

    _renderUsageFacetField(field, facet, labelKey) {
        const value = this._usageFilters[field] || '';
        const items = this._facets.items(facet);
        const isOpen = this._usageFacetOpen === facet && value && value.length >= 2;
        return html`
            <div class="field">
                <label>${this.t(labelKey)}</label>
                <input class="row-input" type="text" .value=${value}
                    @input=${(e) => this._onUsageFilter(field, facet, e.target.value)}
                    @blur=${() => setTimeout(() => { this._usageFacetOpen = null; }, 180)} />
                ${isOpen ? html`
                    <div class="suggest">
                        ${items.length === 0
                            ? html`<div class="suggest-item">${this.t('platform_billing_page.empty')}</div>`
                            : items.map((it) => html`
                                <div class="suggest-item"
                                    @mousedown=${(e) => { e.preventDefault(); this._selectUsageFacet(field, it.value); }}>
                                    ${typeof it.label === 'string' && it.label !== '' ? it.label : it.value}
                                </div>
                            `)}
                    </div>
                ` : null}
            </div>
        `;
    }

    _renderUsageTimeField(field, labelKey) {
        const value = this._usageFilters[field] || '';
        return html`
            <div class="field">
                <label>${this.t(labelKey)}</label>
                <input class="row-input" type="datetime-local" .value=${value}
                    @input=${(e) => this._onUsageFilter(field, null, e.target.value)} />
            </div>
        `;
    }

    _renderUsageTab() {
        const offset = this._usage.state.offset;
        const limit = this._usage.state.limit;
        const items = this._usage.state.items;
        return html`
            <section>
                <div class="section-title">${this.t('platform_billing_page.section_usage')}</div>
                <p class="hint">${this.t('platform_billing_page.usage_facet_hint')}</p>
                <div class="filters">
                    ${this._renderUsageFacetField('company_id', 'companies', 'platform_billing_page.filter_company')}
                    ${this._renderUsageFacetField('usage_type', 'usage_types', 'platform_billing_page.filter_usage_type')}
                    ${this._renderUsageFacetField('resource_name', 'resource_names', 'platform_billing_page.filter_resource')}
                    ${this._renderUsageTimeField('from_time', 'platform_billing_page.filter_from')}
                    ${this._renderUsageTimeField('to_time', 'platform_billing_page.filter_to')}
                </div>
                <div class="actions">
                    <button class="btn primary" ?disabled=${this._usage.busy}
                        @click=${() => this._usage.run({ filters: this._usageFilters, offset: 0, limit })}>
                        ${this.t('platform_billing_page.apply')}
                    </button>
                </div>

                ${this._usage.busy
                    ? html`<div style="margin-top:var(--space-4)"><glass-spinner></glass-spinner></div>`
                    : (items.length === 0
                        ? html`<div class="hint" style="margin-top:var(--space-4)">${this.t('platform_billing_page.empty')}</div>`
                        : html`
                            <table style="margin-top:var(--space-3)">
                                <thead><tr>
                                    <th>${this.t('platform_billing_page.col_time')}</th>
                                    <th>${this.t('platform_billing_page.col_company')}</th>
                                    <th>${this.t('platform_billing_page.col_type')}</th>
                                    <th>${this.t('platform_billing_page.col_resource')}</th>
                                    <th>${this.t('platform_billing_page.col_quantity')}</th>
                                    <th>${this.t('platform_billing_page.col_cost')}</th>
                                    <th>${this.t('platform_billing_page.col_span')}</th>
                                    <th>${this.t('platform_billing_page.col_rule')}</th>
                                </tr></thead>
                                <tbody>
                                    ${items.map((r) => html`
                                        <tr>
                                            <td>${r.created_at ? new Date(r.created_at).toLocaleString() : ''}</td>
                                            <td>${r.company_name || r.company_id || ''}</td>
                                            <td>${r.usage_type || ''}</td>
                                            <td>${r.resource_name || ''}</td>
                                            <td>${r.quantity ?? ''}</td>
                                            <td>${r.total_cost ?? r.cost ?? ''}</td>
                                            <td class="mono">${r.span_id ? r.span_id.slice(0, 12) : ''}</td>
                                            <td>${r.rule_id || ''}</td>
                                        </tr>
                                    `)}
                                </tbody>
                            </table>
                            <div class="actions">
                                <button class="btn" ?disabled=${offset === 0 || this._usage.busy}
                                    @click=${() => this._usage.run({ filters: this._usageFilters, offset: Math.max(0, offset - limit), limit })}>
                                    ${this.t('platform_billing_page.usage_prev')}
                                </button>
                                <span class="hint">
                                    ${this.t('platform_billing_page.usage_page_info', { from: offset + 1, to: offset + items.length })}
                                </span>
                                <button class="btn" ?disabled=${items.length < limit || this._usage.busy}
                                    @click=${() => this._usage.run({ filters: this._usageFilters, offset: offset + limit, limit })}>
                                    ${this.t('platform_billing_page.usage_next')}
                                </button>
                            </div>
                        `)}
            </section>
        `;
    }

    render() {
        let content;
        if (this._tab === 'companies') content = this._renderCompaniesTab();
        else if (this._tab === 'prices_rules') content = this._renderPricesRulesTab();
        else if (this._tab === 'usage') content = this._renderUsageTab();

        return html`
            <page-header
                title=${this.t('platform_billing_page.title')}
                subtitle=${this.t('platform_billing_page.subtitle')}
            ></page-header>
            ${this._renderTabs()}
            ${this._tab !== 'companies' ? this._renderScopeBanner() : null}
            ${content}
        `;
    }
}

customElements.define('frontend-billing-admin-page', FrontendBillingAdminPage);
