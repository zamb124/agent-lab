/**
 * Согласовано с core.utils.domain.extract_subdomain / extract_base_domain.
 * Используется, чтобы не держать консоль и сервисы на apex без субдомена компании.
 */

import {
    getCompanyHostContext,
    buildCompanySubdomainUrl,
} from './company-url.js';

const SUPPORTED_PRODUCTION = ['humanitec.ru', 'agents-lab.ru'];

/**
 * @param {string} hostname
 * @returns {string}
 */
function extractBaseDomain(hostname) {
    const h = hostname.toLowerCase();
    if (h === 'localhost' || h.endsWith('.localhost')) {
        return 'localhost';
    }
    if (h === 'lvh.me' || h.endsWith('.lvh.me')) {
        return 'lvh.me';
    }
    if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(h)) {
        return h;
    }
    for (const d of SUPPORTED_PRODUCTION) {
        if (h === d || h.endsWith(`.${d}`)) {
            return d;
        }
    }
    return 'humanitec.ru';
}

/**
 * @param {string} hostname
 * @returns {string | null} субдомен или null (apex / www / bare dev host)
 */
export function extractSubdomainFromHostname(hostname) {
    if (typeof hostname !== 'string' || hostname.length === 0) {
        throw new Error('extractSubdomainFromHostname: hostname required');
    }
    const h = hostname.toLowerCase();
    const base = extractBaseDomain(h);
    if (h === base || h === `www.${base}`) {
        return null;
    }
    if (h.endsWith(`.${base}`)) {
        const sub = h.slice(0, h.length - (`.${base}`).length);
        if (sub.length > 0) {
            return sub;
        }
    }
    return null;
}

/**
 * @param {object} user
 * @param {ReadonlyArray<{ company_id: string, subdomain?: string }>} companiesList
 * @returns {string | null}
 */
export function resolveActiveCompanySubdomain(user, companiesList) {
    if (!user) {
        return null;
    }
    if (!Array.isArray(companiesList)) {
        throw new Error('resolveActiveCompanySubdomain: companiesList must be an array');
    }
    let activeId;
    if (typeof user.company_id === 'string' && user.company_id.length > 0) {
        activeId = user.company_id;
    } else if (user.raw && typeof user.raw.company_id === 'string' && user.raw.company_id.length > 0) {
        activeId = user.raw.company_id;
    } else {
        return null;
    }
    const entry = companiesList.find((c) => c.company_id === activeId);
    if (!entry) {
        return null;
    }
    if (typeof entry.subdomain === 'string' && entry.subdomain.length > 0) {
        return entry.subdomain;
    }
    return null;
}

/**
 * URL на «оболочку» (тот же baseDomain), без субдомена — для /select-company.
 *
 * @param {string} path
 * @returns {string}
 */
export function buildShellOriginPathUrl(path) {
    const ctx = getCompanyHostContext();
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${ctx.protocol}://${ctx.baseDomain}${ctx.portSuffix}${normalizedPath}`;
}

/**
 * @param {string | null} hostSubdomain
 * @param {string} activeCompanySubdomain
 * @returns {boolean}
 */
function _companySubdomainMatchesHost(hostSubdomain, activeCompanySubdomain) {
    const want = String(activeCompanySubdomain).trim().toLowerCase();
    if (want.length === 0) {
        return false;
    }
    if (hostSubdomain === null) {
        return false;
    }
    return String(hostSubdomain).trim().toLowerCase() === want;
}

/**
 * @param {{ status: string, user: object | null }} auth
 * @param {ReadonlyArray<{ company_id: string, subdomain?: string }>} companiesList
 * @param {boolean} companiesLoading
 * @param {{ loadCompanies: () => void }} [handlers]
 * @param {string} [pathForCompanySubdomain] при наличии субдомена: перейти на этот path (например `/dashboard`), иначе берётся текущий path
 * @returns {'ok' | 'wait' | 'replaced' | 'replaced_select'}
 */
export function applyCompanyHostRedirectIfNeeded(
    auth,
    companiesList,
    companiesLoading,
    handlers,
    pathForCompanySubdomain,
) {
    if (auth == null) {
        return 'ok';
    }
    if (auth.status !== 'authenticated') {
        return 'ok';
    }
    if (typeof window === 'undefined') {
        return 'ok';
    }
    const hostSubdomain = extractSubdomainFromHostname(window.location.hostname);
    if (companiesLoading) {
        return 'wait';
    }
    if (companiesList.length === 0) {
        if (handlers && typeof handlers.loadCompanies === 'function') {
            handlers.loadCompanies();
        }
        return 'wait';
    }
    const activeCompanySubdomain = resolveActiveCompanySubdomain(auth.user, companiesList);
    if (activeCompanySubdomain) {
        if (!_companySubdomainMatchesHost(hostSubdomain, activeCompanySubdomain)) {
            const rawPath =
                typeof pathForCompanySubdomain === 'string' && pathForCompanySubdomain.length > 0
                    ? pathForCompanySubdomain
                    : `${window.location.pathname}${window.location.search}${window.location.hash}`;
            const pathNorm = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
            const next = buildCompanySubdomainUrl(activeCompanySubdomain, pathNorm);
            if (next !== window.location.href) {
                window.location.replace(next);
                return 'replaced';
            }
        }
        return 'ok';
    }
    if (hostSubdomain !== null) {
        return 'ok';
    }
    if (window.location.pathname === '/select-company' || window.location.pathname.startsWith('/select-company?')) {
        return 'ok';
    }
    const selectUrl = buildShellOriginPathUrl('/select-company');
    if (selectUrl !== window.location.href) {
        window.location.replace(selectUrl);
        return 'replaced_select';
    }
    return 'ok';
}
