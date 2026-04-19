/**
 * Office BFF требует заголовок `X-Platform-Namespace` на все запросы под
 * `/documents/api/v1`. Источник правды о выборе namespace — `state.ui.namespace`
 * (см. core `reducers/ui.js`); для http-слоя удобнее читать через
 * `getActivePlatformNamespaceName(companyId)` — одинаковая семантика, и при
 * старте до инициализации bus (когда фабрика уже регистрируется, а
 * пользователь ещё не загружен) утилита сама падает в значение `default`.
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
