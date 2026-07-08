/**
 * Загрузка platform brand bootstrap через HTTP (канон: fetch только в events/).
 */

import { httpRequest } from '../http.js';
import {
    getPlatformBrandBootstrap,
    getCompanyHostContextFromLocation,
    setPlatformBrandBootstrap,
} from '../../utils/platform-brand.js';

/**
 * @returns {Promise<import('../../utils/platform-brand.js').PlatformBrandBootstrap>}
 */
export async function loadPlatformBrandBootstrap() {
    const existing = getPlatformBrandBootstrap();
    if (existing) {
        return existing;
    }
    const ctx = getCompanyHostContextFromLocation();
    /** @type {{ base_domain: string, platform_name: string, support_email: string, logo_path: string, apex_origin: string, supported_domains: string[] }} */
    const payload = await httpRequest('/frontend/api/platform/brand', {
        method: 'GET',
        headers: { Accept: 'application/json' },
    });
    const brand = {
        isProduction: ctx.isProduction,
        baseDomain: payload.base_domain,
        portSuffix: ctx.portSuffix,
        protocol: ctx.protocol,
        platformName: payload.platform_name,
        supportEmail: payload.support_email,
        logoPath: payload.logo_path,
        apexOrigin: payload.apex_origin,
        supportedDomains: payload.supported_domains,
    };
    setPlatformBrandBootstrap(brand);
    return brand;
}
