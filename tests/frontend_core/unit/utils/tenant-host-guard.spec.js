/**
 * tenant-host-guard: согласованность с core.utils.domain (extract_subdomain).
 */

import { describe, it, expect } from 'vitest';
import { extractSubdomainFromHostname, resolveActiveCompanySubdomain } from '@platform/lib/utils/tenant-host-guard.js';

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
