import { afterEach, describe, expect, it, vi } from 'vitest';
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

function scriptFrom(dataset) {
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
        const config = buildHostConfig(script, 'tok_live', 'https://api.example/flows');
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
        expect(config.getRequestHeaders()).toEqual({ Authorization: 'Bearer tok_live' });
    });

    it('defaults theme, locale, branch and toggle', () => {
        const config = buildHostConfig(scriptFrom({ embedId: 'emb_2' }), 'tok', 'https://x/flows');
        expect(config.theme).toBe('auto');
        expect(config.locale).toBe('auto');
        expect(config.branchId).toBe('default');
        expect(config.toggleEventName).toBe(LINNEX_FLOW_UI_TOGGLE_EVENT);
        expect(config.credentials).toBe('include');
    });

    it('resolves presentation, position, launcher and credentials', () => {
        expect(resolvePresentation(scriptFrom({ presentation: 'page' }))).toBe('page');
        expect(resolvePresentation(scriptFrom({ presentation: 'drawer' }))).toBe('drawer');
        expect(resolvePresentation(scriptFrom({}))).toBe('drawer');
        expect(() => resolvePresentation(scriptFrom({ presentation: 'modal' }))).toThrow(
            /invalid data-presentation/,
        );
        expect(resolveLauncherPosition(scriptFrom({ position: 'bottom-left' }))).toBe('bottom-left');
        expect(resolveLauncherPosition(scriptFrom({}))).toBe('bottom-right');
        expect(resolveShowLauncher(scriptFrom({ showLauncher: 'false' }))).toBe(false);
        expect(resolveShowLauncher(scriptFrom({ showLauncher: 'true' }))).toBe(true);
        expect(resolveShowLauncher(scriptFrom({}))).toBe(true);
        expect(resolveCredentials(scriptFrom({ useCredentials: 'false' }))).toBe('omit');
        expect(resolveCredentials(scriptFrom({ useCredentials: 'true' }))).toBe('include');
        expect(resolveToggleEventName(scriptFrom({}))).toBe('linnex-flow-ui-toggle');
        expect(resolveToggleEventName(scriptFrom({ toggleEventName: '  ' }))).toBe(
            'linnex-flow-ui-toggle',
        );
    });
});

describe('bearerFor', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('uses data-static-bearer without token-url', async () => {
        await expect(
            bearerFor(scriptFrom({ staticBearer: 'preview-token' })),
        ).resolves.toBe('preview-token');
    });

    it('throws when token-url is missing and there is no static-bearer', async () => {
        await expect(bearerFor(scriptFrom({ embedId: 'emb_3' }))).rejects.toThrow(
            /requires data-token-url/,
        );
    });

    it('throws on invalid token-expires-seconds', async () => {
        await expect(
            bearerFor(scriptFrom({
                embedId: 'emb_4',
                tokenUrl: '/api/flow-ui-token',
                tokenExpiresSeconds: '0',
            })),
        ).rejects.toThrow(/invalid data-token-expires-seconds/);
    });

    it('POSTs data-token-url and returns token', async () => {
        const fetchMock = vi.fn(async () => ({
            ok: true,
            json: async () => ({ token: 'minted' }),
        }));
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('location', { origin: 'https://shop.example' });
        const token = await bearerFor(scriptFrom({
            embedId: 'emb_5',
            tokenUrl: '/api/flow-ui-token',
            tokenExpiresSeconds: '120',
        }));
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
});
