/**
 * Dashboard stats — лёгкие счётчики по сервисам для витрины /dashboard.
 *
 * Каждый op запрашивает первую страницу соответствующего list-эндпоинта
 * (limit=1) и возвращает только `{ total }`. Никаких новых backend-контрактов:
 * берём `OffsetPage[T].total` существующих API. Documents считают сумму
 * `file_count` по каталогам, потому что у /documents catalogs возвращает
 * собственную модель без поля `total`.
 *
 * silent: ошибка попадает в slice.error через FAILED-событие фабрики,
 * карточка покажет «—» без поломки всей страницы.
 *
 * restMirror с `service: '<target>'` — это cross-service вызов из frontend
 * в другой сервис. Скрипт `check_command_rest_mirror.py` распознаёт
 * `service:` и не верифицирует path против локальных routes frontend (и не
 * даёт WARN/ERROR в strict).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const dashboardFlowsCountOp = createAsyncOp({
    name: 'frontend/dashboard_flows_count',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/', service: 'flows' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/flows/api/v1/flows/?limit=1&offset=0',
        });
        return { total: Number(data.total) };
    },
});

export const dashboardCrmNamespacesCountOp = createAsyncOp({
    name: 'frontend/dashboard_crm_namespaces_count',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces', service: 'crm' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/crm/api/v1/namespaces?limit=1&offset=0',
        });
        return { total: Number(data.total) };
    },
});

export const dashboardRagNamespacesCountOp = createAsyncOp({
    name: 'frontend/dashboard_rag_namespaces_count',
    silent: true,
    restMirror: { method: 'GET', path: '/rag/api/v1/namespaces', service: 'rag' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/rag/api/v1/namespaces?limit=1&offset=0',
        });
        return { total: Number(data.total) };
    },
});

export const dashboardSyncSpacesCountOp = createAsyncOp({
    name: 'frontend/dashboard_sync_spaces_count',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/namespaces', service: 'sync' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/sync/api/v1/namespaces?limit=1&offset=0',
        });
        return { total: Number(data.total) };
    },
});

export const dashboardDocumentsFilesCountOp = createAsyncOp({
    name: 'frontend/dashboard_documents_files_count',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs', service: 'office' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/documents/api/v1/catalogs',
        });
        const items = Array.isArray(data.items) ? data.items : [];
        const total = items.reduce((acc, c) => acc + Number(c.file_count), 0);
        return { total };
    },
});

export const dashboardLitserveModelsCountOp = createAsyncOp({
    name: 'frontend/dashboard_litserve_models_count',
    silent: true,
    restMirror: { method: 'GET', path: '/litserve/api/models', service: 'provider_litserve' },
    request: async () => {
        const data = await httpRequest({
            method: 'GET',
            url: '/litserve/api/models',
        });
        const items = Array.isArray(data.items) ? data.items : [];
        return { total: items.length };
    },
});
