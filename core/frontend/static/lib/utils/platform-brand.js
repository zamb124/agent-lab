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
 * @param {import('./company-url.js').CompanyHostContext} hostContext
 * @param {{
 *   base_domain: string,
 *   platform_name: string,
 *   support_email: string,
 *   logo_path: string,
 *   apex_origin: string,
 *   supported_domains: string[],
 *   agent_product_name: string,
 *   models_product_name: string,
 *   voice_product_name: string,
 *   llms_display_label: string,
 *   flows_product_label: string,
 * }} payload
 * @returns {PlatformBrandBootstrap}
 */
export function buildPlatformBrandBootstrapFromApiPayload(payload, hostContext) {
    if (!payload || typeof payload.base_domain !== 'string' || payload.base_domain.length === 0) {
        throw new Error('buildPlatformBrandBootstrapFromApiPayload: base_domain required');
    }
    if (!hostContext || typeof hostContext.baseDomain !== 'string' || hostContext.baseDomain.length === 0) {
        throw new Error('buildPlatformBrandBootstrapFromApiPayload: hostContext.baseDomain required');
    }
    return {
        isProduction: hostContext.isProduction,
        baseDomain: hostContext.baseDomain,
        portSuffix: hostContext.portSuffix,
        protocol: hostContext.protocol,
        platformName: payload.platform_name,
        supportEmail: payload.support_email,
        logoPath: payload.logo_path,
        apexOrigin: payload.apex_origin,
        supportedDomains: payload.supported_domains,
        agentProductName: payload.agent_product_name,
        modelsProductName: payload.models_product_name,
        voiceProductName: payload.voice_product_name,
        llmsDisplayLabel: payload.llms_display_label,
        flowsProductLabel: payload.flows_product_label,
    };
}

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
