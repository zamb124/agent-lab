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

const DASHBOARD_SERVICES = PLATFORM_SERVICES.filter((s) => s.id !== 'frontend');

/**
 * @param {string} nameKey
 * @returns {string}
 */
function descriptionKeyFromNameKey(nameKey) {
    if (typeof nameKey !== 'string' || !nameKey.endsWith('.name')) {
        throw new Error('dashboard-services-grid: nameKey must end with .name');
    }
    return `${nameKey.slice(0, -5)}description`;
}

export class DashboardServicesGrid extends PlatformElement {
    static i18nNamespace = 'frontend';

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
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
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: var(--space-5);
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
        this._countOps = DASHBOARD_SERVICES.map((svc) => this.useOp(svc.countOp));
        this._activeCompanyId = this.select((s) => s.auth.activeCompanyId);
        this._countsBootstrapped = false;
        this._prevCompanyId = null;
    }

    updated() {
        const cid = this._activeCompanyId.value;
        if (!this._countsBootstrapped) {
            this._countsBootstrapped = true;
            this._status.run(null);
            for (let i = 0; i < this._countOps.length; i++) {
                const svc = DASHBOARD_SERVICES[i];
                if (svc.id === 'litserve' && cid !== 'system') {
                    continue;
                }
                this._countOps[i].run(null);
            }
            this._prevCompanyId = cid;
            return;
        }
        if (cid !== this._prevCompanyId) {
            this._prevCompanyId = cid;
            const litIdx = DASHBOARD_SERVICES.findIndex((s) => s.id === 'litserve');
            if (litIdx >= 0 && cid === 'system') {
                this._countOps[litIdx].run(null);
            }
        }
    }

    _healthForService(_statusResult, healthName, activeCompanyId) {
        if (healthName === 'provider_litserve' && activeCompanyId !== 'system') {
            return { state: 'unhealthy', latencyMs: 0 };
        }
        return { state: 'healthy', latencyMs: 0 };
    }

    _metricValue(idx, metricKey, svcId, activeCompanyId) {
        if (svcId === 'litserve' && activeCompanyId !== 'system') {
            return this.t('console_home.stat_loading');
        }
        const op = this._countOps[idx];
        const result = op.lastResult;
        if (!result) return this.t('console_home.stat_loading');
        return this.t(metricKey, { count: result.total });
    }

    _serviceTiles(statusResult, activeCompanyId) {
        return DASHBOARD_SERVICES.map((svc, idx) => {
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
                    metric-value=${this._metricValue(idx, svc.metricKey, svc.id, activeCompanyId)}
                    health-state=${health.state}
                    latency-ms=${health.latencyMs}
                    ?disabled=${litserveLocked}
                ></dashboard-service-card>
            `;
        });
    }

    _serviceLaunchersHealthMap(statusResult, activeCompanyId) {
        const healthMap = Object.create(null);
        for (const svc of DASHBOARD_SERVICES) {
            const h = this._healthForService(statusResult, svc.healthName, activeCompanyId);
            healthMap[svc.id] = h.state;
        }
        return healthMap;
    }

    render() {
        const statusResult = this._status.lastResult;
        const activeCompanyId = this._activeCompanyId.value;
        const ids = DASHBOARD_SERVICES.map((s) => s.id);
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
