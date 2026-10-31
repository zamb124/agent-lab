/**
 * ``HtmlSandboxBridge``: хостовая сторона моста ``postMessage`` блока ``html``. Проверяет
 * границу протокола iframe → хост: чужие источники игнорируются, неизвестные типы и
 * битые сообщения становятся ``onError``, ``resize`` зажимается в допустимые границы,
 * ``open_url`` принимает только http(s); хост → iframe шлёт лишь ``state`` и ``theme``.
 */

import { expect } from '../helpers/render.js';
import {
    FLOW_UI_HTML_MAX_HEIGHT,
    FLOW_UI_HTML_MIN_HEIGHT,
    HtmlSandboxBridge,
} from '@platform/lib/flow-ui/runtime/html-sandbox.js';
import type { TestEl } from '../helpers/dom.js';

const ECHO_SRCDOC = '<!doctype html><html><body><script>'
    + 'window.addEventListener("message", (event) => { if (event.source === parent && event.data && event.data.type === "__echo") parent.postMessage(event.data.message, "*"); });'
    + 'window.addEventListener("message", (event) => { if (event.source === parent && event.data && (event.data.type === "state" || event.data.type === "theme")) parent.postMessage({ type: "value", value: event.data }, "*"); });'
    + '</script></body></html>';

function recorder() {
    const calls: { action: any[]; value: any[]; resize: any[]; error: any[]; openUrl: any[] } = { action: [], value: [], resize: [], error: [], openUrl: [] };
    return {
        calls,
        handlers: {
            onAction: (name: any, payload: any) => calls.action.push({ name, payload }),
            onValue: (value: any) => calls.value.push(value!),
            onResize: (height: any) => calls.resize.push(height!),
            onError: (error: any) => calls.error.push(error!),
            onOpenUrl: (url: any) => calls.openUrl.push(url!),
        },
    };
}

const mounted: any[] = [];

/** Слушатель ``load`` ставится до вставки в DOM: srcdoc может загрузиться раньше await fixture. */
async function mountIframe() {
    const iframe = document.createElement('iframe');
    iframe.setAttribute('sandbox', 'allow-scripts');
    const loaded = new Promise<void>((resolve) => iframe.addEventListener('load', () => resolve(), { once: true }));
    iframe.srcdoc = ECHO_SRCDOC;
    document.body.appendChild(iframe);
    mounted.push(iframe);
    await loaded;
    return iframe;
}

function nextTick() {
    return new Promise((resolve) => setTimeout(resolve, 20));
}

/** Просит iframe отправить хосту ``message`` от своего лица, как это делает ``flowUi``. */
async function fromFrame(iframe: any, message: any) {
    iframe.contentWindow.postMessage({ type: '__echo', message }, '*');
    await nextTick();
}

describe('HtmlSandboxBridge', function () {
    this.timeout(10_000);

    let bridges: any[] = [];

    afterEach(() => {
        for (const bridge of bridges) bridge.dispose();
        bridges = [];
        for (const iframe of mounted.splice(0)) iframe.remove();
    });

    function attach(iframe: any, handlers: any) {
        const bridge = new HtmlSandboxBridge({ iframe, ...handlers });
        bridges.push(bridge);
        return bridge;
    }

    it('requires an iframe and every handler', async () => {
        const iframe = await mountIframe();
        const { handlers } = recorder();
        expect(() => new HtmlSandboxBridge(null!)).to.throw(/requires iframe/);
        expect(() => new HtmlSandboxBridge({ iframe: document.body as unknown as HTMLIFrameElement, ...handlers })).to.throw(/requires iframe/);
        for (const name of Object.keys(handlers)) {
            expect(() => new HtmlSandboxBridge({ iframe, ...handlers, [name]: null as any }), name).to.throw(new RegExp(`requires ${name}`));
        }
    });

    it('routes action, value, open_url and error messages from the frame', async () => {
        const iframe = await mountIframe();
        const { calls, handlers } = recorder();
        attach(iframe, handlers);
        await fromFrame(iframe, { type: 'action', name: 'save', payload: { plan: 'pro' } });
        await fromFrame(iframe, { type: 'action', name: 'bare' });
        await fromFrame(iframe, { type: 'action', name: 'list', payload: [1, 2] });
        await fromFrame(iframe, { type: 'value', value: 'yes' });
        await fromFrame(iframe, { type: 'value' });
        await fromFrame(iframe, { type: 'open_url', url: 'https://example.com/x' });
        await fromFrame(iframe, { type: 'open_url', url: 'HTTP://EXAMPLE.COM' });
        await fromFrame(iframe, { type: 'error', message: 'boom', stack: 'trace' });
        await fromFrame(iframe, { type: 'error', message: 5 });
        expect(calls.action).to.deep.equal([
            { name: 'save', payload: { plan: 'pro' } },
            { name: 'bare', payload: {} },
            { name: 'list', payload: [1, 2] },
        ]);
        expect(calls.value).to.deep.equal(['yes', null]);
        expect(calls.openUrl).to.deep.equal(['https://example.com/x', 'HTTP://EXAMPLE.COM']);
        expect(calls.error).to.deep.equal([
            { message: 'boom', stack: 'trace' },
            { message: 'error', stack: '' },
        ]);
    });

    it('reports unknown or malformed frame messages as errors without calling other handlers', async () => {
        const iframe = await mountIframe();
        const { calls, handlers } = recorder();
        attach(iframe, handlers);
        await fromFrame(iframe, { type: 'navigate', page_id: 'x' });
        await fromFrame(iframe, 'plain string');
        await fromFrame(iframe, null);
        await fromFrame(iframe, { type: 'action', name: '' });
        await fromFrame(iframe, { type: 'action' });
        await fromFrame(iframe, { type: 'resize', height: 'tall' });
        await fromFrame(iframe, { type: 'resize', height: Number.NaN });
        await fromFrame(iframe, { type: 'resize', height: Number.POSITIVE_INFINITY });
        await fromFrame(iframe, { type: 'open_url', url: 'javascript:alert(1)' });
        await fromFrame(iframe, { type: 'open_url', url: 'ftp://files' });
        await fromFrame(iframe, { type: 'open_url', url: '' });
        await fromFrame(iframe, { type: 'open_url' });
        expect(calls.error.map((error) => error.message)).to.deep.equal([
            'flow-ui: unknown sandbox message "navigate"',
            'flow-ui: unknown sandbox message undefined',
            'flow-ui: unknown sandbox message undefined',
            'flow-ui: sandbox action requires name',
            'flow-ui: sandbox action requires name',
            'flow-ui: sandbox resize requires numeric height',
            'flow-ui: sandbox resize requires numeric height',
            'flow-ui: sandbox resize requires numeric height',
            'flow-ui: sandbox open_url requires http(s) url',
            'flow-ui: sandbox open_url requires http(s) url',
            'flow-ui: sandbox open_url requires http(s) url',
            'flow-ui: sandbox open_url requires http(s) url',
        ]);
        expect(calls.action).to.deep.equal([]);
        expect(calls.resize).to.deep.equal([]);
        expect(calls.openUrl).to.deep.equal([]);
    });

    it('clamps resize heights to the platform bounds and rounds up', async () => {
        const iframe = await mountIframe();
        const { calls, handlers } = recorder();
        attach(iframe, handlers);
        await fromFrame(iframe, { type: 'resize', height: 0 });
        await fromFrame(iframe, { type: 'resize', height: -50 });
        await fromFrame(iframe, { type: 'resize', height: 100.2 });
        await fromFrame(iframe, { type: 'resize', height: 99_999 });
        await fromFrame(iframe, { type: 'resize', height: FLOW_UI_HTML_MAX_HEIGHT });
        expect(calls.resize).to.deep.equal([
            FLOW_UI_HTML_MIN_HEIGHT,
            FLOW_UI_HTML_MIN_HEIGHT,
            101,
            FLOW_UI_HTML_MAX_HEIGHT,
            FLOW_UI_HTML_MAX_HEIGHT,
        ]);
    });

    it('ignores messages from other windows and stops listening after dispose', async () => {
        const iframe = await mountIframe();
        const other = await mountIframe();
        const { calls, handlers } = recorder();
        const bridge = attach(iframe, handlers);
        await fromFrame(other, { type: 'action', name: 'from-other' });
        window.postMessage({ type: 'action', name: 'from-host' }, '*');
        await nextTick();
        expect(calls.action).to.deep.equal([]);
        expect(calls.error).to.deep.equal([]);
        bridge.dispose();
        await fromFrame(iframe, { type: 'action', name: 'after-dispose' });
        expect(calls.action).to.deep.equal([]);
    });

    it('sends only state and theme to the frame and resends both after reload', async () => {
        const iframe = await mountIframe();
        const { calls, handlers } = recorder();
        const bridge = attach(iframe, handlers);
        bridge.sendState({ total: 1 });
        bridge.sendTheme({ '--flow-ui-text': '#123', 'not-a-token': 'x', '--flow-ui-accent': 'a<b>c' });
        await nextTick();
        expect(calls.value).to.deep.equal([
            { type: 'state', state: { total: 1 } },
            { type: 'theme', css: ':root{--flow-ui-text:#123;--flow-ui-accent:abc}' },
        ]);
        bridge.resend();
        await nextTick();
        expect(calls.value.slice(2)).to.deep.equal([
            { type: 'theme', css: ':root{--flow-ui-text:#123;--flow-ui-accent:abc}' },
            { type: 'state', state: { total: 1 } },
        ]);
        expect(() => (bridge as unknown as { _post(msg: unknown): void })._post({ type: 'action', name: 'x' })).to.throw(/host cannot send action/);
    });
});
