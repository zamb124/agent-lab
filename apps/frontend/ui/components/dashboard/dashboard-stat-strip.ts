/**
 * dashboard-stat-strip — четыре сводных метрики:
 *   - текущий тариф;
 *   - баланс компании;
 *   - потрачено в этом месяце;
 *   - количество здоровых сервисов.
 *
 * Container: дёргает три ops, маппит результат в plain-props и отдаёт
 * пресентейшнл-плиткам.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import './dashboard-stat-tile.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

export class DashboardStatStrip extends PlatformElement {
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .strip {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: var(--space-4);
            }
        `,
    ];

    constructor() {
        super();
        this._subscription = this.useOp('frontend/billing_subscription');
        this._usage = this.useOp('frontend/billing_usage');
        this._status = this.useOp('frontend/services_status_load');
        this._activeCompanyId = this.select((s: Record<string, any>) => s.auth.activeCompanyId);
        this._locale = this.select((s: Record<string, any>) => typeof s.i18n.locale === 'string' && s.i18n.locale.length > 0 ? s.i18n.locale : 'en');
        this._loaded = false;
    }
    private _subscription: OpController;
    private _usage: OpController;
    private _status: OpController;
    private _activeCompanyId: SelectController<any>;
    private _locale: SelectController<any>;
    private _loaded: boolean;


    _formatCurrency(value: unknown) {
        if (value === null || value === undefined || value === '') {
            return null;
        }
        const n = Number(value);
        if (!Number.isFinite(n)) {
            return null;
        }
        return formatPlatformNumber(n, this._locale.value, { maximumFractionDigits: 2 });
    }

    override updated() {
        if (this._loaded) return;
        this._loaded = true;
        this._subscription.run(null);
        this._usage.run(null);
        this._status.run(null);
    }

    _planValue(subscription: any) {
        if (subscription && typeof subscription.plan === 'string' && subscription.plan.length > 0) {
            return subscription.plan.charAt(0).toUpperCase() + subscription.plan.slice(1);
        }
        return '—';
    }

    _balanceValue(subscription: any) {
        const formatted = subscription ? this._formatCurrency(subscription.balance) : null;
        if (formatted === null) return '—';
        return `${formatted} ${this.t('console_home.currency_rub')}`;
    }

    _spentValue(subscription: any) {
        const formatted = subscription ? this._formatCurrency(subscription.current_month_spent) : null;
        if (formatted === null) return '—';
        return `${formatted} ${this.t('console_home.currency_rub')}`;
    }

    _servicesValue(statusResult: any, activeCompanyId: string) {
        if (!statusResult || !Array.isArray(statusResult.items)) {
            return '—';
        }
        const items = statusResult.items;
        const total = items.length;
        if (activeCompanyId === 'system') {
            return `${total} / ${total}`;
        }
        const hasHumanitecModelsInternalService = items.some((s: Record<string, any>) => s.name === 'provider_litserve');
        const online = hasHumanitecModelsInternalService ? total - 1 : total;
        return `${online} / ${total}`;
    }

    override render(): TemplateResult {
        const subscription = this._subscription.lastResult;
        const statusResult = this._status.lastResult;
        const activeCompanyId = this._activeCompanyId.value;
        return html`
            <div class="strip">
                <dashboard-stat-tile
                    icon="target"
                    tone="accent"
                    label=${this.t('console_home.stat_plan')}
                    value=${this._planValue(subscription)}
                ></dashboard-stat-tile>
                <dashboard-stat-tile
                    icon="chart"
                    tone="success"
                    label=${this.t('console_home.stat_balance')}
                    value=${this._balanceValue(subscription)}
                ></dashboard-stat-tile>
                <dashboard-stat-tile
                    icon="schedule"
                    tone="warning"
                    label=${this.t('console_home.stat_spent_month')}
                    value=${this._spentValue(subscription)}
                ></dashboard-stat-tile>
                <dashboard-stat-tile
                    icon="server"
                    tone="info"
                    label=${this.t('console_home.stat_services_online')}
                    value=${this._servicesValue(statusResult, activeCompanyId)}
                ></dashboard-stat-tile>
            </div>
        `;
    }
}

customElements.define('dashboard-stat-strip', DashboardStatStrip);
