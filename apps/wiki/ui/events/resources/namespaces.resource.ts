/**
 * Рабочие пространства wiki — источник для переключателя в сайдбаре.
 *
 * Список тот же, что у Documents и Networkle (company workspaces компании),
 * но читается через собственный эндпоинт сервиса: у wiki своя авторизация и
 * свой контейнер, ходить в чужой BFF ради списка нельзя.
 */

import { createResourceCollection } from '@platform/lib/events/index.js';

export const wikiNamespacesResource = createResourceCollection({
    name: 'wiki/namespaces',
    baseUrl: '/wiki/api/v1/namespaces',
    idField: 'name',
    operations: ['list'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'wiki/namespaces': typeof wikiNamespacesResource;
    }
}
