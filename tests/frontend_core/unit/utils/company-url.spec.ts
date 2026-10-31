/**
 * company-url: host context и URL субдомена компании на текущем brand apex.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    getCompanyHostContext,
    buildCompanySubdomainUrl,
} from '@platform/lib/utils/company-url.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';

/** @type {import('@platform/lib/utils/platform-brand.js').PlatformBrandBootstrap} */
const LINNEX_BRAND = {
    baseDomain: 'linnex.io',
    isProduction: true,
    portSuffix: '',
    protocol: 'https',
    platformName: 'Linnex',
    supportEmail: 'support@linnex.io',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'https://linnex.io/',
    supportedDomains: ['linnex.io', 'humanitec.ru'],
    modelsProductName: 'Linnex Models',
    voiceProductName: 'Linnex Voice',
    llmsDisplayLabel: 'Linnex LLMs',
    flowsProductLabel: 'Linnex Flows',
};

/**
 * @param {Partial<Location> & { __PLATFORM_BRAND__?: typeof LINNEX_BRAND }} loc
 */
function withLocation(loc) {
    const prev = globalThis.window;
    globalThis.window = {
        location: {
            hostname: loc.hostname ?? 'localhost',
            port: loc.port ?? '',
            protocol: loc.protocol ?? 'https:',
        },
    };
    if (loc.__PLATFORM_BRAND__) {
        setPlatformBrandBootstrap(loc.__PLATFORM_BRAND__);
    }
    return () => {
        globalThis.window = prev;
    };
}

beforeEach(() => {
    delete globalThis.window?.__PLATFORM_BRAND__;
});

afterEach(() => {
    delete globalThis.window?.__PLATFORM_BRAND__;
});

describe('getCompanyHostContext', () => {
    it('linnex.io использует baseDomain из platform brand bootstrap', () => {
        const restore = withLocation({
            hostname: 'linnex.io',
            port: '',
            protocol: 'https:',
            __PLATFORM_BRAND__: LINNEX_BRAND,
        });
        const ctx = getCompanyHostContext();
        restore();
        expect(ctx.baseDomain).toBe('linnex.io');
        expect(ctx.protocol).toBe('https');
        expect(ctx.isProduction).toBe(true);
    });

    it('system.linnex.io использует тот же brand context', () => {
        const restore = withLocation({
            hostname: 'system.linnex.io',
            port: '',
            protocol: 'https:',
            __PLATFORM_BRAND__: LINNEX_BRAND,
        });
        const ctx = getCompanyHostContext();
        restore();
        expect(ctx.baseDomain).toBe('linnex.io');
    });

    it('lvh.me остаётся dev-хостом без bootstrap', () => {
        const restore = withLocation({
            hostname: 'acme.lvh.me',
            port: '8002',
            protocol: 'http:',
        });
        const ctx = getCompanyHostContext();
        restore();
        expect(ctx.baseDomain).toBe('lvh.me');
        expect(ctx.protocol).toBe('http');
        expect(ctx.portSuffix).toBe(':8002');
    });
});

describe('buildCompanySubdomainUrl', () => {
    it('linnex.io строит system.linnex.io, не humanitec.ru', () => {
        const restore = withLocation({
            hostname: 'linnex.io',
            port: '',
            protocol: 'https:',
            __PLATFORM_BRAND__: LINNEX_BRAND,
        });
        const url = buildCompanySubdomainUrl('system', '/dashboard');
        restore();
        expect(url).toBe('https://system.linnex.io/dashboard');
    });
});
