/**
 * Утилиты для синхронизации URL с состоянием flows UI (deep linking).
 *
 * Схема URL:
 *   /flows/{flow_id}?skill=...&session=...&edit=1
 */

/**
 * Прочитать начальное состояние из текущего URL.
 * @returns {{ flowId: string|null, skillId: string|null, sessionId: string|null, edit: boolean }}
 */
export function readUrlState() {
    const path = window.location.pathname.replace(/\/$/, '') || '';
    const urlParts = path.split('/');
    const lastSegment = urlParts[urlParts.length - 1];
    const flowId = (lastSegment && lastSegment !== 'flows') ? lastSegment : null;

    const params = new URLSearchParams(window.location.search);
    const skillId = params.get('skill') || null;
    const sessionId = params.get('session') || null;
    const edit = params.get('edit') === '1';

    return { flowId, skillId, sessionId, edit };
}

/**
 * Обновить URL без перезагрузки страницы.
 * @param {Object} opts
 * @param {string|null} opts.flowId
 * @param {string|null} [opts.skillId]
 * @param {string|null} [opts.sessionId]
 * @param {boolean}     [opts.edit]
 */
export function updateUrl({ flowId, skillId = null, sessionId = null, edit = false }) {
    if (!flowId) return;

    const path = `/flows/${flowId}`;
    const params = new URLSearchParams();

    if (skillId) params.set('skill', skillId);
    if (sessionId) params.set('session', sessionId);
    if (edit) params.set('edit', '1');

    const qs = params.toString();
    const url = qs ? `${path}?${qs}` : path;

    if (url !== window.location.pathname + window.location.search) {
        window.history.replaceState({}, '', url);
    }
}

/**
 * Добавить или убрать отдельный query-параметр, сохраняя остальные.
 * @param {string} key
 * @param {string|null} value  — null для удаления
 */
export function setUrlParam(key, value) {
    const params = new URLSearchParams(window.location.search);
    if (value != null) {
        params.set(key, value);
    } else {
        params.delete(key);
    }
    const qs = params.toString();
    const url = qs
        ? `${window.location.pathname}?${qs}`
        : window.location.pathname;

    if (url !== window.location.pathname + window.location.search) {
        window.history.replaceState({}, '', url);
    }
}

/**
 * Удалить один или несколько query-параметров.
 * @param {...string} keys
 */
export function removeUrlParams(...keys) {
    const params = new URLSearchParams(window.location.search);
    let changed = false;
    for (const key of keys) {
        if (params.has(key)) {
            params.delete(key);
            changed = true;
        }
    }
    if (!changed) return;

    const qs = params.toString();
    const url = qs
        ? `${window.location.pathname}?${qs}`
        : window.location.pathname;
    window.history.replaceState({}, '', url);
}
