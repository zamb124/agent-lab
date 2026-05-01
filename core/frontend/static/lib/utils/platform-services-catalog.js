/**
 * Единый каталог продуктов платформы для витрины (иконки, бренд, ключи i18n).
 * Метрики dashboard — поля countOp / metricKey (только frontend app).
 */

export const SERVICE_LOGO_BASE = '/static/core/assets/service_logos';

export const PLATFORM_SERVICES = Object.freeze([
    Object.freeze({
        id: 'flows',
        nameKey: 'apps.flows.name',
        logoSrc: `${SERVICE_LOGO_BASE}/agents_logo.svg`,
        brandFrom: '#7c3aed',
        brandTo: '#0ea5e9',
        healthName: 'flows',
        countOp: 'frontend/dashboard_flows_count',
        metricKey: 'console_home.stat_flows_count',
    }),
    Object.freeze({
        id: 'crm',
        nameKey: 'apps.crm.name',
        logoSrc: `${SERVICE_LOGO_BASE}/crm_logo.svg`,
        brandFrom: '#ec4899',
        brandTo: '#f97316',
        healthName: 'crm',
        countOp: 'frontend/dashboard_crm_namespaces_count',
        metricKey: 'console_home.stat_namespaces_count',
    }),
    Object.freeze({
        id: 'rag',
        nameKey: 'apps.rag.name',
        logoSrc: `${SERVICE_LOGO_BASE}/rag_logo.svg`,
        brandFrom: '#10b981',
        brandTo: '#0ea5e9',
        healthName: 'rag',
        countOp: 'frontend/dashboard_rag_namespaces_count',
        metricKey: 'console_home.stat_namespaces_count',
    }),
    Object.freeze({
        id: 'sync',
        nameKey: 'apps.sync.name',
        logoSrc: `${SERVICE_LOGO_BASE}/sync_logo.svg`,
        brandFrom: '#0ea5e9',
        brandTo: '#6366f1',
        healthName: 'sync',
        countOp: 'frontend/dashboard_sync_spaces_count',
        metricKey: 'console_home.stat_spaces_count',
    }),
    Object.freeze({
        id: 'documents',
        nameKey: 'apps.documents.name',
        logoSrc: `${SERVICE_LOGO_BASE}/documents_logo.svg`,
        brandFrom: '#f59e0b',
        brandTo: '#ef4444',
        healthName: 'office',
        countOp: 'frontend/dashboard_documents_files_count',
        metricKey: 'console_home.stat_files_count',
    }),
    Object.freeze({
        id: 'frontend',
        nameKey: 'apps.frontend.name',
        logoSrc: `${SERVICE_LOGO_BASE}/frontend_logo.svg`,
        brandFrom: '#6366f1',
        brandTo: '#0ea5e9',
        healthName: 'frontend',
        countOp: null,
        metricKey: null,
    }),
    Object.freeze({
        id: 'litserve',
        nameKey: 'apps.litserve.name',
        logoSrc: `${SERVICE_LOGO_BASE}/rag_logo.svg`,
        brandFrom: '#8b5cf6',
        brandTo: '#d946ef',
        healthName: 'provider_litserve',
        countOp: 'frontend/dashboard_litserve_models_count',
        metricKey: 'console_home.stat_models_count',
    }),
    Object.freeze({
        id: 'grafana',
        nameKey: 'apps.grafana.name',
        logoSrc: `${SERVICE_LOGO_BASE}/frontend_logo.svg`,
        brandFrom: '#f97316',
        brandTo: '#f59e0b',
        healthName: 'grafana',
        countOp: null,
        metricKey: null,
    }),
]);
