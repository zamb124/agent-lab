/**
 * Billing Page - Управление биллингом и подпиской
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '@platform/lib/components/layout/page-header.js';

export class BillingPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .page-container {
                max-width: 1200px;
                margin: 0 auto;
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
                margin: 0;
            }

            .primary-button {
                width: 100%;
                padding: var(--space-3) var(--space-6);
                background: var(--accent);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: all var(--duration-fast);
                margin-top: var(--space-4);
            }

            .primary-button:hover {
                transform: scale(1.02);
                box-shadow: 0 8px 24px rgba(153, 166, 249, 0.4);
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

            .usage-section {
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
        }));
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._loadBilling();
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
                
                <button class="primary-button" @click=${this._onTopUpClick}>
                    ${tb('frontend_console.top_up')}
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
                
                ${plan === 'FREE' ? html`
                    <button class="primary-button" @click=${this._onUpgradeClick}>
                        ${tb('frontend_console.upgrade_pro')}
                    </button>
                ` : ''}
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
                
                <button class="primary-button" @click=${this._onSetBudgetClick}>
                    ${monthlyBudget > 0 ? tb('frontend_console.change_limit') : tb('frontend_console.set_limit')}
                </button>
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
            <div class="usage-section">
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

    _onTopUpClick() {
        const modal = document.createElement('topup-balance-modal');
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.addEventListener('topped-up', async () => {
            await this._reloadBilling();
            this.success(this.i18n.t('frontend_console.topup_success', {}, I18nNs.BILLING));
        });
    }

    async _reloadBilling() {
        FrontendStore.setBillingLoading(true);
        const billingService = this.services.get('billing');
        const [subscription, usage] = await Promise.all([
            billingService.getSubscription(),
            billingService.getUsageStats(),
        ]);
        FrontendStore.setBillingData(subscription, usage);
    }

    _onUpgradeClick() {
        this.info(this.i18n.t('frontend_console.upgrade_wip', {}, I18nNs.BILLING));
    }

    _onSetBudgetClick() {
        this.info(this.i18n.t('frontend_console.budget_wip', {}, I18nNs.BILLING));
    }
}

customElements.define('billing-page', BillingPage);
