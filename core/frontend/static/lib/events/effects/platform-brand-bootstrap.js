/**
 * Загрузка platform brand bootstrap через HTTP (канон: fetch только в events/).
 */

import { httpRequest } from '../http.js';
import {
    buildPlatformBrandBootstrapFromApiPayload,
    getPlatformBrandBootstrap,
    getCompanyHostContextFromLocation,
    setPlatformBrandBootstrap,
} from '../../utils/platform-brand.js';

/**
 * @param {{ platformUiOrigin?: string }} [options]
 * @returns {Promise<import('../../utils/platform-brand.js').PlatformBrandBootstrap>}
 */
export async function loadPlatformBrandBootstrap(options = {}) {
    const existing = getPlatformBrandBootstrap();
    if (existing) {
        return existing;
    }
    const ctx = getCompanyHostContextFromLocation();
    const originRaw =
        typeof options.platformUiOrigin === 'string' ? options.platformUiOrigin.trim().replace(/\/+$/, '') : '';
    const brandUrl = originRaw
        ? `${originRaw}/frontend/api/platform/brand`
        : '/frontend/api/platform/brand';
    /** @type {{
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
     * }} */
    const payload = await httpRequest({
        url: brandUrl,
        method: 'GET',
        headers: { Accept: 'application/json' },
    });
    const brand = buildPlatformBrandBootstrapFromApiPayload(payload, ctx);
    setPlatformBrandBootstrap(brand);
    return brand;
}
