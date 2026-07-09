import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('@platform/lib/chat/platform-chat.js', () => ({}));

import {
    mountFromScript,
    readDatasetBool,
} from '../../../../core/frontend/static/lib/chat/embed-autoload.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';

const TEST_PLATFORM_BRAND = {
    isProduction: false,
    baseDomain: 'localhost',
    portSuffix: ':8002',
    protocol: 'http',
    platformName: 'Humanitec',
    supportEmail: 'support@humanitec.ru',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'http://localhost:8002/',
    supportedDomains: ['humanitec.ru', 'linnex.io', 'localhost', 'lvh.me'],
    agentProductName: 'HumanitecAgent',
    modelsProductName: 'Humanitec Models',
    voiceProductName: 'Humanitec Voice',
    llmsDisplayLabel: 'Humanitec LLMs',
    flowsProductLabel: 'Humanitec Flows',
};

function createMockScript(dataset = {}, src = 'https://cdn.example.com/humanitec-embed-autoload.js') {
    const script = {
        src,
        dataset: { ...dataset },
    };
    return script;
}

function createMockChatElement() {
    const attrs = new Map();
    return {
        tagName: 'PLATFORM-CHAT',
        attributes: attrs,
        useCredentials: false,
        showLauncher: false,
        initialOpen: false,
        flowsBaseUrl: '',
        getAuthToken: null,
        getExtraMetadataVariables: null,
        getContextVariables: null,
        setAttribute(name, value) {
            attrs.set(name, String(value));
        },
        getAttribute(name) {
            return attrs.has(name) ? attrs.get(name) : null;
        },
    };
}

let mockChat;
let appended;
let headChildren;
let originalDocument;
let originalWindow;
let originalCustomElements;
let fetchMock;

beforeEach(() => {
    mockChat = createMockChatElement();
    appended = [];
    headChildren = [];
    fetchMock = vi.fn();

    originalDocument = globalThis.document;
    originalWindow = globalThis.window;
    originalCustomElements = globalThis.customElements;

    setPlatformBrandBootstrap(TEST_PLATFORM_BRAND);
    globalThis.fetch = fetchMock;
    globalThis.document = {
        body: {
            appendChild(el) {
                appended.push(el);
            },
        },
        head: {
            appendChild(el) {
                headChildren.push(el);
            },
        },
        readyState: 'complete',
        title: 'Embed host page',
        querySelector(selector) {
            if (selector === 'link[data-humanitec-chat-tokens="1"]') {
                const found = headChildren.find(
                    (el) => el.getAttribute && el.getAttribute('data-humanitec-chat-tokens') === '1',
                );
                return found ?? null;
            }
            return null;
        },
        createElement(tag) {
            if (tag === 'platform-chat') {
                return mockChat;
            }
            if (tag === 'link') {
                const attrs = new Map();
                return {
                    rel: '',
                    href: '',
                    setAttribute(name, value) {
                        attrs.set(name, String(value));
                    },
                    getAttribute(name) {
                        return attrs.has(name) ? attrs.get(name) : null;
                    },
                };
            }
            throw new Error(`unexpected tag ${tag}`);
        },
        addEventListener: vi.fn(),
    };
    globalThis.window = {
        location: {
            origin: 'https://customer.example',
            href: 'https://customer.example/page',
            hostname: 'customer.example',
            host: 'customer.example',
            protocol: 'https:',
            port: '',
        },
        innerWidth: 1280,
        innerHeight: 720,
        humanitecEmbed: undefined,
        addEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
    };
    globalThis.customElements = {
        define: vi.fn(),
    };
});

afterEach(() => {
    globalThis.document = originalDocument;
    globalThis.window = originalWindow;
    globalThis.customElements = originalCustomElements;
    if (typeof globalThis.window !== 'undefined') {
        delete globalThis.window.__PLATFORM_BRAND__;
    }
    vi.restoreAllMocks();
});

describe('readDatasetBool', () => {
    it('возвращает default при отсутствии ключа', () => {
        const script = createMockScript({});
        expect(readDatasetBool(script, 'showLauncher', false)).toBe(false);
        expect(readDatasetBool(script, 'showLauncher', true)).toBe(true);
    });

    it('распознаёт true/1/yes', () => {
        const script = createMockScript({ showLauncher: 'true' });
        expect(readDatasetBool(script, 'showLauncher', false)).toBe(true);
    });
});

describe('mountFromScript', () => {
    it('требует data-embed-id и data-flows-base-url', async () => {
        await expect(mountFromScript(createMockScript({ flowsBaseUrl: 'https://api/flows' }))).rejects.toThrow(
            /data-embed-id required/,
        );
        await expect(mountFromScript(createMockScript({ embedId: 'embed_x' }))).rejects.toThrow(
            /data-flows-base-url required/,
        );
    });

    it('монтирует platform-chat drawer embed_public с dataset attrs', async () => {
        await mountFromScript(
            createMockScript({
                embedId: 'embed_abc',
                flowsBaseUrl: 'https://api.humanitec.ru/flows',
                assistantTitle: 'Helper',
                theme: 'dark',
                locale: 'ru',
                platformUiOrigin: 'https://api.humanitec.ru',
                voiceBaseUrl: 'https://api.humanitec.ru/voice',
                companyId: 'company_1',
                eventNamespace: 'assistant',
                toggleEventName: 'custom-toggle',
                showLauncher: 'true',
                voiceEnabled: 'true',
            }),
        );

        expect(appended).toHaveLength(1);
        expect(appended[0]).toBe(mockChat);
        expect(mockChat.getAttribute('display')).toBe('drawer');
        expect(mockChat.getAttribute('profile')).toBe('embed_public');
        expect(mockChat.getAttribute('embed-id')).toBe('embed_abc');
        expect(mockChat.getAttribute('assistant-title')).toBe('Helper');
        expect(mockChat.getAttribute('theme')).toBe('dark');
        expect(mockChat.getAttribute('interface-locale')).toBe('ru');
        expect(mockChat.getAttribute('platform-ui-origin')).toBe('https://api.humanitec.ru');
        expect(mockChat.getAttribute('voice-base-url')).toBe('https://api.humanitec.ru/voice');
        expect(mockChat.getAttribute('company-id')).toBe('company_1');
        expect(mockChat.getAttribute('toggle-event-name')).toBe('custom-toggle');
        expect(mockChat.showLauncher).toBe(true);
        expect(mockChat.getAttribute('voice-enabled')).toBe('');
        expect(mockChat.flowsBaseUrl).toBe('https://api.humanitec.ru/flows');
        expect(headChildren).toHaveLength(1);
        expect(headChildren[0].rel).toBe('stylesheet');
        expect(headChildren[0].href).toBe('https://api.humanitec.ru/static/core/lib/chat/chat-tokens.css');
        expect(headChildren[0].getAttribute('data-humanitec-chat-tokens')).toBe('1');
    });

    it('data-static-bearer не вызывает fetch', async () => {
        await mountFromScript(
            createMockScript({
                embedId: 'embed_static',
                flowsBaseUrl: 'https://api/flows',
                staticBearer: 'preview-token',
            }),
        );

        const headers = await mockChat.getAuthToken();
        expect(headers).toEqual({ Authorization: 'Bearer preview-token' });
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('getAuthToken POST /api/chat-token с embed_id origin TTL', async () => {
        fetchMock.mockResolvedValue({
            ok: true,
            json: async () => ({ token: 'short-lived-jwt' }),
        });

        await mountFromScript(
            createMockScript({
                embedId: 'embed_token',
                flowsBaseUrl: 'https://api/flows',
                chatTokenUrl: '/api/chat-token',
                tokenExpiresSeconds: '120',
            }),
        );

        const headers = await mockChat.getAuthToken();
        expect(headers).toEqual({ Authorization: 'Bearer short-lived-jwt' });
        expect(fetchMock).toHaveBeenCalledWith('/api/chat-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                embed_id: 'embed_token',
                origin: 'https://customer.example',
                expires_in_seconds: 120,
            }),
        });
    });

    it('бросает при 4xx token response и missing token field', async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 401 });

        await mountFromScript(
            createMockScript({
                embedId: 'embed_fail',
                flowsBaseUrl: 'https://api/flows',
            }),
        );
        await expect(mockChat.getAuthToken()).rejects.toThrow(/Cannot get embed session token/);

        fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
        await expect(mockChat.getAuthToken()).rejects.toThrow(/missing token field/);
    });

    it('humanitecEmbed API меняет chat и metadata hooks', async () => {
        await mountFromScript(
            createMockScript({
                embedId: 'embed_api',
                flowsBaseUrl: 'https://api/flows',
            }),
        );

        const api = globalThis.window.humanitecEmbed;
        expect(api.element).toBe(mockChat);

        api.setTheme('light');
        api.setLocale('en');
        api.setLauncherVisible(true);
        api.setAssistantTitle('Title');
        api.setFlowsBaseUrl('https://other/flows');
        api.setEventNamespace('ns');
        api.setToggleEventName('toggle-x');

        expect(mockChat.getAttribute('theme')).toBe('light');
        expect(mockChat.getAttribute('interface-locale')).toBe('en');
        expect(mockChat.showLauncher).toBe(true);
        expect(mockChat.getAttribute('assistant-title')).toBe('Title');
        expect(mockChat.flowsBaseUrl).toBe('https://other/flows');
        expect(mockChat.getAttribute('event-namespace')).toBe('ns');
        expect(mockChat.getAttribute('toggle-event-name')).toBe('toggle-x');

        const meta = { custom: true };
        api.setMetadataHooks(async () => meta, async () => ({ w: 1 }));
        expect(await mockChat.getExtraMetadataVariables()).toEqual(meta);
        expect(await mockChat.getContextVariables()).toEqual({ w: 1 });

        const customAuth = async () => ({ Authorization: 'Bearer custom' });
        api.setAuthProvider(customAuth);
        expect(await mockChat.getAuthToken()).toEqual({ Authorization: 'Bearer custom' });
    });

    it('defaults metadata/context variables from page', async () => {
        await mountFromScript(
            createMockScript({
                embedId: 'embed_meta',
                flowsBaseUrl: 'https://api/flows',
            }),
        );

        expect(await mockChat.getExtraMetadataVariables()).toEqual({
            page_url: 'https://customer.example/page',
            page_title: 'Embed host page',
        });
        expect(await mockChat.getContextVariables()).toEqual({
            viewport_width: 1280,
            viewport_height: 720,
        });
    });

    it('data-initial-open и show-launcher false', async () => {
        await mountFromScript(
            createMockScript({
                embedId: 'embed_open',
                flowsBaseUrl: 'https://api/flows',
                initialOpen: 'true',
                showLauncher: 'false',
            }),
        );

        expect(mockChat.initialOpen).toBe(true);
        expect(mockChat.getAttribute('initial-open')).toBe('');
        expect(mockChat.showLauncher).toBe(false);
    });
});
