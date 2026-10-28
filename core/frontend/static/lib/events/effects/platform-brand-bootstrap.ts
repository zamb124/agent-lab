/**
 * Загрузка platform brand bootstrap через HTTP (канон: fetch только в events/).
 */

import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';
import type { PlatformBrandBootstrap, PlatformBrandApiPayload } from '../../utils/platform-brand.js';
import {
    buildPlatformBrandBootstrapFromApiPayload,
    getPlatformBrandBootstrap,
    getCompanyHostContextFromLocation,
    setPlatformBrandBootstrap,
} from '../../utils/platform-brand.js';

function isStringList(value: unknown): value is string[] {
    if (!Array.isArray(value)) return false;
    for (const item of value) {
        if (typeof item !== 'string') return false;
    }
    return true;
}

function isPlatformBrandApiPayload(value: unknown): value is PlatformBrandApiPayload {
    if (!isPlainRecord(value)) return false;
    if (typeof value.base_domain !== 'string' || typeof value.platform_name !== 'string') return false;
    if (typeof value.support_email !== 'string' || typeof value.logo_path !== 'string') return false;
    if (typeof value.apex_origin !== 'string' || typeof value.agent_product_name !== 'string') return false;
    if (typeof value.models_product_name !== 'string' || typeof value.voice_product_name !== 'string') return false;
    if (typeof value.llms_display_label !== 'string' || typeof value.flows_product_label !== 'string') return false;
    return isStringList(value.supported_domains);
}

export async function loadPlatformBrandBootstrap(options: { platformUiOrigin?: string } = {}): Promise<PlatformBrandBootstrap> {
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
    const payload = await httpRequest({
        url: brandUrl,
        method: 'GET',
        headers: { Accept: 'application/json' },
    });
    if (!isPlatformBrandApiPayload(payload)) {
        throw new Error('loadPlatformBrandBootstrap: brand payload required');
    }
    const brand = buildPlatformBrandBootstrapFromApiPayload(payload, ctx);
    setPlatformBrandBootstrap(brand);
    return brand;
}
