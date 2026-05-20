/**
 * Ссылки и подпись «адрес компании» с тем же shell-origin, что у текущей страницы.
 * Согласовано с core.utils.subdomain.build_subdomain_url (dev: localhost / lvh.me + порт).
 */

/**
 * @typedef {{ isProduction: boolean, baseDomain: string, portSuffix: string, protocol: string }} CompanyHostContext
 */

/**
 * @returns {CompanyHostContext}
 */
export function getCompanyHostContext() {
    const hostname = window.location.hostname;
    const rawPort = window.location.port;

    const devPortSuffix = () => {
        if (rawPort && rawPort !== '80' && rawPort !== '443') {
            return `:${rawPort}`;
        }
        return ':8002';
    };

    if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
        return {
            isProduction: false,
            baseDomain: 'localhost',
            portSuffix: devPortSuffix(),
            protocol: 'http',
        };
    }

    if (hostname === 'lvh.me' || hostname.endsWith('.lvh.me')) {
        return {
            isProduction: false,
            baseDomain: 'lvh.me',
            portSuffix: devPortSuffix(),
            protocol: 'http',
        };
    }

    if (hostname === '127.0.0.1') {
        return {
            isProduction: false,
            baseDomain: '127.0.0.1',
            portSuffix: devPortSuffix(),
            protocol: 'http',
        };
    }

    if (hostname === 'humanitec.ru' || hostname.endsWith('.humanitec.ru')) {
        return {
            isProduction: true,
            baseDomain: 'humanitec.ru',
            portSuffix: '',
            protocol: 'https',
        };
    }

    if (hostname === 'agents-lab.ru' || hostname.endsWith('.agents-lab.ru')) {
        return {
            isProduction: true,
            baseDomain: 'agents-lab.ru',
            portSuffix: '',
            protocol: 'https',
        };
    }

    return {
        isProduction: true,
        baseDomain: 'humanitec.ru',
        portSuffix: '',
        protocol: 'https',
    };
}

/**
 * @param {string} subdomain
 * @param {string} [path]
 * @returns {string}
 */
export function buildCompanySubdomainUrl(subdomain, path = '/') {
    const ctx = getCompanyHostContext();
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${ctx.protocol}://${subdomain}.${ctx.baseDomain}${ctx.portSuffix}${normalizedPath}`;
}

/**
 * Текст превью: myco.lvh.me:8002 или myco.humanitec.ru
 *
 * @param {string} subdomain
 * @returns {string}
 */
export function formatCompanySubdomainLabel(subdomain) {
    const ctx = getCompanyHostContext();
    return `${subdomain}.${ctx.baseDomain}${ctx.portSuffix}`;
}

/**
 * Публичная «вершина» платформы без поддомена компании (лендинг после выхода и т.п.).
 *
 * @returns {string}
 */
export function getPlatformApexOriginUrl() {
    const ctx = getCompanyHostContext();
    return `${ctx.protocol}://${ctx.baseDomain}${ctx.portSuffix}/`;
}
