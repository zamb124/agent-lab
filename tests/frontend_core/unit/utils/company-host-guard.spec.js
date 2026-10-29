/**
 * company-host-guard: согласованность с core.utils.domain (extract_subdomain).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    extractSubdomainFromHostname,
    resolveActiveCompanySubdomain,
    applyCompanyHostRedirectIfNeeded,
} from '@platform/lib/utils/company-host-guard.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';

/** @type {import('@platform/lib/utils/platform-brand.js').PlatformBrandBootstrap} */
const HUMANITEC_BRAND = {
    baseDomain: 'humanitec.ru',
    isProduction: true,
    portSuffix: '',
    protocol: 'https',
    platformName: 'Humanitec',
    supportEmail: 'helpme@humanitec.ru',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'https://humanitec.ru/',
    supportedDomains: ['humanitec.ru', 'linnex.io'],
    modelsProductName: 'Humanitec Models',
    voiceProductName: 'Humanitec Voice',
    llmsDisplayLabel: 'Humanitec LLMs',
    flowsProductLabel: 'Humanitec Flows',
};

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
 * @param {import('@platform/lib/utils/platform-brand.js').PlatformBrandBootstrap | null} brand
 * @param {() => void} fn
 */
function withPlatformBrand(brand, fn) {
    const prevWindow = globalThis.window;
    const prevBrand = prevWindow?.__PLATFORM_BRAND__;
    globalThis.window = globalThis.window ?? {};
    if (brand) {
        setPlatformBrandBootstrap(brand);
    } else {
        delete globalThis.window.__PLATFORM_BRAND__;
    }
    try {
        fn();
    } finally {
        if (prevBrand !== undefined) {
            setPlatformBrandBootstrap(prevBrand);
        } else {
            delete globalThis.window.__PLATFORM_BRAND__;
        }
    }
}

beforeEach(() => {
    delete globalThis.window?.__PLATFORM_BRAND__;
});

afterEach(() => {
    delete globalThis.window?.__PLATFORM_BRAND__;
});

describe('extractSubdomainFromHostname', () => {
    it('humanitec.ru -> null (apex)', () => {
        withPlatformBrand(HUMANITEC_BRAND, () => {
            expect(extractSubdomainFromHostname('humanitec.ru')).toBeNull();
        });
    });
    it('www.humanitec.ru -> null', () => {
        withPlatformBrand(HUMANITEC_BRAND, () => {
            expect(extractSubdomainFromHostname('www.humanitec.ru')).toBeNull();
        });
    });
    it('system.humanitec.ru -> system', () => {
        withPlatformBrand(HUMANITEC_BRAND, () => {
            expect(extractSubdomainFromHostname('system.humanitec.ru')).toBe('system');
        });
    });
    it('linnex.io -> null (apex)', () => {
        withPlatformBrand(LINNEX_BRAND, () => {
            expect(extractSubdomainFromHostname('linnex.io')).toBeNull();
        });
    });
    it('system.linnex.io -> system', () => {
        withPlatformBrand(LINNEX_BRAND, () => {
            expect(extractSubdomainFromHostname('system.linnex.io')).toBe('system');
        });
    });
    it('localhost -> null', () => {
        expect(extractSubdomainFromHostname('localhost')).toBeNull();
    });
    it('a.localhost -> a', () => {
        expect(extractSubdomainFromHostname('a.localhost')).toBe('a');
    });
});

describe('resolveActiveCompanySubdomain', () => {
    it('возвращает subdomain по company_id из списка', () => {
        const sub = resolveActiveCompanySubdomain(
            { company_id: 'c1' },
            [{ company_id: 'c1', subdomain: 'acme' }],
        );
        expect(sub).toBe('acme');
    });
    it('raw.company_id используется если company_id пуст', () => {
        const sub = resolveActiveCompanySubdomain(
            { raw: { company_id: 'c1' } },
            [{ company_id: 'c1', subdomain: 'acme' }],
        );
        expect(sub).toBe('acme');
    });
    it('возвращает null если субдомен не задан', () => {
        const sub = resolveActiveCompanySubdomain(
            { company_id: 'c1' },
            [{ company_id: 'c1' }],
        );
        expect(sub).toBeNull();
    });
});

describe('applyCompanyHostRedirectIfNeeded', () => {
    const withWindow = (loc, fn) => {
        const prev = globalThis.window;
        const replace = loc.replace ?? vi.fn();
        globalThis.window = { location: { ...loc, replace } };
        if (loc.__PLATFORM_BRAND__) {
            setPlatformBrandBootstrap(loc.__PLATFORM_BRAND__);
        }
        try {
            return fn(replace);
        } finally {
            globalThis.window = prev;
        }
    };

    it('demo.lvh.me + активная компания system -> replace на system (тот же path)', () => {
        withWindow(
            {
                hostname: 'demo.lvh.me',
                port: '8002',
                protocol: 'http:',
                pathname: '/dashboard',
                search: '',
                hash: '',
                href: 'http://demo.lvh.me:8002/dashboard',
            },
            (replace) => {
                const auth = { status: 'authenticated', user: { company_id: 'sys' } };
                const companies = [
                    { company_id: 'sys', subdomain: 'system' },
                    { company_id: 'd1', subdomain: 'demo' },
                ];

                const r = applyCompanyHostRedirectIfNeeded(auth, companies, false, undefined, undefined);
                expect(r).toBe('replaced');
                expect(replace).toHaveBeenCalledTimes(1);
                expect(replace.mock.calls[0][0]).toBe('http://system.lvh.me:8002/dashboard');
            },
        );
    });

    it('system.lvh.me + активная компания system -> без replace', () => {
        withWindow(
            {
                hostname: 'system.lvh.me',
                port: '8002',
                protocol: 'http:',
                pathname: '/dashboard',
                search: '',
                hash: '',
                href: 'http://system.lvh.me:8002/dashboard',
            },
            (replace) => {
                const auth = { status: 'authenticated', user: { company_id: 'sys' } };
                const companies = [{ company_id: 'sys', subdomain: 'system' }];

                const r = applyCompanyHostRedirectIfNeeded(auth, companies, false, undefined, undefined);
                expect(r).toBe('ok');
                expect(replace).not.toHaveBeenCalled();
            },
        );
    });

    it('lvh.me (apex) + активная компания acme -> replace на acme', () => {
        withWindow(
            {
                hostname: 'lvh.me',
                port: '8002',
                protocol: 'http:',
                pathname: '/team',
                search: '',
                hash: '',
                href: 'http://lvh.me:8002/team',
            },
            (replace) => {
                const auth = { status: 'authenticated', user: { company_id: 'c2' } };
                const companies = [{ company_id: 'c2', subdomain: 'acme' }];

                const r = applyCompanyHostRedirectIfNeeded(auth, companies, false, undefined, undefined);
                expect(r).toBe('replaced');
                expect(replace.mock.calls[0][0]).toBe('http://acme.lvh.me:8002/team');
            },
        );
    });

    it('linnex.io + активная компания system -> replace на system.linnex.io', () => {
        withWindow(
            {
                hostname: 'linnex.io',
                port: '',
                protocol: 'https:',
                pathname: '/dashboard',
                search: '',
                hash: '',
                href: 'https://linnex.io/dashboard',
                __PLATFORM_BRAND__: LINNEX_BRAND,
            },
            (replace) => {
                const auth = { status: 'authenticated', user: { company_id: 'sys' } };
                const companies = [{ company_id: 'sys', subdomain: 'system' }];

                const r = applyCompanyHostRedirectIfNeeded(auth, companies, false, undefined, undefined);
                expect(r).toBe('replaced');
                expect(replace).toHaveBeenCalledTimes(1);
                expect(replace.mock.calls[0][0]).toBe('https://system.linnex.io/dashboard');
            },
        );
    });

    it('system.linnex.io + активная компания system -> без replace', () => {
        withWindow(
            {
                hostname: 'system.linnex.io',
                port: '',
                protocol: 'https:',
                pathname: '/dashboard',
                search: '',
                hash: '',
                href: 'https://system.linnex.io/dashboard',
                __PLATFORM_BRAND__: LINNEX_BRAND,
            },
            (replace) => {
                const auth = { status: 'authenticated', user: { company_id: 'sys' } };
                const companies = [{ company_id: 'sys', subdomain: 'system' }];

                const r = applyCompanyHostRedirectIfNeeded(auth, companies, false, undefined, undefined);
                expect(r).toBe('ok');
                expect(replace).not.toHaveBeenCalled();
            },
        );
    });
});
