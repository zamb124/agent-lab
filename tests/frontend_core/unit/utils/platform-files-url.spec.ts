import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    buildPlatformFileDownloadUrl,
    clearPlatformFilesRouteSegment,
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
});
