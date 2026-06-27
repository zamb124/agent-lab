import { describe, it, expect } from 'vitest';
import { buildFrontendPublicPath } from '@platform/lib/utils/build-service-entry-url.js';

describe('buildFrontendPublicPath', () => {
    const withWindow = (loc, fn) => {
        const prev = globalThis.window;
        globalThis.window = { location: loc };
        try {
            fn();
        } finally {
            globalThis.window = prev;
        }
    };

    it('throws when path is invalid', () => {
        withWindow(
            { hostname: 'humanitec.ru', port: '', protocol: 'https:' },
            () => {
                expect(() => buildFrontendPublicPath('')).toThrow(
                    'buildFrontendPublicPath: path must be a non-empty string starting with /',
                );
                expect(() => buildFrontendPublicPath('agent')).toThrow(
                    'buildFrontendPublicPath: path must be a non-empty string starting with /',
                );
            },
        );
    });

    it('returns path as-is on production host', () => {
        withWindow(
            { hostname: 'humanitec.ru', port: '', protocol: 'https:' },
            () => {
                expect(buildFrontendPublicPath('/agent')).toBe('/agent');
            },
        );
    });

    it('returns path as-is when already on frontend dev port', () => {
        withWindow(
            { hostname: 'system.lvh.me', port: '8002', protocol: 'http:' },
            () => {
                expect(buildFrontendPublicPath('/agent')).toBe('/agent');
            },
        );
    });

    it('adds frontend port for flows dev host', () => {
        withWindow(
            { hostname: 'system.lvh.me', port: '8001', protocol: 'http:' },
            () => {
                expect(buildFrontendPublicPath('/agent')).toBe('http://system.lvh.me:8002/agent');
            },
        );
    });

    it('adds frontend dev port from other service host', () => {
        withWindow(
            { hostname: 'system.lvh.me', port: '9001', protocol: 'http:' },
            () => {
                expect(buildFrontendPublicPath('/agent')).toBe('http://system.lvh.me:8002/agent');
            },
        );
    });
});
