/**
 * Host-aware platform brand bootstrap и domain utils.
 * Согласовано с core.utils.domain и /frontend/api/platform/brand.
 */

/** @type {import('./company-url.js').CompanyHostContext & PlatformBrandProductLabels | null} */
let cachedPlatformBrand = null;

/**
 * @typedef {object} PlatformBrandProductLabels
 * @property {string} platformName
 * @property {string} supportEmail
 * @property {string} logoPath
 * @property {string} apexOrigin
 * @property {string[]} supportedDomains
 * @property {string} agentProductName
 * @property {string} modelsProductName
 * @property {string} voiceProductName
 * @property {string} llmsDisplayLabel
 * @property {string} flowsProductLabel
 */

/**
 * @typedef {PlatformBrandProductLabels & {
 *   baseDomain: string,
 *   isProduction: boolean,
 *   portSuffix: string,
 *   protocol: string,
 * }} PlatformBrandBootstrap
 */

/**
 * @param {PlatformBrandBootstrap} brand
 */
export function setPlatformBrandBootstrap(brand) {
    if (!brand || typeof brand.baseDomain !== 'string' || brand.baseDomain.length === 0) {
        throw new Error('setPlatformBrandBootstrap: baseDomain required');
    }
    cachedPlatformBrand = {
        isProduction: brand.isProduction,
        baseDomain: brand.baseDomain,
        portSuffix: brand.portSuffix,
        protocol: brand.protocol,
        platformName: brand.platformName,
        supportEmail: brand.supportEmail,
        logoPath: brand.logoPath,
        supportedDomains: brand.supportedDomains,
        apexOrigin: brand.apexOrigin,
        agentProductName: brand.agentProductName,
        modelsProductName: brand.modelsProductName,
        voiceProductName: brand.voiceProductName,
        llmsDisplayLabel: brand.llmsDisplayLabel,
        flowsProductLabel: brand.flowsProductLabel,
    };
    if (typeof window !== 'undefined') {
        window.__PLATFORM_BRAND__ = cachedPlatformBrand;
    }
}

/**
 * @returns {PlatformBrandBootstrap | null}
 */
export function getPlatformBrandBootstrap() {
    if (cachedPlatformBrand) {
        return cachedPlatformBrand;
    }
    if (typeof window !== 'undefined' && window.__PLATFORM_BRAND__) {
        cachedPlatformBrand = window.__PLATFORM_BRAND__;
        return cachedPlatformBrand;
    }
    return null;
}

/**
 * @returns {import('./company-url.js').CompanyHostContext}
 */
export function getCompanyHostContextFromLocation() {
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

    return {
        isProduction: true,
        baseDomain: hostname,
        portSuffix: '',
        protocol: 'https',
    };
}

/**
 * @param {string} hostname
 * @returns {string}
 */
function extractBaseDomainFromHostname(hostname) {
    const brand = getPlatformBrandBootstrap();
    if (!brand || !Array.isArray(brand.supportedDomains) || brand.supportedDomains.length === 0) {
        throw new Error('platform brand bootstrap required for production host resolution');
    }
    const supported = brand.supportedDomains;
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
    for (const domain of supported) {
        if (h === domain || h.endsWith(`.${domain}`)) {
            return domain;
        }
    }
    if (brand && typeof brand.baseDomain === 'string' && brand.baseDomain.length > 0) {
        return brand.baseDomain;
    }
    throw new Error(`unsupported host domain: ${hostname}`);
}

export { extractBaseDomainFromHostname };
