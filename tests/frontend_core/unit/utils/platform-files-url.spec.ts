import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    buildPlatformFileDownloadUrl,
    clearPlatformFilesRouteSegment,
    platformFileImageVariantUrl,
    resolvePlatformFilesApiBase,
    resolvePlatformFilesRouteSegment,
    setPlatformFilesRouteSegment,
} from '@platform/lib/utils/platform-files-url.js';
import { installDomShim } from '../../helpers/dom-shim.js';

let dom: ReturnType<typeof installDomShim>;

beforeEach(() => {
    clearPlatformFilesRouteSegment();
    dom = installDomShim();
});

afterEach(() => {
    clearPlatformFilesRouteSegment();
    dom.uninstall();
});

describe('platform-files-url', () => {
    it('bound segment wins over empty pathname', () => {
        setPlatformFilesRouteSegment('frontend');
        expect(resolvePlatformFilesRouteSegment()).toBe('frontend');
        expect(resolvePlatformFilesApiBase()).toBe('/frontend/api/v1/files');
        expect(buildPlatformFileDownloadUrl('f1')).toBe('/frontend/api/v1/files/download/f1');
    });

    it('pathname under /crm uses crm segment when unbound', () => {
        dom.window.location.pathname = '/crm/dashboard';
        Object.defineProperty(globalThis.location, 'pathname', {
            value: '/crm/dashboard',
            configurable: true,
        });
        expect(resolvePlatformFilesRouteSegment()).toBe('crm');
    });

    it('frontend SPA pathname /dashboard without bind raises', () => {
        dom.window.location.pathname = '/dashboard';
        Object.defineProperty(globalThis.location, 'pathname', {
            value: '/dashboard',
            configurable: true,
        });
        expect(() => resolvePlatformFilesRouteSegment()).toThrow(/service path segment required/);
    });

    it('opts.routeSegment overrides bind', () => {
        setPlatformFilesRouteSegment('frontend');
        expect(resolvePlatformFilesRouteSegment({ routeSegment: 'sync' })).toBe('sync');
    });

    it('variant query on download URLs: относительные и абсолютные', () => {
        expect(platformFileImageVariantUrl('/shop/api/v1/files/download/f1', 'sm!sq')).toBe(
            '/shop/api/v1/files/download/f1?v=sm%21sq',
        );
        expect(
            platformFileImageVariantUrl('https://h.test/sync/api/v1/files/download/f2', 'md'),
        ).toBe('https://h.test/sync/api/v1/files/download/f2?v=md');
    });

    it('variant query: сохраняет hash и заменяет существующий v', () => {
        expect(
            platformFileImageVariantUrl('/crm/api/v1/files/download/f1?x=1#frag', 'lg'),
        ).toBe('/crm/api/v1/files/download/f1?x=1&v=lg#frag');
        expect(
            platformFileImageVariantUrl('/crm/api/v1/files/download/f1?v=sm', 'lg'),
        ).toBe('/crm/api/v1/files/download/f1?v=lg');
    });

    it('variant query: не-download URL возвращается как есть', () => {
        expect(platformFileImageVariantUrl('https://cdn.test/a.png', 'sm')).toBe(
            'https://cdn.test/a.png',
        );
        expect(platformFileImageVariantUrl('/static/core/logo.svg', 'sm')).toBe(
            '/static/core/logo.svg',
        );
    });
});
