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
import { isPlainRecord } from '@platform/lib/events/payload.js';

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
        this._activeCompanyId = this.select((s) => s.auth.activeCompanyId);
        this._locale = this.select((s) => {
            const locale = s.i18n.locale;
            if (locale.length === 0) {
                throw new Error('dashboard-stat-strip: locale required');
            }
            return locale;
        });
        this._loaded = false;
    }
    private _subscription: OpController;
    private _usage: OpController;
    private _status: OpController;
    private _activeCompanyId: SelectController<string | null>;
    private _locale: SelectController<string>;
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

    _planValue(subscription: unknown) {
        if (!isPlainRecord(subscription) || typeof subscription.plan !== 'string' || subscription.plan.length === 0) {
            return '—';
        }
        return subscription.plan.charAt(0).toUpperCase() + subscription.plan.slice(1);
    }

    _balanceValue(subscription: unknown) {
        const formatted = isPlainRecord(subscription) ? this._formatCurrency(subscription.balance) : null;
        if (formatted === null) return '—';
        return `${formatted} ${this.t('console_home.currency_rub')}`;
    }

    _spentValue(subscription: unknown) {
        const formatted = isPlainRecord(subscription) ? this._formatCurrency(subscription.current_month_spent) : null;
        if (formatted === null) return '—';
        return `${formatted} ${this.t('console_home.currency_rub')}`;
    }

    _servicesValue(statusResult: unknown, activeCompanyId: string | null) {
        if (!isPlainRecord(statusResult) || !Array.isArray(statusResult.items)) {
            return '—';
        }
        const items: unknown[] = [];
        for (const item of statusResult.items) items.push(item);
        const total = items.length;
        if (activeCompanyId === 'system') {
            return `${total} / ${total}`;
        }
        const hasLinnexModelsInternalService = items.some((item) => isPlainRecord(item) && item.name === 'provider_litserve');
        const online = hasLinnexModelsInternalService ? total - 1 : total;
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
