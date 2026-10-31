import { afterEach, describe, expect, it, vi } from 'vitest';
import { prop } from '../../helpers/prop.js';
import { platformStaticSrc } from '../../../../core/frontend/static/lib/flow-ui/shell/brand-logo.js';
import {
    LINNEX_FLOW_UI_TOGGLE_EVENT,
    bearerFor,
    buildHostConfig,
    resolveCredentials,
    resolveLauncherPosition,
    resolvePresentation,
    resolveShowLauncher,
    resolveToggleEventName,
} from '../../../../core/frontend/static/lib/flow-ui/shell/embed-script-config.js';

function scriptFrom(dataset: Record<string, string>) {
    return { dataset };
}

describe('platformStaticSrc', () => {
    it('prefixes origin when set', () => {
        expect(
            platformStaticSrc('https://api.example', '/static/core/assets/icons/send.svg'),
        ).toBe('https://api.example/static/core/assets/icons/send.svg');
    });

    it('keeps a relative path when origin is empty', () => {
        expect(platformStaticSrc('', '/static/core/assets/icons/send.svg')).toBe(
            '/static/core/assets/icons/send.svg',
        );
    });

    it('rejects a path outside /static/core/', () => {
        expect(() => platformStaticSrc('https://api.example', '/icons/send.svg')).toThrow(
            /must start with \/static\/core\//,
        );
    });
});

describe('embed script data-* → host config', () => {
    it('maps every live data-* that belongs on the host', () => {
        const script = scriptFrom({
            embedId: 'emb_1',
            flowId: 'flow_a',
            branchId: 'docs',
            contextId: 'ctx_1',
            theme: 'dark',
            locale: 'ru',
            companyId: 'co_1',
            voiceBaseUrl: 'https://api.example/voice',
            platformUiOrigin: 'https://api.example/',
            useCredentials: 'false',
            toggleEventName: 'site-open-chat',
        });
        const config = Reflect.apply(buildHostConfig, null, [script, 'tok_live', 'https://api.example/flows']);
        expect(config).toMatchObject({
            embedId: 'emb_1',
            flowId: 'flow_a',
            branchId: 'docs',
            contextId: 'ctx_1',
            theme: 'dark',
            locale: 'ru',
            profile: 'embed_public',
            companyId: 'co_1',
            voiceBaseUrl: 'https://api.example/voice',
            platformUiOrigin: 'https://api.example',
            credentials: 'omit',
            toggleEventName: 'site-open-chat',
            baseUrl: 'https://api.example/flows',
        });
        const getRequestHeaders = prop(config, 'getRequestHeaders');
        if (typeof getRequestHeaders !== 'function') {
            throw new Error('getRequestHeaders is not a function');
        }
        expect(getRequestHeaders()).toEqual({ Authorization: 'Bearer tok_live' });
    });

    it('defaults theme, locale, branch and toggle', () => {
        const config = Reflect.apply(buildHostConfig, null, [scriptFrom({ embedId: 'emb_2' }), 'tok', 'https://x/flows']);
        expect(config.theme).toBe('auto');
        expect(config.locale).toBe('auto');
        expect(config.branchId).toBe('default');
        expect(config.toggleEventName).toBe(LINNEX_FLOW_UI_TOGGLE_EVENT);
        expect(config.credentials).toBe('include');
    });

    it('resolves presentation, position, launcher and credentials', () => {
        expect(Reflect.apply(resolvePresentation, null, [scriptFrom({ presentation: 'page' })])).toBe('page');
        expect(Reflect.apply(resolvePresentation, null, [scriptFrom({ presentation: 'drawer' })])).toBe('drawer');
        expect(Reflect.apply(resolvePresentation, null, [scriptFrom({})])).toBe('drawer');
        expect(() => Reflect.apply(resolvePresentation, null, [scriptFrom({ presentation: 'modal' })])).toThrow(
            /invalid data-presentation/,
        );
        expect(Reflect.apply(resolveLauncherPosition, null, [scriptFrom({ position: 'bottom-left' })])).toBe('bottom-left');
        expect(Reflect.apply(resolveLauncherPosition, null, [scriptFrom({})])).toBe('bottom-right');
        expect(Reflect.apply(resolveShowLauncher, null, [scriptFrom({ showLauncher: 'false' })])).toBe(false);
        expect(Reflect.apply(resolveShowLauncher, null, [scriptFrom({ showLauncher: 'true' })])).toBe(true);
        expect(Reflect.apply(resolveShowLauncher, null, [scriptFrom({})])).toBe(true);
        expect(Reflect.apply(resolveCredentials, null, [scriptFrom({ useCredentials: 'false' })])).toBe('omit');
        expect(Reflect.apply(resolveCredentials, null, [scriptFrom({ useCredentials: 'true' })])).toBe('include');
        expect(Reflect.apply(resolveToggleEventName, null, [scriptFrom({})])).toBe('linnex-flow-ui-toggle');
        expect(Reflect.apply(resolveToggleEventName, null, [scriptFrom({ toggleEventName: '  ' })])).toBe(
            'linnex-flow-ui-toggle',
        );
    });

    it('normalizes case and whitespace but rejects unknown corners and empty-vs-missing differently', () => {
        expect(Reflect.apply(resolvePresentation, null, [scriptFrom({ presentation: '  PAGE ' })])).toBe('page');
        expect(Reflect.apply(resolveLauncherPosition, null, [scriptFrom({ position: ' Bottom-Left ' })])).toBe('bottom-left');
        expect(() => Reflect.apply(resolveLauncherPosition, null, [scriptFrom({ position: 'top-right' })])).toThrow(
            /invalid data-position "top-right"/,
        );
        expect(() => Reflect.apply(resolveLauncherPosition, null, [scriptFrom({ position: 'fullscreen' })])).toThrow(/invalid data-position/);
        // Пустой атрибут — это тоже «дефолт», как и отсутствующий
        expect(Reflect.apply(resolvePresentation, null, [scriptFrom({ presentation: '' })])).toBe('drawer');
        expect(Reflect.apply(resolveLauncherPosition, null, [scriptFrom({ position: '' })])).toBe('bottom-right');
        expect(Reflect.apply(resolveShowLauncher, null, [scriptFrom({ showLauncher: '' })])).toBe(true);
        expect(Reflect.apply(resolveShowLauncher, null, [scriptFrom({ showLauncher: 'FALSE' })])).toBe(true);
        expect(Reflect.apply(resolveCredentials, null, [scriptFrom({ useCredentials: 'omit' })])).toBe('include');
        expect(Reflect.apply(resolveToggleEventName, null, [scriptFrom({ toggleEventName: ' my-toggle ' })])).toBe('my-toggle');
    });
});

describe('bearerFor', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('uses data-static-bearer without token-url', async () => {
        await expect(
            Reflect.apply(bearerFor, null, [scriptFrom({ staticBearer: 'preview-token' })]),
        ).resolves.toBe('preview-token');
    });

    it('throws when token-url is missing and there is no static-bearer', async () => {
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_3' })])).rejects.toThrow(
            /requires data-token-url/,
        );
    });

    it('throws on invalid token-expires-seconds', async () => {
        await expect(
            Reflect.apply(bearerFor, null, [scriptFrom({
                embedId: 'emb_4',
                tokenUrl: '/api/flow-ui-token',
                tokenExpiresSeconds: '0',
            })]),
        ).rejects.toThrow(/invalid data-token-expires-seconds/);
    });

    it('POSTs data-token-url and returns token', async () => {
        const fetchMock = vi.fn(async () => ({
            ok: true,
            json: async () => ({ token: 'minted' }),
        }));
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('location', { origin: 'https://shop.example' });
        const token = await Reflect.apply(bearerFor, null, [scriptFrom({
            embedId: 'emb_5',
            tokenUrl: '/api/flow-ui-token',
            tokenExpiresSeconds: '120',
        })]);
        expect(token).toBe('minted');
        expect(fetchMock).toHaveBeenCalledWith('/api/flow-ui-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                embed_id: 'emb_5',
                origin: 'https://shop.example',
                expires_in_seconds: 120,
            }),
        });
    });

    it('defaults expiry to 300 seconds and prefers a static bearer over token-url', async () => {
        const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({ ok: true, json: async () => ({ token: 'minted' }) }));
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('location', { origin: 'https://shop.example' });
        await Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_6', tokenUrl: '/api/flow-ui-token', tokenExpiresSeconds: '' })]);
        expect(JSON.parse(String(prop(fetchMock.mock.calls[0]?.[1], 'body'))).expires_in_seconds).toBe(300);
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ staticBearer: 'static', tokenUrl: '/api/flow-ui-token' })])).resolves.toBe('static');
        expect(fetchMock).toHaveBeenCalledTimes(1);
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ staticBearer: '   ', embedId: 'emb_7' })])).rejects.toThrow(/requires data-token-url/);
    });

    it('rejects non-numeric expiry, HTTP failures and responses without a token', async () => {
        await expect(
            Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_8', tokenUrl: '/t', tokenExpiresSeconds: 'soon' })]),
        ).rejects.toThrow(/invalid data-token-expires-seconds/);
        vi.stubGlobal('location', { origin: 'https://shop.example' });
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) })));
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_9', tokenUrl: '/t' })])).rejects.toThrow(/token: HTTP 403/);
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ token: '  ' }) })));
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_9', tokenUrl: '/t' })])).rejects.toThrow(/response has no token/);
        vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => null })));
        await expect(Reflect.apply(bearerFor, null, [scriptFrom({ embedId: 'emb_9', tokenUrl: '/t' })])).rejects.toThrow(/response has no token/);
    });
});
