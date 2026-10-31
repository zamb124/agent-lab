import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { loadPlatformBrandBootstrap } from '@platform/lib/events/effects/platform-brand-bootstrap.js';
import {
    getPlatformBrandBootstrap,
} from '@platform/lib/utils/platform-brand.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { installDomShim } from '../../helpers/dom-shim.js';

const BRAND_URL = '/frontend/api/platform/brand';

const API_PAYLOAD = {
    base_domain: 'linnex.io',
    platform_name: 'Linnex',
    support_email: 'support@linnex.io',
    logo_path: '/static/core/assets/service_logos/frontend_logo.svg',
    apex_origin: 'https://linnex.io/',
    supported_domains: ['linnex.io', 'humanitec.ru'],
    models_product_name: 'Linnex Models',
    voice_product_name: 'Linnex Voice',
    llms_display_label: 'Linnex LLMs',
    flows_product_label: 'Linnex Flows',
};

let fetchMock;
let dom;

beforeEach(() => {
    dom = installDomShim();
    dom.window.location.hostname = 'linnex.io';
    dom.window.location.protocol = 'https:';
    dom.window.location.host = 'linnex.io';
    dom.window.location.port = '';
    dom.window.location.href = 'https://linnex.io/';
    fetchMock = installFetchMock();
    if (typeof globalThis.window !== 'undefined') {
        delete globalThis.window.__PLATFORM_BRAND__;
    }
});

afterEach(() => {
    fetchMock.uninstall();
    dom.uninstall();
    if (typeof globalThis.window !== 'undefined') {
        delete globalThis.window.__PLATFORM_BRAND__;
    }
});

describe('loadPlatformBrandBootstrap', () => {
    it('загружает brand с API и сохраняет bootstrap', async () => {
        fetchMock.respondJson('GET', BRAND_URL, API_PAYLOAD);
        const brand = await loadPlatformBrandBootstrap();
        expect(brand.baseDomain).toBe('linnex.io');
        expect(brand.platformName).toBe('Linnex');
        expect(brand.protocol).toBe('https');
        expect(getPlatformBrandBootstrap()).toEqual(brand);
        expect(fetchMock.calls).toHaveLength(1);
        expect(fetchMock.calls[0].url).toBe(BRAND_URL);
    });

    it('возвращает кеш без HTTP если bootstrap уже установлен', async () => {
        const cached = getPlatformBrandBootstrap();
        if (!cached) {
            throw new Error('expected bootstrap from prior test');
        }
        const brand = await loadPlatformBrandBootstrap();
        expect(brand).toEqual(cached);
        expect(fetchMock.calls).toHaveLength(0);
    });
});
