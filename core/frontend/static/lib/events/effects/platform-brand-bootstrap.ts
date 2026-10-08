/**
 * Загрузка platform brand bootstrap через HTTP (канон: fetch только в events/).
 */

import { httpRequest } from '../http.js';
import type { PlatformBrandBootstrap, PlatformBrandApiPayload } from '../../utils/platform-brand.js';
import {
    buildPlatformBrandBootstrapFromApiPayload,
    getPlatformBrandBootstrap,
    getCompanyHostContextFromLocation,
    setPlatformBrandBootstrap,
} from '../../utils/platform-brand.js';

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
    const payload = (await httpRequest({
        url: brandUrl,
        method: 'GET',
        headers: { Accept: 'application/json' },
    })) as PlatformBrandApiPayload;
    const brand = buildPlatformBrandBootstrapFromApiPayload(payload, ctx);
    setPlatformBrandBootstrap(brand);
    return brand;
}
