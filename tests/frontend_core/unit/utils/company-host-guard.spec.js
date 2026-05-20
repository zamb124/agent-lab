/**
 * company-host-guard: согласованность с core.utils.domain (extract_subdomain).
 */

import { describe, it, expect, vi } from 'vitest';
import {
    extractSubdomainFromHostname,
    resolveActiveCompanySubdomain,
    applyCompanyHostRedirectIfNeeded,
} from '@platform/lib/utils/company-host-guard.js';

describe('extractSubdomainFromHostname', () => {
    it('humanitec.ru -> null (apex)', () => {
        expect(extractSubdomainFromHostname('humanitec.ru')).toBeNull();
    });
    it('www.humanitec.ru -> null', () => {
        expect(extractSubdomainFromHostname('www.humanitec.ru')).toBeNull();
    });
    it('system.humanitec.ru -> system', () => {
        expect(extractSubdomainFromHostname('system.humanitec.ru')).toBe('system');
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
});
