/**
 * Статистика dashboard — одна команда `frontend/dashboard/stats_requested`:
 * бэкенд собирает счётчики у владельцев (flows, namespaces, RAG, Documents,
 * каталог моделей) и отдаёт `DashboardStats`. Карточки витрины читают поля
 * результата по `metricField` каталога `PLATFORM_SERVICES`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const dashboardStatsOp = createAsyncOp({
    name: 'frontend/dashboard_stats',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'frontend/dashboard/stats_requested',
    restMirror: { method: 'GET', path: '/frontend/api/dashboard/stats' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/dashboard_stats': typeof dashboardStatsOp;
    }
}
