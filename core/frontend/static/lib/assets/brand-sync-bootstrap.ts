/**
 * Синхронный bootstrap бренда до загрузки модулей: XHR → /frontend/api/platform/brand
 * в window.__PLATFORM_BRAND__. Realm-файл: собирается esbuild'ом в embed-dist,
 * отдаётся как классический script (не module) — window-глобалы типизированы явно.
 */

import type { PlatformBrandBootstrap } from '../utils/platform-brand.js';

interface PlatformBrandResponse {
    base_domain?: string;
    platform_name?: string;
    models_product_name?: string;
    voice_product_name?: string;
    llms_display_label?: string;
    flows_product_label?: string;
    support_email?: string;
    logo_path?: string;
    apex_origin?: string;
    supported_domains?: unknown;
}

(function () {
    try {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', '/frontend/api/platform/brand', false);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.send(null);
        if (xhr.status !== 200) {
            return;
        }
        const brand: PlatformBrandResponse = JSON.parse(xhr.responseText);
        const hostname = window.location.hostname;
        const rawPort = window.location.port;
        let portSuffix = '';
        if (rawPort && rawPort !== '80' && rawPort !== '443') {
            portSuffix = ':' + rawPort;
        }
        let baseDomain = String(brand.base_domain || '');
        if (baseDomain === '') {
            if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
                baseDomain = 'localhost';
            } else if (hostname === 'lvh.me' || hostname.endsWith('.lvh.me')) {
                baseDomain = 'lvh.me';
            } else if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(hostname)) {
                baseDomain = hostname;
            }
        }
        const protocol = window.location.protocol.replace(':', '');
        const isProduction = protocol === 'https' && portSuffix === '';
        const bootstrap: PlatformBrandBootstrap = {
            platformName: String(brand.platform_name || 'Platform'),
            modelsProductName: String(brand.models_product_name || 'Platform Models'),
            voiceProductName: String(brand.voice_product_name || 'Platform Voice'),
            llmsDisplayLabel: String(brand.llms_display_label || 'Platform LLMs'),
            flowsProductLabel: String(brand.flows_product_label || 'Platform Flows'),
            supportEmail: String(brand.support_email || ''),
            logoPath: String(brand.logo_path || ''),
            apexOrigin: String(brand.apex_origin || ''),
            supportedDomains: Array.isArray(brand.supported_domains) ? brand.supported_domains : [],
            baseDomain: baseDomain,
            isProduction: isProduction,
            portSuffix: portSuffix,
            protocol: protocol,
        };
        window.__PLATFORM_BRAND__ = bootstrap;
    } catch (_err) {
        /* brand bootstrap optional before module load */
    }
})();
