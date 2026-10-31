/**
 * Ссылки и подпись «адрес компании» с тем же shell-origin, что у текущей страницы.
 * Согласовано с core.utils.subdomain.build_subdomain_url (dev: localhost / lvh.me + порт).
 */

import {
    extractBaseDomainFromHostname,
    getPlatformBrandBootstrap,
} from './platform-brand.js';

export interface CompanyHostContext {
    isProduction: boolean;
    baseDomain: string;
    portSuffix: string;
    protocol: string;
}

/**
 * @returns {CompanyHostContext}
 */
export function getCompanyHostContext(): CompanyHostContext {
    const hostname = window.location.hostname;
    const rawPort = window.location.port;
    const protocol = window.location.protocol.replace(':', '');

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

    const brand = getPlatformBrandBootstrap();
    if (brand) {
        return {
            isProduction: brand.isProduction,
            baseDomain: brand.baseDomain,
            portSuffix: brand.portSuffix,
            protocol: brand.protocol,
        };
    }

    const baseDomain = extractBaseDomainFromHostname(hostname);
    const portSuffix = rawPort && rawPort !== '80' && rawPort !== '443' ? `:${rawPort}` : '';
    const isProduction = protocol === 'https' && portSuffix === '';
    return {
        isProduction,
        baseDomain,
        portSuffix,
        protocol,
    };
}

/**
 * @param {string} subdomain
 * @param {string} [path]
 * @returns {string}
 */
export function buildCompanySubdomainUrl(subdomain: string, path = '/'): string {
    const ctx = getCompanyHostContext();
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${ctx.protocol}://${subdomain}.${ctx.baseDomain}${ctx.portSuffix}${normalizedPath}`;
}

/**
 * Текст превью: myco.lvh.me:8002 или myco.linnex.io
 *
 * @param {string} subdomain
 * @returns {string}
 */
export function formatCompanySubdomainLabel(subdomain: string) {
    const ctx = getCompanyHostContext();
    return `${subdomain}.${ctx.baseDomain}${ctx.portSuffix}`;
}

/**
 * Публичная «вершина» платформы без поддомена компании (лендинг после выхода и т.п.).
 *
 * @returns {string}
 */
export function getPlatformApexOriginUrl(): string {
    const ctx = getCompanyHostContext();
    return `${ctx.protocol}://${ctx.baseDomain}${ctx.portSuffix}/`;
}
