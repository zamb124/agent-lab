/**
 * Единый каталог продуктов платформы для витрины (иконки, бренд, ключи i18n).
 * Метрики dashboard — поля metricField (поле `DashboardStats`) / metricKey (только frontend app).
 */

export const SERVICE_LOGO_BASE = '/static/core/assets/service_logos';

export interface PlatformServiceEntry {
    id: string;
    nameKey: string;
    logoSrc: string;
    brandFrom: string;
    brandTo: string;
    healthName: string;
    metricField: string | null;
    metricKey: string | null;
}

export const PLATFORM_SERVICES: readonly PlatformServiceEntry[] = Object.freeze([
    Object.freeze({
        id: 'flows',
        nameKey: 'apps.flows.name',
        logoSrc: `${SERVICE_LOGO_BASE}/agents_logo.svg`,
        brandFrom: '#7c3aed',
        brandTo: '#0ea5e9',
        healthName: 'flows',
        metricField: 'flows_total',
        metricKey: 'console_home.stat_flows_count',
    }),
    Object.freeze({
        id: 'crm',
        nameKey: 'apps.crm.name',
        logoSrc: `${SERVICE_LOGO_BASE}/crm_logo.svg`,
        brandFrom: '#ec4899',
        brandTo: '#f97316',
        healthName: 'crm',
        metricField: 'namespaces_total',
        metricKey: 'console_home.stat_namespaces_count',
    }),
    Object.freeze({
        id: 'rag',
        nameKey: 'apps.rag.name',
        logoSrc: `${SERVICE_LOGO_BASE}/rag_logo.svg`,
        brandFrom: '#10b981',
        brandTo: '#0ea5e9',
        healthName: 'rag',
        metricField: 'rag_namespaces_total',
        metricKey: 'console_home.stat_namespaces_count',
    }),
    Object.freeze({
        id: 'sync',
        nameKey: 'apps.sync.name',
        logoSrc: `${SERVICE_LOGO_BASE}/sync_logo.svg`,
        brandFrom: '#0ea5e9',
        brandTo: '#6366f1',
        healthName: 'sync',
        metricField: 'namespaces_total',
        metricKey: 'console_home.stat_spaces_count',
    }),
    Object.freeze({
        id: 'worktracker',
        nameKey: 'apps.worktracker.name',
        logoSrc: `${SERVICE_LOGO_BASE}/worktracker_logo.svg`,
        brandFrom: '#6366f1',
        brandTo: '#14b8a6',
        healthName: 'worktracker',
        metricField: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'documents',
        nameKey: 'apps.documents.name',
        logoSrc: `${SERVICE_LOGO_BASE}/documents_logo.svg`,
        brandFrom: '#f59e0b',
        brandTo: '#ef4444',
        healthName: 'office',
        metricField: 'documents_files_total',
        metricKey: 'console_home.stat_files_count',
    }),
    Object.freeze({
        id: 'wiki',
        nameKey: 'apps.wiki.name',
        logoSrc: `${SERVICE_LOGO_BASE}/wiki_logo.svg`,
        brandFrom: '#8b5cf6',
        brandTo: '#22d3ee',
        healthName: 'wiki',
        metricField: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'stock',
        nameKey: 'apps.stock.name',
        logoSrc: `${SERVICE_LOGO_BASE}/stock_logo.svg`,
        brandFrom: '#22c55e',
        brandTo: '#0ea5e9',
        healthName: 'stock',
        metricField: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'shop',
        nameKey: 'apps.shop.name',
        logoSrc: `${SERVICE_LOGO_BASE}/shop_logo.svg`,
        brandFrom: '#eab308',
        brandTo: '#f97316',
        healthName: 'shop',
        metricField: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'frontend',
        nameKey: 'apps.frontend.name',
        logoSrc: `${SERVICE_LOGO_BASE}/frontend_logo.svg`,
        brandFrom: '#6366f1',
        brandTo: '#0ea5e9',
        healthName: 'frontend',
        metricField: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'litserve',
        nameKey: 'apps.litserve.name',
        logoSrc: `${SERVICE_LOGO_BASE}/rag_logo.svg`,
        brandFrom: '#8b5cf6',
        brandTo: '#d946ef',
        healthName: 'provider_litserve',
        metricField: 'litserve_models_total',
        metricKey: 'console_home.stat_models_count',
    }),
    Object.freeze({
        id: 'grafana',
        nameKey: 'apps.grafana.name',
        logoSrc: `${SERVICE_LOGO_BASE}/frontend_logo.svg`,
        brandFrom: '#f97316',
        brandTo: '#f59e0b',
        healthName: 'grafana',
        metricField: null,
        metricKey: null,
    }),
]);
