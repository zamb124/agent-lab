/**
 * Утилита deep-link путей: чистые функции, тестируем как pure.
 */

import { describe, it, expect } from 'vitest';
import {
    DEEPLINK_PATH_PREFIXES,
    getAasaPathPatterns,
    hrefForDeepLinkNavigation,
} from '@platform/lib/utils/platform-deeplink-paths.js';

describe('DEEPLINK_PATH_PREFIXES', () => {
    it('содержит / и продуктовые префиксы', () => {
        expect(DEEPLINK_PATH_PREFIXES).toContain('/');
        expect(DEEPLINK_PATH_PREFIXES).toContain('/l');
        expect(DEEPLINK_PATH_PREFIXES).toContain('/join');
        expect(DEEPLINK_PATH_PREFIXES).toContain('/sync');
        expect(DEEPLINK_PATH_PREFIXES).toContain('/crm');
    });
});

describe('getAasaPathPatterns', () => {
    it('/ остаётся /, остальные получают /*', () => {
        const patterns = getAasaPathPatterns();
        expect(patterns).toContain('/');
        expect(patterns).toContain('/l/*');
        expect(patterns).toContain('/sync/*');
        expect(patterns).toContain('/crm/*');
    });
});

describe('hrefForDeepLinkNavigation', () => {
    it('тот же origin — pathname + search + hash', () => {
        const opened = new URL('https://humanitec.ru/join?x=1#frag');
        expect(hrefForDeepLinkNavigation(opened, 'https://humanitec.ru')).toBe('/join?x=1#frag');
    });

    it('короткая ссылка /l/ обрабатывается как внутренний path', () => {
        const opened = new URL('https://humanitec.ru/l/PFOGc35jDs7b3SkH');
        expect(hrefForDeepLinkNavigation(opened, 'https://humanitec.ru')).toBe('/l/PFOGc35jDs7b3SkH');
    });

    it('другой origin — полный href', () => {
        const opened = new URL('https://acme.humanitec.ru/crm/');
        expect(hrefForDeepLinkNavigation(opened, 'https://humanitec.ru')).toBe('https://acme.humanitec.ru/crm/');
    });

    it('на корне без search/hash — просто /', () => {
        const opened = new URL('https://humanitec.ru/');
        expect(hrefForDeepLinkNavigation(opened, 'https://humanitec.ru')).toBe('/');
    });
});
