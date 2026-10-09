/**
 * dashboard-services-grid — витрина из сервисных карточек.
 *
 * Список сервисов и бренд — единый каталог platform-services-catalog;
 * метрики и health — фабрики frontend.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { PLATFORM_SERVICES } from '@platform/lib/utils/platform-services-catalog.js';
import { buildServiceEntryUrl } from '@platform/lib/utils/build-service-entry-url.js';
import '@platform/lib/components/platform-services-launcher.js';
import './dashboard-service-card.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const DASHBOARD_SERVICES = PLATFORM_SERVICES.filter((s) => s.id !== 'frontend');
const SYSTEM_ONLY_SERVICE_IDS = new Set(['grafana', 'litserve']);

/**
 * @param {string} nameKey
 * @returns {string}
 */
function descriptionKeyFromNameKey(nameKey: string) {
    if (typeof nameKey !== 'string' || !nameKey.endsWith('.name')) {
        throw new Error('dashboard-services-grid: nameKey must end with .name');
    }
    return nameKey.replace(/\.name$/, '.description');
}

export class DashboardServicesGrid extends PlatformElement {
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }
            .header { margin-bottom: var(--space-5); }
            .title {
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0;
            }
            .subtitle {
                margin-top: var(--space-2);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .cards-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
                gap: var(--space-5);
                min-width: 0;
                width: 100%;
            }
            .launchers {
                display: none;
            }
            @media (max-width: 767px) {
                .header { margin-bottom: var(--space-3); }
                .title { font-size: var(--text-xl); }
                .subtitle {
                    margin-top: var(--space-1);
                    font-size: var(--text-xs);
                    line-height: 1.35;
                }
                .cards-grid { display: none; }
                .launchers {
                    display: block;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._status = this.useOp('frontend/services_status_load');
        this._stats = this.useOp('frontend/dashboard_stats');
        this._activeCompanyId = this.select((s: Record<string, any>) => s.auth.activeCompanyId);
        this._countsBootstrapped = false;
        this._prevCompanyId = null;
    }
    private _status: OpController;
    private _stats: OpController;
    private _activeCompanyId: SelectController<any>;
    private _countsBootstrapped: boolean;
    private _prevCompanyId: any;


    _visibleServices(activeCompanyId: string | null) {
        return DASHBOARD_SERVICES.filter((svc) => activeCompanyId === 'system' || !SYSTEM_ONLY_SERVICE_IDS.has(svc.id));
    }

    override updated() {
        const cid = this._activeCompanyId.value as string | null;
        if (!this._countsBootstrapped) {
            this._countsBootstrapped = true;
            this._status.run(null);
            this._stats.run(null);
            this._prevCompanyId = cid;
            return;
        }
        if (cid !== this._prevCompanyId) {
            this._prevCompanyId = cid;
            this._stats.run(null);
        }
    }

    _healthForService(_statusResult: Record<string, any>, healthName: string, activeCompanyId: string | null) {
        if (healthName === 'provider_litserve' && activeCompanyId !== 'system') {
            return { state: 'unhealthy', latencyMs: 0 };
        }
        return { state: 'healthy', latencyMs: 0 };
    }

    _metricValue(metricField: string | null, metricKey: string | null, svcId: string, activeCompanyId: string | null) {
        if (!metricKey || !metricField) {
            return '—';
        }
        if (svcId === 'litserve' && activeCompanyId !== 'system') {
            return '—';
        }
        const stats = this._stats.lastResult;
        if (!stats) return '—';
        const count = (stats as Record<string, any>)[metricField];
        if (typeof count !== 'number') return '—';
        return this.t(metricKey, { count });
    }

    _serviceTiles(statusResult: any, activeCompanyId: string | null) {
        const visible = this._visibleServices(activeCompanyId);
        return visible.map((svc) => {
            const health = this._healthForService(statusResult, svc.healthName, activeCompanyId);
            const litserveLocked = svc.id === 'litserve' && activeCompanyId !== 'system';
            const descriptionKey = descriptionKeyFromNameKey(svc.nameKey);
            return html`
                <dashboard-service-card
                    svc-id=${svc.id}
                    name-key=${svc.nameKey}
                    description-key=${descriptionKey}
                    logo-src=${svc.logoSrc}
                    href=${buildServiceEntryUrl(svc.id)}
                    brand-from=${svc.brandFrom}
                    brand-to=${svc.brandTo}
                    metric-value=${this._metricValue(svc.metricField, svc.metricKey, svc.id, activeCompanyId)}
                    health-state=${health.state}
                    latency-ms=${health.latencyMs}
                    ?disabled=${litserveLocked}
                ></dashboard-service-card>
            `;
        });
    }

    _serviceLaunchersHealthMap(statusResult: any, activeCompanyId: string) {
        const healthMap = Object.create(null);
        for (const svc of this._visibleServices(activeCompanyId)) {
            const h = this._healthForService(statusResult, svc.healthName, activeCompanyId);
            healthMap[svc.id] = h.state;
        }
        return healthMap;
    }

    override render(): TemplateResult {
        const statusResult = this._status.lastResult;
        const activeCompanyId = this._activeCompanyId.value;
        const ids = this._visibleServices(activeCompanyId).map((s) => s.id);
        const healthByServiceId = this._serviceLaunchersHealthMap(statusResult, activeCompanyId);
        return html`
            <div class="header">
                <h2 class="title">${this.t('console_home.services_title')}</h2>
                <div class="subtitle">${this.t('console_home.services_subtitle')}</div>
            </div>
            <div class="cards-grid">
                ${this._serviceTiles(statusResult, activeCompanyId)}
            </div>
            <div class="launchers">
                <platform-services-launcher
                    layout="compact"
                    .includeServiceIds=${ids}
                    .healthByServiceId=${healthByServiceId}
                ></platform-services-launcher>
            </div>
        `;
    }
}

customElements.define('dashboard-services-grid', DashboardServicesGrid);
