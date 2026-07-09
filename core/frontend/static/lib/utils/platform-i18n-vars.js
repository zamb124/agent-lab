/**
 * Host-aware i18n interpolation vars from platform brand bootstrap.
 */

import { getPlatformBrandBootstrap } from './platform-brand.js';

/**
 * @returns {{
 *   platformName: string,
 *   supportEmail: string,
 *   agentProductName: string,
 *   modelsProductName: string,
 *   voiceProductName: string,
 *   llmsDisplayLabel: string,
 *   flowsProductLabel: string,
 * }}
 */
export function getPlatformI18nVars() {
    const brand = getPlatformBrandBootstrap();
    if (!brand) {
        throw new Error('getPlatformI18nVars: platform brand bootstrap required');
    }
    return {
        platformName: brand.platformName,
        supportEmail: brand.supportEmail,
        agentProductName: brand.agentProductName,
        modelsProductName: brand.modelsProductName,
        voiceProductName: brand.voiceProductName,
        llmsDisplayLabel: brand.llmsDisplayLabel,
        flowsProductLabel: brand.flowsProductLabel,
    };
}

/**
 * @param {Record<string, string | number> | null | undefined} vars
 * @returns {Record<string, string | number>}
 */
export function mergePlatformI18nVars(vars) {
    const brandVars = getPlatformI18nVars();
    if (!vars) {
        return brandVars;
    }
    return { ...brandVars, ...vars };
}
