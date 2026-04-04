/**
 * Админка: прайс-лист (конфиг + override) и отчёт по usage (только system).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';

const API_BASE = '/frontend/api/platform-billing';

export class BillingAdminPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .section {
                margin-bottom: var(--space-6);
            }
            .section h2 {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-3);
            }
            .grid {
                display: grid;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            label.field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            input,
            textarea {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            textarea.code {
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                min-height: 12rem;
            }
            pre.effective {
                margin: 0;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                white-space: pre-wrap;
                word-break: break-word;
                color: var(--text-primary);
            }
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: center;
            }
            .table-wrap {
                background: var(--glass-solid-medium);
                border-radius: var(--radius-lg);
                overflow-x: auto;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th,
            td {
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                text-align: left;
                font-size: var(--text-xs);
                color: var(--text-primary);
                vertical-align: top;
            }
            th {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-top: none;
            }
            .err {
                color: var(--color-danger, #c00);
                font-size: var(--text-sm);
            }
        `,
    ];

    static properties = {
        _effectiveJson: { type: String, state: true },
        _overrideText: { type: String, state: true },
        _pricesError: { type: String, state: true },
        _pricesLoading: { type: Boolean, state: true },
        _usageRows: { type: Array, state: true },
        _usageError: { type: String, state: true },
        _usageLoading: { type: Boolean, state: true },
        _uCompany: { type: String, state: true },
        _uUsageType: { type: String, state: true },
        _uFrom: { type: String, state: true },
        _uTo: { type: String, state: true },
        _uLimit: { type: String, state: true },
        _rulesText: { type: String, state: true },
        _rulesError: { type: String, state: true },
        _rulesLoading: { type: Boolean, state: true },
        _cPriceCompanyId: { type: String, state: true },
        _cPriceEffectiveJson: { type: String, state: true },
        _cPriceOverrideText: { type: String, state: true },
        _cPriceError: { type: String, state: true },
        _cPriceLoading: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this._effectiveJson = '';
        this._overrideText = '{}';
        this._pricesError = '';
        this._pricesLoading = false;
        this._usageRows = [];
        this._usageError = '';
        this._usageLoading = false;
        this._uCompany = '';
        this._uUsageType = '';
        this._uFrom = '';
        this._uTo = '';
        this._uLimit = '200';
        this._rulesText = '';
        this._rulesError = '';
        this._rulesLoading = false;
        this._cPriceCompanyId = '';
        this._cPriceEffectiveJson = '';
        this._cPriceOverrideText = '{}';
        this._cPriceError = '';
        this._cPriceLoading = false;
    }

    connectedCallback() {
        super.connectedCallback();
        void this._loadPrices();
        void this._loadSettlementRules();
    }

    async _loadPrices() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        this._pricesLoading = true;
        this._pricesError = '';
        try {
            const response = await fetch(`${API_BASE}/prices`, { credentials: 'include' });
            if (response.status === 403) {
                this._pricesError = t('platform_billing_page.forbidden');
                return;
            }
            if (!response.ok) {
                this._pricesError = t('platform_billing_page.prices_load_error');
                return;
            }
            const data = await response.json();
            this._effectiveJson = JSON.stringify(data.effective, null, 2);
            this._overrideText = JSON.stringify(data.storage_override ?? {}, null, 2);
        } catch {
            this._pricesError = t('platform_billing_page.prices_load_error');
        } finally {
            this._pricesLoading = false;
        }
    }

    async _saveOverride() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        this._pricesError = '';
        let parsed;
        try {
            parsed = JSON.parse(this._overrideText);
        } catch {
            this._pricesError = t('platform_billing_page.invalid_json');
            return;
        }
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            this._pricesError = t('platform_billing_page.invalid_json');
            return;
        }
        const response = await fetch(`${API_BASE}/prices`, {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsed),
        });
        if (!response.ok) {
            this._pricesError = t('platform_billing_page.save_error');
            return;
        }
        await this._loadPrices();
    }

    async _loadSettlementRules() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        this._rulesLoading = true;
        this._rulesError = '';
        try {
            const response = await fetch(`${API_BASE}/settlement-rules`, { credentials: 'include' });
            if (response.status === 403) {
                this._rulesError = t('platform_billing_page.forbidden');
                return;
            }
            if (!response.ok) {
                this._rulesError = t('platform_billing_page.rules_load_error');
                return;
            }
            const data = await response.json();
            this._rulesText = JSON.stringify(data.document ?? {}, null, 2);
        } catch {
            this._rulesError = t('platform_billing_page.rules_load_error');
        } finally {
            this._rulesLoading = false;
        }
    }

    async _saveSettlementRules() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        this._rulesError = '';
        let parsed;
        try {
            parsed = JSON.parse(this._rulesText);
        } catch {
            this._rulesError = t('platform_billing_page.invalid_json');
            return;
        }
        const response = await fetch(`${API_BASE}/settlement-rules`, {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsed),
        });
        if (!response.ok) {
            this._rulesError = t('platform_billing_page.save_rules_error');
            return;
        }
        await this._loadSettlementRules();
    }

    async _loadCompanyPrices() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        const cid = this._cPriceCompanyId.trim();
        if (!cid) {
            this._cPriceError = t('platform_billing_page.company_id_required');
            return;
        }
        this._cPriceLoading = true;
        this._cPriceError = '';
        try {
            const enc = encodeURIComponent(cid);
            const response = await fetch(`${API_BASE}/prices/company/${enc}`, { credentials: 'include' });
            if (response.status === 403) {
                this._cPriceError = t('platform_billing_page.forbidden');
                return;
            }
            if (!response.ok) {
                this._cPriceError = t('platform_billing_page.company_prices_load_error');
                return;
            }
            const data = await response.json();
            this._cPriceEffectiveJson = JSON.stringify(data.effective ?? {}, null, 2);
            this._cPriceOverrideText = JSON.stringify(data.storage_override ?? {}, null, 2);
        } catch {
            this._cPriceError = t('platform_billing_page.company_prices_load_error');
        } finally {
            this._cPriceLoading = false;
        }
    }

    async _saveCompanyPrices() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        const cid = this._cPriceCompanyId.trim();
        if (!cid) {
            this._cPriceError = t('platform_billing_page.company_id_required');
            return;
        }
        this._cPriceError = '';
        let parsed;
        try {
            parsed = JSON.parse(this._cPriceOverrideText);
        } catch {
            this._cPriceError = t('platform_billing_page.invalid_json');
            return;
        }
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
            this._cPriceError = t('platform_billing_page.invalid_json');
            return;
        }
        const enc = encodeURIComponent(cid);
        const response = await fetch(`${API_BASE}/prices/company/${enc}`, {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsed),
        });
        if (!response.ok) {
            this._cPriceError = t('platform_billing_page.save_error');
            return;
        }
        await this._loadCompanyPrices();
    }

    async _loadUsage() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        this._usageLoading = true;
        this._usageError = '';
        const params = new URLSearchParams();
        if (this._uCompany.trim()) params.set('company_id', this._uCompany.trim());
        if (this._uUsageType.trim()) params.set('usage_type', this._uUsageType.trim());
        if (this._uFrom.trim()) params.set('from', this._uFrom.trim());
        if (this._uTo.trim()) params.set('to', this._uTo.trim());
        const lim = parseInt(this._uLimit, 10);
        if (Number.isFinite(lim) && lim > 0) params.set('limit', String(lim));
        try {
            const response = await fetch(`${API_BASE}/usage-report?${params.toString()}`, {
                credentials: 'include',
            });
            if (response.status === 403) {
                this._usageError = t('platform_billing_page.forbidden');
                return;
            }
            if (!response.ok) {
                this._usageError = t('platform_billing_page.usage_load_error');
                return;
            }
            const data = await response.json();
            this._usageRows = Array.isArray(data.items) ? data.items : [];
        } catch {
            this._usageError = t('platform_billing_page.usage_load_error');
        } finally {
            this._usageLoading = false;
        }
    }

    render() {
        const t = (k, p = {}) => this.i18n.t(k, p);
        return html`
            <page-header
                title=${t('platform_billing_page.title')}
                subtitle=${t('platform_billing_page.subtitle')}
            ></page-header>

            <div class="section">
                <h2>${t('platform_billing_page.section_prices')}</h2>
                ${this._pricesError ? html`<div class="err">${this._pricesError}</div>` : ''}
                ${this._pricesLoading
                    ? html`<div>${t('platform_billing_page.loading')}</div>`
                    : html`
                          <p class="text-secondary" style="font-size: var(--text-xs); margin-bottom: var(--space-2);">
                              ${t('platform_billing_page.effective_hint')}
                          </p>
                          <pre class="effective">${this._effectiveJson}</pre>
                          <p class="text-secondary" style="font-size: var(--text-xs); margin: var(--space-3) 0 var(--space-2);">
                              ${t('platform_billing_page.override_hint')}
                          </p>
                          <textarea
                              class="code"
                              .value=${this._overrideText}
                              @input=${(e) => {
                                  this._overrideText = e.target.value;
                              }}
                          ></textarea>
                          <div class="actions" style="margin-top: var(--space-3);">
                              <platform-button @click=${() => this._loadPrices()}>
                                  ${t('platform_billing_page.reload')}
                              </platform-button>
                              <platform-button variant="primary" @click=${() => this._saveOverride()}>
                                  ${t('platform_billing_page.save_override')}
                              </platform-button>
                          </div>
                      `}
            </div>

            <div class="section">
                <h2>${t('platform_billing_page.section_settlement_rules')}</h2>
                ${this._rulesError ? html`<div class="err">${this._rulesError}</div>` : ''}
                ${this._rulesLoading
                    ? html`<div>${t('platform_billing_page.loading')}</div>`
                    : html`
                          <p class="text-secondary" style="font-size: var(--text-xs); margin-bottom: var(--space-2);">
                              ${t('platform_billing_page.settlement_rules_hint')}
                          </p>
                          <textarea
                              class="code"
                              style="min-height: 16rem;"
                              .value=${this._rulesText}
                              @input=${(e) => {
                                  this._rulesText = e.target.value;
                              }}
                          ></textarea>
                          <div class="actions" style="margin-top: var(--space-3);">
                              <platform-button @click=${() => this._loadSettlementRules()}>
                                  ${t('platform_billing_page.reload')}
                              </platform-button>
                              <platform-button variant="primary" @click=${() => this._saveSettlementRules()}>
                                  ${t('platform_billing_page.save_rules')}
                              </platform-button>
                          </div>
                      `}
            </div>

            <div class="section">
                <h2>${t('platform_billing_page.section_company_prices')}</h2>
                ${this._cPriceError ? html`<div class="err">${this._cPriceError}</div>` : ''}
                <div class="grid" style="grid-template-columns: 1fr auto; align-items: end; max-width: 32rem;">
                    <label class="field">
                        ${t('platform_billing_page.company_price_id_label')}
                        <input
                            type="text"
                            .value=${this._cPriceCompanyId}
                            @input=${(e) => {
                                this._cPriceCompanyId = e.target.value;
                            }}
                        />
                    </label>
                    <platform-button @click=${() => this._loadCompanyPrices()}>
                        ${this._cPriceLoading
                            ? t('platform_billing_page.loading')
                            : t('platform_billing_page.load_company_prices')}
                    </platform-button>
                </div>
                ${this._cPriceEffectiveJson
                    ? html`
                          <p
                              class="text-secondary"
                              style="font-size: var(--text-xs); margin: var(--space-3) 0 var(--space-2);"
                          >
                              ${t('platform_billing_page.company_effective_hint')}
                          </p>
                          <pre class="effective">${this._cPriceEffectiveJson}</pre>
                          <p
                              class="text-secondary"
                              style="font-size: var(--text-xs); margin: var(--space-3) 0 var(--space-2);"
                          >
                              ${t('platform_billing_page.company_override_hint')}
                          </p>
                          <textarea
                              class="code"
                              .value=${this._cPriceOverrideText}
                              @input=${(e) => {
                                  this._cPriceOverrideText = e.target.value;
                              }}
                          ></textarea>
                          <div class="actions" style="margin-top: var(--space-3);">
                              <platform-button variant="primary" @click=${() => this._saveCompanyPrices()}>
                                  ${t('platform_billing_page.save_company_override')}
                              </platform-button>
                          </div>
                      `
                    : ''}
            </div>

            <div class="section">
                <h2>${t('platform_billing_page.section_usage')}</h2>
                ${this._usageError ? html`<div class="err">${this._usageError}</div>` : ''}
                <div class="grid" style="grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));">
                    <label class="field">
                        ${t('platform_billing_page.filter_company')}
                        <input
                            type="text"
                            .value=${this._uCompany}
                            @input=${(e) => {
                                this._uCompany = e.target.value;
                            }}
                        />
                    </label>
                    <label class="field">
                        ${t('platform_billing_page.filter_usage_type')}
                        <input
                            type="text"
                            .value=${this._uUsageType}
                            @input=${(e) => {
                                this._uUsageType = e.target.value;
                            }}
                        />
                    </label>
                    <label class="field">
                        ${t('platform_billing_page.filter_from')}
                        <input
                            type="text"
                            placeholder="2026-01-01T00:00:00Z"
                            .value=${this._uFrom}
                            @input=${(e) => {
                                this._uFrom = e.target.value;
                            }}
                        />
                    </label>
                    <label class="field">
                        ${t('platform_billing_page.filter_to')}
                        <input
                            type="text"
                            placeholder="2026-02-01T00:00:00Z"
                            .value=${this._uTo}
                            @input=${(e) => {
                                this._uTo = e.target.value;
                            }}
                        />
                    </label>
                    <label class="field">
                        ${t('platform_billing_page.filter_limit')}
                        <input
                            type="text"
                            .value=${this._uLimit}
                            @input=${(e) => {
                                this._uLimit = e.target.value;
                            }}
                        />
                    </label>
                </div>
                <div class="actions">
                    <platform-button variant="primary" @click=${() => this._loadUsage()}>
                        ${this._usageLoading
                            ? t('platform_billing_page.loading')
                            : t('platform_billing_page.apply')}
                    </platform-button>
                </div>
                <div class="table-wrap" style="margin-top: var(--space-3);">
                    <table>
                        <thead>
                            <tr>
                                <th>${t('platform_billing_page.col_time')}</th>
                                <th>${t('platform_billing_page.col_company')}</th>
                                <th>${t('platform_billing_page.col_resource')}</th>
                                <th>${t('platform_billing_page.col_cost')}</th>
                                <th>${t('platform_billing_page.col_type')}</th>
                                <th>${t('platform_billing_page.col_span')}</th>
                                <th>${t('platform_billing_page.col_rule')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${this._usageRows.length === 0
                                ? html`<tr>
                                      <td colspan="7">${t('platform_billing_page.empty')}</td>
                                  </tr>`
                                : this._usageRows.map(
                                      (row) => html`
                                          <tr>
                                              <td>${row.timestamp ?? ''}</td>
                                              <td>${row.company_id ?? ''}</td>
                                              <td>${row.resource_name ?? ''}</td>
                                              <td>${row.cost ?? ''}</td>
                                              <td>${row.usage_type ?? ''}</td>
                                              <td>${row.metadata?.span_id ?? ''}</td>
                                              <td>${row.metadata?.rule_id ?? ''}</td>
                                          </tr>
                                      `,
                                  )}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

customElements.define('billing-admin-page', BillingAdminPage);
