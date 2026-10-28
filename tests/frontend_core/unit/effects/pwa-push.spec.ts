/**
 * pwaEffect: установка PWA, разрешение на уведомления, веб-подписка (VAPID) и отписка.
 * Окружение браузера задаётся стабами глобалов; сеть — настоящий `Response` поверх подменённого `fetch`.
 */

import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { CoreEvents, createEvent } from '@platform/lib/events/contract.js';
import type { EffectCtx, PlatformEvent } from '@platform/lib/events/contract.js';
import { createPwaEffect, PWA_EVENTS } from '@platform/lib/events/effects/pwa.effect.js';

interface Dispatched {
    type: string;
    payload: unknown;
}

type PwaState = { pwa?: { deploymentVersion?: string | null } };

function makeCtx(): { ctx: EffectCtx<PwaState>; dispatched: Dispatched[] } {
    const dispatched: Dispatched[] = [];
    const ctx: EffectCtx<PwaState> = {
        dispatch: (type, payload) => {
            dispatched.push({ type: typeof type === 'string' ? type : type.type, payload });
        },
        getState: () => ({}),
    };
    return { ctx, dispatched };
}

function eventOf(type: string, payload: unknown = null): PlatformEvent {
    return createEvent(type, payload, { ts: 0, source: 'system' });
}

interface FakeSubscription {
    endpoint: string;
    toJSON: () => { keys?: { p256dh?: string; auth?: string } };
    getKey: (name: string) => ArrayBuffer;
    unsubscribe: ReturnType<typeof vi.fn>;
}

function makeSubscription(keys: { p256dh?: string; auth?: string }): FakeSubscription {
    return {
        endpoint: 'https://push.example/sub1',
        toJSON: () => ({ keys }),
        getKey: () => new Uint8Array([1, 2, 3]).buffer,
        unsubscribe: vi.fn(async () => true),
    };
}

function stubBrowser({ existing = null, created }: {
    existing?: FakeSubscription | null;
    created?: FakeSubscription;
}): { subscribe: ReturnType<typeof vi.fn> } {
    const subscribe = vi.fn(async () => created);
    const registration = {
        pushManager: {
            getSubscription: vi.fn(async () => existing),
            subscribe,
        },
    };
    vi.stubGlobal('navigator', { serviceWorker: { ready: Promise.resolve(registration) } });
    vi.stubGlobal('window', { PushManager: {}, __platformDeferredInstallPrompt__: null });
    return { subscribe };
}

type FetchSpy = Mock<(url: string, init?: RequestInit) => Promise<Response>>;

function stubFetchJson(routes: Record<string, unknown>): FetchSpy {
    const fetchSpy: FetchSpy = vi.fn(async (url: string) => {
        if (!(url in routes)) {
            return new Response(JSON.stringify({ detail: 'нет маршрута' }), { status: 404 });
        }
        return new Response(JSON.stringify(routes[url]), { status: 200, headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchSpy);
    return fetchSpy;
}

function subscribeBody(fetchSpy: FetchSpy): unknown {
    const call = fetchSpy.mock.calls.find(([url]) => url === '/svc/api/push/subscribe');
    if (!call) throw new Error('запрос подписки не отправлен');
    return JSON.parse(String(call[1]?.body));
}

beforeEach(() => {
    vi.stubGlobal('window', {});
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('pwaEffect: установка', () => {
    it('показывает отложенный prompt, сообщает об установке и очищает prompt', async () => {
        const prompt = { prompt: vi.fn(async () => undefined), userChoice: Promise.resolve({ outcome: 'accepted' }) };
        const windowStub = { __platformDeferredInstallPrompt__: prompt };
        vi.stubGlobal('window', windowStub);
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.INSTALL_PROMPT_REQUESTED), ctx);
        expect(prompt.prompt).toHaveBeenCalledOnce();
        expect(dispatched.map((d) => d.type)).toEqual([CoreEvents.PWA_INSTALLED]);
        expect(windowStub.__platformDeferredInstallPrompt__).toBeNull();
    });

    it('отказ пользователя установку не сообщает, но prompt очищается', async () => {
        const prompt = { prompt: vi.fn(async () => undefined), userChoice: Promise.resolve({ outcome: 'dismissed' }) };
        const windowStub = { __platformDeferredInstallPrompt__: prompt };
        vi.stubGlobal('window', windowStub);
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.INSTALL_PROMPT_REQUESTED), ctx);
        expect(dispatched).toEqual([]);
        expect(windowStub.__platformDeferredInstallPrompt__).toBeNull();
    });

    it('без отложенного prompt ничего не делает', async () => {
        vi.stubGlobal('window', { __platformDeferredInstallPrompt__: null });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.INSTALL_PROMPT_REQUESTED), ctx);
        expect(dispatched).toEqual([]);
    });
});

describe('pwaEffect: разрешение на уведомления', () => {
    it('запрашивает разрешение у браузера и публикует результат', async () => {
        vi.stubGlobal('Notification', { permission: 'default', requestPermission: vi.fn(async () => 'granted') });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED), ctx);
        expect(dispatched).toEqual([{ type: CoreEvents.PWA_PUSH_PERMISSION_REQUESTED, payload: { permission: 'granted' } }]);
    });

    it('без Notification ничего не публикует', async () => {
        vi.stubGlobal('Notification', undefined);
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED), ctx);
        expect(dispatched).toEqual([]);
    });
});

describe('pwaEffect: веб-подписка', () => {
    it('уже существующая подписка возвращается без запросов к серверу', async () => {
        stubBrowser({ existing: makeSubscription({}) });
        const fetchSpy = stubFetchJson({});
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect({ baseUrl: '/svc' })(eventOf(PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED), ctx);
        expect(fetchSpy).not.toHaveBeenCalled();
        expect(dispatched).toEqual([
            { type: CoreEvents.PWA_PUSH_REGISTERED, payload: { endpoint: 'https://push.example/sub1', transport: 'web_vapid' } },
        ]);
    });

    it('создаёт подписку по VAPID-ключу и отправляет ключи на сервер', async () => {
        const created = makeSubscription({ p256dh: 'P', auth: 'A' });
        const { subscribe } = stubBrowser({ created });
        const fetchSpy = stubFetchJson({ '/svc/api/push/vapid-public-key': { publicKey: 'AQAB' }, '/svc/api/push/subscribe': {} });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect({ baseUrl: '/svc' })(eventOf(PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED), ctx);
        expect(subscribe).toHaveBeenCalledOnce();
        expect(subscribeBody(fetchSpy)).toEqual({
            transport: 'web_vapid',
            endpoint: 'https://push.example/sub1',
            keys: { p256dh: 'P', auth: 'A' },
            platform: 'web',
        });
        expect(dispatched.map((d) => d.type)).toEqual([CoreEvents.PWA_PUSH_REGISTERED]);
    });

    it('ключи берутся из getKey, когда toJSON их не отдал', async () => {
        stubBrowser({ created: makeSubscription({}) });
        const fetchSpy = stubFetchJson({ '/svc/api/push/vapid-public-key': { publicKey: 'AQAB' }, '/svc/api/push/subscribe': {} });
        const { ctx } = makeCtx();
        await createPwaEffect({ baseUrl: '/svc' })(eventOf(PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED), ctx);
        expect(subscribeBody(fetchSpy)).toMatchObject({ keys: { p256dh: 'AQID', auth: 'AQID' } });
    });

    it('без VAPID-ключа публикует PUSH_SUBSCRIBE_FAILED', async () => {
        stubBrowser({ created: makeSubscription({}) });
        stubFetchJson({ '/svc/api/push/vapid-public-key': {} });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect({ baseUrl: '/svc' })(eventOf(PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED), ctx);
        expect(dispatched).toEqual([{ type: PWA_EVENTS.PUSH_SUBSCRIBE_FAILED, payload: { message: 'VAPID public key недоступен' } }]);
    });

    it('браузер без PushManager не подписывается', async () => {
        stubBrowser({});
        vi.stubGlobal('window', {});
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.PUSH_SUBSCRIBE_REQUESTED), ctx);
        expect(dispatched).toEqual([]);
    });
});

describe('pwaEffect: отписка', () => {
    it('отписывает существующую подписку и публикует UNSUBSCRIBED', async () => {
        const existing = makeSubscription({});
        stubBrowser({ existing });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.PUSH_UNSUBSCRIBE_REQUESTED), ctx);
        expect(existing.unsubscribe).toHaveBeenCalledOnce();
        expect(dispatched.map((d) => d.type)).toEqual([PWA_EVENTS.PUSH_UNSUBSCRIBED]);
    });

    it('без подписки всё равно публикует UNSUBSCRIBED', async () => {
        stubBrowser({ existing: null });
        const { ctx, dispatched } = makeCtx();
        await createPwaEffect()(eventOf(PWA_EVENTS.PUSH_UNSUBSCRIBE_REQUESTED), ctx);
        expect(dispatched.map((d) => d.type)).toEqual([PWA_EVENTS.PUSH_UNSUBSCRIBED]);
    });
});
