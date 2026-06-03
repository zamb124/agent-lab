/**
 * Ссылки на пользовательскую документацию (Zensical, docs/scenarios/...).
 * Статика из documentation-dist/ монтируется на /documentation/; у frontend дубль на /frontend/documentation/.
 */

const SCENARIO_SERVICES = new Set(['sync', 'flows', 'crm', 'rag', 'frontend']);

export function getDocumentationBasePath() {
    const p = window.location.pathname;
    if (p === '/frontend' || p.startsWith('/frontend/')) {
        return '/frontend/documentation/';
    }
    return '/documentation/';
}

export function getDocumentationScenarioServiceKey() {
    const segments = window.location.pathname.split('/').filter(Boolean);
    if (segments[0] === 'frontend' && segments.length >= 2) {
        const cand = segments[1];
        if (SCENARIO_SERVICES.has(cand)) {
            return cand;
        }
        return 'frontend';
    }
    if (segments.length >= 1) {
        const cand = segments[0];
        if (SCENARIO_SERVICES.has(cand)) {
            return cand;
        }
    }
    return 'frontend';
}

/**
 * @param {{ service?: string, tag?: string | null, slug?: string | null }} options
 *   service — ключ из pytest scenario / docs/scenarios/<service>/; по умолчанию из URL.
 *   tag — необязательный сегмент пути для старых групповых ссылок.
 *   slug — необязательный slug сценария. В сборке docs_prepare теги исходников
 *   становятся внутренней группировкой, поэтому публичный путь сценария:
 *   /scenarios/<service>/<slug>/.
 */
export function buildScenarioDocumentationUrl(options = {}) {
    const service = options.service ?? getDocumentationScenarioServiceKey();
    const tag = options.tag;
    const slug = options.slug;
    const base = getDocumentationBasePath();
    let path = `scenarios/${service}/`;
    if (typeof slug === 'string' && slug.trim()) {
        const seg = slug.trim().replace(/^\/+|\/+$/g, '');
        if (seg) {
            path = `scenarios/${service}/${seg}/`;
        }
    } else if (typeof tag === 'string' && tag.trim()) {
        const seg = tag.trim().replace(/^\/+|\/+$/g, '');
        if (seg) {
            path = `scenarios/${service}/${seg}/`;
        }
    }
    return new URL(path, `${window.location.origin}${base}`).href;
}
