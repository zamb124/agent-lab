/**
 * Sync Platform Namespaces — read-only список платформенных namespaces.
 *
 * Источник: shared KV `namespaces` (тот же, что использует CRM); Sync
 * получает их через свой backend-эндпоинт `/sync/api/v1/platform-namespaces`,
 * чтобы не зависеть от CRM HTTP-API.
 *
 * UI sidebar отображает этот список в едином `<select>` namespace; при
 * выборе глобально переключает `setPlatformNamespaceSelection` (общий с
 * CRM/Office/RAG). Создание namespace через sync — атомарное вместе с
 * SyncSpace (см. backend `_create_space.get_or_create`).
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

function _normalizeNamespace(item) {
    if (!item || typeof item !== 'object') return item;
    return Object.freeze({
        ...item,
        name: typeof item.name === 'string' ? item.name : '',
        description: typeof item.description === 'string' ? item.description : null,
        is_default: item.is_default === true,
    });
}

export const platformNamespacesResource = createResourceCollection({
    name: 'sync/platform_namespaces',
    baseUrl: '/sync/api/v1/platform-namespaces',
    idField: 'name',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    mapItem: _normalizeNamespace,
});
