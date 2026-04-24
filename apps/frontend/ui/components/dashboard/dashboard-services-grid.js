/**
 * dashboard-services-grid — витрина из сервисных карточек.
 *
 * Container: дёргает counts ops по каждому сервису и общий health,
 * собирает props для пресентейшнл-карточек. Сервисы и их бренд-цвета —
 * константный массив локально, чтобы каждая правка дизайна была
 * сконцентрирована в одном файле.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './dashboard-service-card.js';

const SERVICES = Object.freeze([
    Object.freeze({
        svcId: 'flows',
        nameKey: 'apps.flows.name',
        descriptionKey: 'apps.flows.description',
        logoSrc: '/static/core/assets/service_logos/agents_logo.svg',
        href: '/flows',
        brandFrom: '#7c3aed',
        brandTo: '#0ea5e9',
        countOp: 'frontend/dashboard_flows_count',
        metricKey: 'console_home.stat_flows_count',
        healthName: 'flows',
    }),
    Object.freeze({
        svcId: 'crm',
        nameKey: 'apps.crm.name',
        descriptionKey: 'apps.crm.description',
        logoSrc: '/static/core/assets/service_logos/crm_logo.svg',
        href: '/crm',
        brandFrom: '#ec4899',
        brandTo: '#f97316',
        countOp: 'frontend/dashboard_crm_namespaces_count',
        metricKey: 'console_home.stat_namespaces_count',
        healthName: 'crm',
    }),
    Object.freeze({
        svcId: 'rag',
        nameKey: 'apps.rag.name',
        descriptionKey: 'apps.rag.description',
        logoSrc: '/static/core/assets/service_logos/rag_logo.svg',
        href: '/rag',
        brandFrom: '#10b981',
        brandTo: '#0ea5e9',
        countOp: 'frontend/dashboard_rag_namespaces_count',
        metricKey: 'console_home.stat_namespaces_count',
        healthName: 'rag',
    }),
    Object.freeze({
        svcId: 'sync',
        nameKey: 'apps.sync.name',
        descriptionKey: 'apps.sync.description',
        logoSrc: '/static/core/assets/service_logos/sync_logo.svg',
        href: '/sync',
        brandFrom: '#0ea5e9',
        brandTo: '#6366f1',
        countOp: 'frontend/dashboard_sync_spaces_count',
        metricKey: 'console_home.stat_spaces_count',
        healthName: 'sync',
    }),
    Object.freeze({
        svcId: 'documents',
        nameKey: 'apps.documents.name',
        descriptionKey: 'apps.documents.description',
        logoSrc: '/static/core/assets/service_logos/documents_logo.svg',
        href: '/documents',
        brandFrom: '#f59e0b',
        brandTo: '#ef4444',
        countOp: 'frontend/dashboard_documents_files_count',
        metricKey: 'console_home.stat_files_count',
        healthName: 'office',
    }),
    Object.freeze({
        svcId: 'litserve',
        nameKey: 'apps.litserve.name',
        descriptionKey: 'apps.litserve.description',
        logoSrc: '/static/core/assets/service_logos/rag_logo.svg',
        href: '/litserve',
        brandFrom: '#8b5cf6',
        brandTo: '#d946ef',
        countOp: 'frontend/dashboard_litserve_models_count',
        metricKey: 'console_home.stat_models_count',
        healthName: 'provider_litserve',
    }),
]);

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
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: var(--space-5);
            }
        `,
    ];

    constructor() {
        super();
        this._status = this.useOp('frontend/services_status_load');
        this._countOps = SERVICES.map((svc) => this.useOp(svc.countOp));
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
                const svc = SERVICES[i];
                if (svc.svcId === 'litserve' && cid !== 'system') {
                    continue;
                }
                this._countOps[i].run(null);
            }
            this._prevCompanyId = cid;
            return;
        }
        if (cid !== this._prevCompanyId) {
            this._prevCompanyId = cid;
            const litIdx = SERVICES.findIndex((s) => s.svcId === 'litserve');
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

    render() {
        const statusResult = this._status.lastResult;
        const activeCompanyId = this._activeCompanyId.value;
        return html`
            <div class="header">
                <h2 class="title">${this.t('console_home.services_title')}</h2>
                <div class="subtitle">${this.t('console_home.services_subtitle')}</div>
            </div>
            <div class="grid">
                ${SERVICES.map((svc, idx) => {
                    const health = this._healthForService(statusResult, svc.healthName, activeCompanyId);
                    const litserveLocked = svc.svcId === 'litserve' && activeCompanyId !== 'system';
                    return html`
                        <dashboard-service-card
                            svc-id=${svc.svcId}
                            name-key=${svc.nameKey}
                            description-key=${svc.descriptionKey}
                            logo-src=${svc.logoSrc}
                            href=${svc.href}
                            brand-from=${svc.brandFrom}
                            brand-to=${svc.brandTo}
                            metric-value=${this._metricValue(idx, svc.metricKey, svc.svcId, activeCompanyId)}
                            health-state=${health.state}
                            latency-ms=${health.latencyMs}
                            ?disabled=${litserveLocked}
                        ></dashboard-service-card>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('dashboard-services-grid', DashboardServicesGrid);
