/**
 * Office BFF требует заголовок `X-Platform-Namespace` на все запросы под
 * `/documents/api/v1`. Каталоги и документы жёстко привязаны к namespace,
 * режим «все пространства» в Документах запрещён — `office-sidebar`
 * автоматически выбирает первый namespace, если выбора ещё нет.
 *
 * Источник правды о выборе — `state.ui.namespace`; для http-слоя читаем
 * через `getActivePlatformNamespaceName(companyId)`. Утилита возвращает
 * `default` только в bootstrap-окне (между регистрацией фабрики и
 * автоселектом sidebar) — backend всё равно валидирует, что namespace
 * реально существует в активной компании (`_require_explicit_namespace`).
 *
 * Применение в фабрике:
 *
 *   request: ({ payload, ctx }) => httpRequest({
 *       method: 'GET',
 *       url: '/documents/api/v1/...',
 *       headers: nsHeader(ctx),
 *   }),
 */

import { getActivePlatformNamespaceName } from '@platform/lib/utils/platform-namespace.js';

export function nsHeader(ctx) {
    if (!ctx || typeof ctx.getState !== 'function') {
        throw new Error('nsHeader: ctx with getState() required');
    }
    const user = ctx.getState().auth.user;
    const companyId = user && typeof user.company_id === 'string' ? user.company_id : '';
    return { 'X-Platform-Namespace': getActivePlatformNamespaceName(companyId) };
}
