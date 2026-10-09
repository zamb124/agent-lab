/**
 * Заголовок `X-Platform-Namespace` для сервисов, у которых данные жёстко
 * привязаны к рабочему пространству (Documents, Wiki).
 *
 * Источник правды о выборе — `state.ui.namespace`; здесь только чтение для
 * http-слоя. В bootstrap-окне (между регистрацией фабрики и автовыбором в
 * сайдбаре) вернётся `default` — backend всё равно проверяет, что пространство
 * существует в активной компании, поэтому подстановка не ослабляет изоляцию.
 *
 * @example
 * request: ({ ctx }) => httpRequest({ url, headers: platformNamespaceHeader(ctx) })
 */

import { getActivePlatformNamespaceName } from './platform-namespace.js';

/**
 * @param {{ getState: () => object }} ctx контекст фабрики
 * @param {string} [explicitNamespace] явное пространство (перемещение между ними)
 * @returns {{ 'X-Platform-Namespace': string }}
 */
export function platformNamespaceHeader(ctx: { getState: () => unknown }, explicitNamespace = ''): { 'X-Platform-Namespace': string } {
    if (typeof explicitNamespace === 'string' && explicitNamespace.trim().length > 0) {
        return { 'X-Platform-Namespace': explicitNamespace.trim() };
    }
    if (!ctx || typeof ctx.getState !== 'function') {
        throw new Error('platformNamespaceHeader: требуется ctx с getState()');
    }
    const state = ctx.getState() as { auth?: { user?: { company_id?: unknown } | null } };
    const user = state.auth ? state.auth.user : null;
    const companyId = user && typeof user.company_id === 'string' ? user.company_id : '';
    return { 'X-Platform-Namespace': getActivePlatformNamespaceName(companyId) };
}
