import { describe, it, expect } from 'vitest';
import {
    buildDocumentsCatalogEntryUrl,
    buildFrontendPublicPath,
} from '@platform/lib/utils/build-service-entry-url.js';

describe('buildFrontendPublicPath', () => {
    const withWindow = (loc: Partial<Location>, fn: () => void) => {
        const prev = globalThis.window;
        Object.defineProperty(globalThis, 'window', { value: { location: loc }, configurable: true, writable: true });
        try {
            fn();
        } finally {
            Object.defineProperty(globalThis, 'window', { value: prev, configurable: true, writable: true });
        }
    };

    it('throws when path is invalid', () => {
        withWindow(
            { hostname: 'linnex.io', port: '', protocol: 'https:' },
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
            { hostname: 'linnex.io', port: '', protocol: 'https:' },
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

describe('buildDocumentsCatalogEntryUrl', () => {
    const withWindow = (loc: Partial<Location>, fn: () => void) => {
        const prev = globalThis.window;
        Object.defineProperty(globalThis, 'window', { value: { location: loc }, configurable: true, writable: true });
        try {
            fn();
        } finally {
            Object.defineProperty(globalThis, 'window', { value: prev, configurable: true, writable: true });
        }
    };

    it('throws without catalog_id or namespace', () => {
        withWindow(
            { hostname: 'system.lvh.me', port: '8001', protocol: 'http:', origin: 'http://system.lvh.me:8001' },
            () => {
                expect(() => buildDocumentsCatalogEntryUrl('', 'default')).toThrow(
                    'buildDocumentsCatalogEntryUrl: catalog_id required',
                );
                expect(() => buildDocumentsCatalogEntryUrl('cat-1', '')).toThrow(
                    'buildDocumentsCatalogEntryUrl: namespace required',
                );
            },
        );
    });

    it('adds namespace and catalog_id on documents dev port', () => {
        withWindow(
            { hostname: 'system.lvh.me', port: '8001', protocol: 'http:', origin: 'http://system.lvh.me:8001' },
            () => {
                expect(buildDocumentsCatalogEntryUrl('cat-1', 'default')).toBe(
                    'http://system.lvh.me:8008/documents?namespace=default&catalog_id=cat-1',
                );
            },
        );
    });
});
