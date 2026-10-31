/**
 * Ссылки на пользовательскую документацию (Zensical, docs/scenarios/...).
 * Статика из documentation-dist/ монтируется на /documentation/; у frontend дубль на /frontend/documentation/.
 */

const SCENARIO_SERVICES = new Set(['sync', 'flows', 'crm', 'rag', 'frontend', 'platform', 'office']);

function normalizeDocumentationLocale(locale: unknown): string {
    if (typeof locale !== 'string') {
        return 'ru';
    }
    const normalized = locale.trim().toLowerCase();
    if (normalized === 'en') {
        return 'en';
    }
    return 'ru';
}

function documentationLocalePrefix(locale: unknown): string {
    return normalizeDocumentationLocale(locale) === 'en' ? 'en/' : '';
}

/**
 * @param {{ locale?: string }} [options]
 */
export function getDocumentationBasePath(options: { locale?: string | undefined } = {}): string {
    const localePrefix = documentationLocalePrefix(options.locale);
    const p = window.location.pathname;
    if (p === '/frontend' || p.startsWith('/frontend/')) {
        return `/frontend/documentation/${localePrefix}`;
    }
    return `/documentation/${localePrefix}`;
}

export function getDocumentationScenarioServiceKey(): string {
    const segments = window.location.pathname.split('/').filter(Boolean);
    if (segments[0] === 'frontend' && segments.length >= 2) {
        const cand = segments[1] ?? 'frontend';
        if (SCENARIO_SERVICES.has(cand)) {
            return cand;
        }
        return 'frontend';
    }
    if (segments.length >= 1) {
        const cand = segments[0] ?? 'frontend';
        if (SCENARIO_SERVICES.has(cand)) {
            return cand;
        }
    }
    return 'frontend';
}

/**
 * Преобразует путь вида /documentation/scenarios/... в locale-aware URL.
 * @param {string} href
 * @param {{ locale?: string }} [options]
 */
export function resolveDocumentationHref(href: string, options: { locale?: string } = {}): string {
    const raw = typeof href === 'string' ? href.trim() : '';
    if (raw === '') {
        return raw;
    }
    const localePrefix = documentationLocalePrefix(options.locale);
    if (localePrefix === '') {
        return raw;
    }
    if (raw.startsWith('/frontend/documentation/') && !raw.startsWith('/frontend/documentation/en/')) {
        return raw.replace('/frontend/documentation/', '/frontend/documentation/en/');
    }
    if (raw.startsWith('/documentation/') && !raw.startsWith('/documentation/en/')) {
        return raw.replace('/documentation/', '/documentation/en/');
    }
    return raw;
}

/**
 * @param {{ service?: string, tag?: string | null, slug?: string | null, locale?: string }} options
 *   service — ключ из pytest scenario / docs/scenarios/<service>/; по умолчанию из URL.
 *   tag — необязательный сегмент пути для старых групповых ссылок.
 *   slug — необязательный slug сценария. В сборке docs_prepare теги исходников
 *   становятся внутренней группировкой, поэтому публичный путь сценария:
 *   /scenarios/<service>/<slug>/.
 */
export function buildScenarioDocumentationUrl(options: { service?: string; tag?: string | null; slug?: string | null; locale?: string } = {}): string {
    const service = options.service ?? getDocumentationScenarioServiceKey();
    const tag = options.tag;
    const slug = options.slug;
    const base = getDocumentationBasePath({ locale: options.locale });
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
