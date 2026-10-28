/**
 * Обновление document title и базовых meta-тегов по platform brand bootstrap.
 */

import { getPlatformBrandBootstrap } from './platform-brand.js';

/**
 * @param {import('./platform-brand.js').PlatformBrandBootstrap} brand
 */
export function applyPlatformDocumentMeta(brand: import('./platform-brand.js').PlatformBrandBootstrap | null | undefined): void {
    if (typeof document === 'undefined' || !brand) {
        return;
    }
    const origin = brand.apexOrigin.replace(/\/$/, '');
    const platformName = brand.platformName;
    document.title = `${platformName} — платформа автоматизации бизнеса`;

    const setMeta = (selector: string, attr: string, value: string) => {
        const node = document.querySelector(selector);
        if (node) {
            node.setAttribute(attr, value);
        }
    };

    setMeta('meta[property="og:site_name"]', 'content', platformName);
    setMeta('meta[property="og:title"]', 'content', document.title);
    setMeta('meta[name="twitter:title"]', 'content', document.title);
    setMeta('link[rel="canonical"]', 'href', `${origin}/`);
    setMeta('meta[property="og:url"]', 'content', `${origin}/`);
    setMeta('meta[name="apple-mobile-web-app-title"]', 'content', platformName);
}

/**
 * Применяет meta, если brand bootstrap уже загружен.
 */
export function applyPlatformDocumentMetaIfReady(): void {
    const brand = getPlatformBrandBootstrap();
    if (brand) {
        applyPlatformDocumentMeta(brand);
    }
}
