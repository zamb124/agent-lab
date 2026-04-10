/**
 * Billing Page - Баланс, тарифный план, пополнение и история платежей.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '../../modals/topup-modal.js';
import '@platform/lib/components/layout/page-header.js';

export class BillingPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .billing-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: var(--space-6);
                margin-bottom: var(--space-8);
            }

            .billing-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                backdrop-filter: blur(20px);
            }

            .card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-5);
            }

            .card-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
            }

            .card-icon {
                font-size: var(--text-3xl);
            }

            .balance-amount {
                font-size: var(--text-5xl);
                font-weight: var(--font-bold);
                color: var(--accent);
                margin: 0 0 var(--space-2) 0;
            }

            .balance-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-4) 0;
            }

            .btn-topup {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-5);
                background: var(--accent-gradient);
                color: var(--text-on-accent, #fff);
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: opacity var(--duration-normal);
            }

            .btn-topup:hover {
                opacity: 0.9;
            }

            .plan-info {
                margin-bottom: var(--space-4);
            }

            .plan-name {
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                text-transform: uppercase;
                margin: 0 0 var(--space-2) 0;
            }

            .plan-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0 0 var(--space-4) 0;
            }

            .plan-features {
                list-style: none;
                padding: 0;
                margin: 0;
            }

            .plan-feature {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .feature-icon {
                color: var(--success);
                font-size: var(--text-base);
            }

            .budget-info {
                margin-bottom: var(--space-4);
            }

            .budget-row {
                display: flex;
                justify-content: space-between;
                padding: var(--space-3) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .budget-row:last-child {
                border-bottom: none;
            }

            .budget-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .budget-value {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .progress-bar {
                width: 100%;
                height: 8px;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-full);
                overflow: hidden;
                margin-top: var(--space-4);
            }

            .progress-fill {
                height: 100%;
                background: var(--accent-gradient);
                transition: width var(--duration-normal);
            }

            .section {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-8);
                backdrop-filter: blur(20px);
                margin-bottom: var(--space-8);
            }

            .section-title {
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-6) 0;
            }

            .usage-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: var(--space-6);
            }

            .usage-stat {
                text-align: center;
            }

            .stat-value {
                font-size: var(--text-4xl);
                font-weight: var(--font-bold);
                color: var(--accent);
                margin: 0 0 var(--space-2) 0;
            }

            .stat-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0;
            }

            .resource-list {
                margin-top: var(--space-6);
            }

            .resource-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-3);
            }

            .resource-name {
                font-size: var(--text-base);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .resource-stats {
                text-align: right;
            }

            .resource-cost {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--accent);
            }

            .resource-calls {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            /* --- Payment History --- */

            .history-table {
                width: 100%;
                border-collapse: collapse;
            }

            .history-table th {
                text-align: left;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .history-table td {
                font-size: var(--text-sm);
                color: var(--text-primary);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .history-table tr:last-child td {
                border-bottom: none;
            }

            .status-badge {
                display: inline-block;
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }

            .status-success {
                background: rgba(52, 211, 153, 0.15);
                color: var(--success);
            }

            .status-pending {
                background: rgba(251, 191, 36, 0.15);
                color: var(--warning, #fbbf24);
            }

            .status-failed {
                background: rgba(239, 68, 68, 0.15);
                color: var(--error);
            }

            .empty-state {
                text-align: center;
                padding: var(--space-8);
                color: var(--text-tertiary);
            }

            .empty-state-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin: 0 0 var(--space-2) 0;
            }

            .empty-state-desc {
                font-size: var(--text-sm);
                margin: 0;
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
            }

            @media (max-width: 768px) {
                .billing-grid,
                .usage-grid {
                    grid-template-columns: 1fr;
                }
            }
        `
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            subscription: s.entities.billing.subscription,
            usage: s.entities.billing.usage,
            loading: s.entities.billing.loading,
            payments: s.entities.payments.history,
            paymentsLoading: s.entities.payments.loading,
        }));
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._loadBilling();
        await this._loadHistory();
        this._handlePaymentCallback();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadBilling() {
        const { subscription } = this.state.value;
        if (subscription) return;

        FrontendStore.setBillingLoading(true);
        const billingService = this.services.get('billing');
        const [sub, usage] = await Promise.all([
            billingService.getSubscription(),
            billingService.getUsageStats(),
        ]);
        FrontendStore.setBillingData(sub, usage);
    }

    async _loadHistory() {
        FrontendStore.setPaymentsLoading(true);
        const billingService = this.services.get('billing');
        const data = await billingService.getHistory();
        FrontendStore.setPaymentHistory(data.payments ?? []);
    }

    _handlePaymentCallback() {
        const params = new URLSearchParams(window.location.search);
        const paymentStatus = params.get('payment');
        if (!paymentStatus) return;

        const tb = (key, p) => this.i18n.t(key, p ?? {}, I18nNs.BILLING);

        if (paymentStatus === 'success') {
            this.success(tb('payment_success_message'));
            this._reloadAfterPayment();
        } else if (paymentStatus === 'fail') {
            this.error(tb('payment_error_message'));
        }

        const url = new URL(window.location.href);
        url.searchParams.delete('payment');
        url.searchParams.delete('transaction_id');
        window.history.replaceState({}, '', url.pathname);
    }

    async _reloadAfterPayment() {
        const billingService = this.services.get('billing');
        const [sub, usage] = await Promise.all([
            billingService.getSubscription(),
            billingService.getUsageStats(),
        ]);
        FrontendStore.setBillingData(sub, usage);
        await this._loadHistory();
    }

    _openTopupModal() {
        const modal = document.createElement('topup-modal');
        modal.heading = this.i18n.t('modal.title', {}, I18nNs.BILLING);
        document.body.appendChild(modal);
        modal.showModal();
        modal.addEventListener('close', () => modal.remove());
    }

    render() {
        const { loading } = this.state.value;
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);

        if (loading) {
            return html`
                <div class="loading-state">
                    ${tb('frontend_console.loading')}
                </div>
            `;
        }

        return html`
            <page-header title=${tb('frontend_console.page_title')}></page-header>

            <div class="billing-grid">
                ${this._renderBalanceCard()}
                ${this._renderPlanCard()}
                ${this._renderBudgetCard()}
            </div>

            ${this._renderUsageSection()}
            ${this._renderHistorySection()}
        `;
    }

    _renderBalanceCard() {
        const { subscription } = this.state.value;
        const balance = subscription?.balance ?? 0;
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);
        const cur = tb('frontend_console.currency_rub');

        return html`
            <div class="billing-card">
                <div class="card-header">
                    <h2 class="card-title">${tb('frontend_console.balance_title')}</h2>
                    <span class="card-icon">B</span>
                </div>

                <h3 class="balance-amount">${balance.toFixed(0)} ${cur}</h3>
                <p class="balance-label">${tb('frontend_console.balance_available')}</p>

                <button class="btn-topup" @click=${this._openTopupModal}>
                    + ${tb('frontend_console.top_up')}
                </button>
            </div>
        `;
    }

    _renderPlanCard() {
        const { subscription } = this.state.value;
        const plan = subscription?.plan ?? 'FREE';
        const planFeatures = this._getPlanFeatures(plan);
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);

        return html`
            <div class="billing-card">
                <div class="card-header">
                    <h2 class="card-title">${tb('frontend_console.plan_title')}</h2>
                    <span class="card-icon">P</span>
                </div>

                <div class="plan-info">
                    <h3 class="plan-name">${plan}</h3>
                    <p class="plan-description">${planFeatures.description}</p>

                    <ul class="plan-features">
                        ${planFeatures.features.map((feature) => html`
                            <li class="plan-feature">
                                <span class="feature-icon">+</span>
                                <span>${feature}</span>
                            </li>
                        `)}
                    </ul>
                </div>
            </div>
        `;
    }

    _renderBudgetCard() {
        const { subscription } = this.state.value;
        const monthlyBudget = subscription?.monthly_budget ?? 0;
        const currentSpent = subscription?.current_month_spent ?? 0;
        const percentage = monthlyBudget > 0 ? (currentSpent / monthlyBudget * 100) : 0;
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);
        const cur = tb('frontend_console.currency_rub');

        return html`
            <div class="billing-card">
                <div class="card-header">
                    <h2 class="card-title">${tb('frontend_console.budget_title')}</h2>
                    <span class="card-icon">L</span>
                </div>

                <div class="budget-info">
                    <div class="budget-row">
                        <span class="budget-label">${tb('frontend_console.spent')}</span>
                        <span class="budget-value">${currentSpent.toFixed(2)} ${cur}</span>
                    </div>
                    <div class="budget-row">
                        <span class="budget-label">${tb('frontend_console.limit')}</span>
                        <span class="budget-value">
                            ${monthlyBudget > 0 ? `${monthlyBudget.toFixed(0)} ${cur}` : tb('frontend_console.limit_not_set')}
                        </span>
                    </div>
                </div>

                ${monthlyBudget > 0 ? html`
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${Math.min(percentage, 100)}%"></div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderUsageSection() {
        const { usage } = this.state.value;

        if (!usage) {
            return html``;
        }

        const totalCost = usage.total_cost ?? 0;
        const totalCalls = usage.total_calls ?? 0;
        const byResource = usage.by_resource ?? {};
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);
        const cur = tb('frontend_console.currency_rub');

        return html`
            <div class="section">
                <h2 class="section-title">${tb('frontend_console.usage_title')}</h2>

                <div class="usage-grid">
                    <div class="usage-stat">
                        <div class="stat-value">${totalCost.toFixed(2)} ${cur}</div>
                        <div class="stat-label">${tb('frontend_console.total_spent')}</div>
                    </div>
                    <div class="usage-stat">
                        <div class="stat-value">${totalCalls}</div>
                        <div class="stat-label">${tb('frontend_console.total_calls')}</div>
                    </div>
                    <div class="usage-stat">
                        <div class="stat-value">${Object.keys(byResource).length}</div>
                        <div class="stat-label">${tb('frontend_console.resources_used')}</div>
                    </div>
                </div>

                ${Object.keys(byResource).length > 0 ? html`
                    <div class="resource-list">
                        ${Object.entries(byResource).map(([name, stats]) => html`
                            <div class="resource-item">
                                <div class="resource-name">${name}</div>
                                <div class="resource-stats">
                                    <div class="resource-cost">${stats.cost.toFixed(2)} ${cur}</div>
                                    <div class="resource-calls">${tb('frontend_console.resource_calls', { count: String(stats.calls) })}</div>
                                </div>
                            </div>
                        `)}
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderHistorySection() {
        const { payments, paymentsLoading } = this.state.value;
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);
        const cur = tb('frontend_console.currency_rub');

        return html`
            <div class="section">
                <h2 class="section-title">${tb('payment_history.title')}</h2>

                ${paymentsLoading ? html`
                    <div class="loading-state">${tb('frontend_console.loading')}</div>
                ` : !payments || payments.length === 0 ? html`
                    <div class="empty-state">
                        <p class="empty-state-title">${tb('payment_history.empty_title')}</p>
                        <p class="empty-state-desc">${tb('payment_history.empty_description')}</p>
                    </div>
                ` : html`
                    <table class="history-table">
                        <thead>
                            <tr>
                                <th>${tb('history_table.date')}</th>
                                <th>${tb('history_table.amount')}</th>
                                <th>${tb('history_table.status')}</th>
                                <th>${tb('history_table.provider')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${payments.map((p) => html`
                                <tr>
                                    <td>${this._formatDate(p.created_at)}</td>
                                    <td>${p.amount.toFixed(2)} ${cur}</td>
                                    <td>
                                        <span class="status-badge ${this._statusClass(p.status)}">
                                            ${tb(`status.${p.status}`) || p.status}
                                        </span>
                                    </td>
                                    <td>${tb(`payment_methods.${p.payment_provider}`) || p.payment_provider}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                `}
            </div>
        `;
    }

    _statusClass(status) {
        const map = {
            success: 'status-success',
            pending: 'status-pending',
            failed: 'status-failed',
            cancelled: 'status-failed',
            refunded: 'status-pending',
        };
        return map[status] ?? 'status-pending';
    }

    _formatDate(isoStr) {
        if (!isoStr) return '—';
        const d = new Date(isoStr);
        return d.toLocaleDateString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    _getPlanFeatures(plan) {
        const p = plan.toUpperCase();
        const tb = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.BILLING);
        const counts = { FREE: 3, BASIC: 4, PREMIUM: 4, ENTERPRISE: 4 };
        const planKey = counts[p] !== undefined ? p : 'FREE';
        const n = counts[planKey];
        const featureList = [];
        for (let i = 1; i <= n; i += 1) {
            featureList.push(tb(`frontend_console.plan_${planKey}_f${i}`));
        }
        return {
            description: tb(`frontend_console.plan_${planKey}_description`),
            features: featureList,
        };
    }
}

customElements.define('billing-page', BillingPage);
