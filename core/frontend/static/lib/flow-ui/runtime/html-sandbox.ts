/**
 * Sandbox блока ``html``: iframe с opaque origin (единственный флаг ``sandbox="allow-scripts"``),
 * фиксированный CSP в ``srcdoc``, токены темы и мост ``postMessage``.
 *
 * Хост → iframe: ``state {state}`` (проекция только по ``fields`` и ``data-bind``/``data-show``
 * путям блока), ``theme {tokens}``. iframe → хост: ``action {name, payload}``, ``value {value}``,
 * ``resize {height}``, ``open_url {url}``, ``error {message, stack}``. Любой другой тип — ошибка.
 * API внутри iframe — ``flowUi.state``, ``flowUi.onChange``, ``flowUi.send``, ``flowUi.setValue``,
 * ``flowUi.resize``, ``flowUi.openUrl``; декларативно — ``data-bind`` (textContent) и ``data-show``.
 */

import { isPlainRecord } from '../../events/payload.js';
import { STATE_PATH_PATTERN } from '../protocol/constants.js';
import { valueAtPath } from './templating.js';

export const FLOW_UI_HTML_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https:; font-src data: https:; media-src https:";
export const FLOW_UI_HTML_SANDBOX = 'allow-scripts';
export const FLOW_UI_HTML_MIN_HEIGHT = 24;
export const FLOW_UI_HTML_MAX_HEIGHT = 4000;

const HOST_MESSAGE_TYPES = new Set(['state', 'theme']);
const FRAME_MESSAGE_TYPES = new Set(['action', 'value', 'resize', 'open_url', 'error']);

export const FLOW_UI_HTML_THEME_TOKENS = Object.freeze([
    '--flow-ui-text', '--flow-ui-heading', '--flow-ui-muted', '--flow-ui-border', '--flow-ui-panel',
    '--flow-ui-surface', '--flow-ui-input', '--flow-ui-accent', '--flow-ui-accent-hover', '--flow-ui-on-accent',
    '--flow-ui-accent-muted', '--flow-ui-radius', '--flow-ui-radius-md', '--flow-ui-page-background',
]);

/** Тёмная тема хоста: модалка и первый кадр iframe часто ещё без computed tokens. */
export const FLOW_UI_HTML_THEME_FALLBACKS = Object.freeze({
    '--flow-ui-text': 'rgba(255, 255, 255, 0.95)',
    '--flow-ui-heading': 'rgba(255, 255, 255, 0.95)',
    '--flow-ui-muted': 'rgba(255, 255, 255, 0.45)',
    '--flow-ui-border': 'rgba(255, 255, 255, 0.1)',
    '--flow-ui-panel': 'rgba(35, 35, 55, 0.85)',
    '--flow-ui-surface': 'rgba(35, 35, 55, 0.85)',
    '--flow-ui-input': 'rgba(0, 0, 0, 0.22)',
    '--flow-ui-accent': '#99A6F9',
    '--flow-ui-accent-hover': '#8794F0',
    '--flow-ui-on-accent': '#0f0f1a',
    '--flow-ui-accent-muted': 'rgba(153, 166, 249, 0.15)',
    '--flow-ui-radius': '24px',
    '--flow-ui-radius-md': '12px',
    '--flow-ui-page-background': '#16213e',
});

const BINDING_ATTRIBUTES = new Set(['data-bind', 'data-show']);
// Разметка, которую HTML-парсер не читает как теги: комментарии, CDATA/декларации/PI
// и тела raw-text элементов (сами открывающие теги остаются — их атрибуты считаются).
const SKIPPED_MARKUP_RE = /<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<![^>]*>|<\?[^>]*>|(<(script|style|textarea|title)\b(?:"[^"]*"|'[^']*'|[^'">])*>)[\s\S]*?(?:<\/\2\s*>|$)/gi;
const START_TAG_RE = /<[a-zA-Z][^\s/>]*((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
const ATTRIBUTE_RE = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
const NAMED_CHAR_REFS = Object.freeze({ amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" });

function namedCharRef(name: string): string | undefined {
    switch (name) {
        case 'amp': return NAMED_CHAR_REFS.amp;
        case 'lt': return NAMED_CHAR_REFS.lt;
        case 'gt': return NAMED_CHAR_REFS.gt;
        case 'quot': return NAMED_CHAR_REFS.quot;
        case 'apos': return NAMED_CHAR_REFS.apos;
        default: return undefined;
    }
}

function capture(value: string | undefined): string {
    return value === undefined ? '' : value;
}

function decodeCharRefs(value: string): string {
    return value.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (reference: string, body: string) => {
        if (body[0] === '#') {
            const hex = body[1] === 'x' || body[1] === 'X';
            return String.fromCodePoint(Number.parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10));
        }
        const named = namedCharRef(body.toLowerCase());
        return named === undefined ? reference : named;
    });
}

/**
 * Пути ``data-bind`` / ``data-show`` из ``source`` в порядке появления; невалидный путь — ошибка автора.
 * Правила те же, что у ``core.flow_ui.html_bindings``: атрибуты читаются только в открывающих тегах,
 * имена без учёта регистра, ссылки на символы в значениях раскрываются, атрибут без значения — ошибка.
 */
export function htmlBoundPaths(source: unknown): string[] {
    const paths: string[] = [];
    const invalid: string[] = [];
    const markup = String(source).replace(SKIPPED_MARKUP_RE, (_skipped: string, rawTextStart: string | undefined) => capture(rawTextStart));
    for (const tag of markup.matchAll(START_TAG_RE)) {
        for (const attribute of capture(tag[1]).matchAll(ATTRIBUTE_RE)) {
            const name = capture(attribute[1]).toLowerCase();
            if (!BINDING_ATTRIBUTES.has(name)) continue;
            const rawValue = attribute[2] ?? attribute[3] ?? attribute[4];
            const path = rawValue === undefined ? '' : decodeCharRefs(rawValue).trim();
            if (!STATE_PATH_PATTERN.test(path)) {
                invalid.push(`${name}=${rawValue === undefined ? 'None' : JSON.stringify(decodeCharRefs(rawValue))}`);
                continue;
            }
            if (!paths.includes(path)) paths.push(path);
        }
    }
    if (invalid.length > 0) throw new Error(`flow-ui: html block has invalid state path in ${invalid.join(', ')}`);
    return paths;
}

/** Проекция state для блока: только ``fields`` и пути привязок. */
export function htmlBlockState(block: { fields?: unknown; source?: unknown } | Record<string, unknown>, state: unknown): Record<string, unknown> {
    const projection: Record<string, unknown> = {};
    const paths = [...(Array.isArray(block.fields) ? block.fields : []), ...htmlBoundPaths(block.source)];
    for (const path of paths) {
        const value = valueAtPath(state, path);
        if (value === undefined) continue;
        const segments = String(path).split('.');
        let target = projection;
        for (const segment of segments.slice(0, -1)) {
            let child = target[segment];
            if (!isPlainRecord(child)) {
                const created: Record<string, unknown> = {};
                target[segment] = created;
                child = created;
            }
            if (!isPlainRecord(child)) {
                throw new Error('flow-ui: html state path segment is not an object');
            }
            target = child;
        }
        const leaf = segments[segments.length - 1];
        if (leaf === undefined) {
            throw new Error('flow-ui: html state path is empty');
        }
        target[leaf] = value;
    }
    return projection;
}

function themeTokenSources(element: Element): Element[] {
    const sources: Element[] = [];
    const seen = new Set<Element>();
    let node: Element | null = element;
    while (node && !seen.has(node)) {
        seen.add(node);
        sources.push(node);
        if (typeof document !== 'undefined' && node === document.documentElement) break;
        if (node.parentElement) {
            node = node.parentElement;
            continue;
        }
        const root: Node | null = typeof node.getRootNode === 'function' ? node.getRootNode() : null;
        node = root instanceof ShadowRoot ? root.host : null;
    }
    if (typeof document !== 'undefined' && document.documentElement && !seen.has(document.documentElement)) {
        sources.push(document.documentElement);
    }
    return sources;
}

export function readThemeTokens(element: Element): Record<string, string> {
    const tokens: Record<string, string> = {};
    const sources = themeTokenSources(element);
    for (const name of FLOW_UI_HTML_THEME_TOKENS) {
        let value = '';
        for (const source of sources) {
            if (!source || typeof getComputedStyle !== 'function') continue;
            value = getComputedStyle(source).getPropertyValue(name).trim();
            if (value !== '') break;
        }
        const fallbacks: Readonly<Record<string, string>> = FLOW_UI_HTML_THEME_FALLBACKS;
        const fallback = fallbacks[name];
        if (fallback === undefined) {
            throw new Error(`flow-ui: theme fallback missing for ${name}`);
        }
        tokens[name] = value !== '' ? value : fallback;
    }
    return tokens;
}

function themeCss(tokens: Record<string, unknown>): string {
    const declarations = Object.entries(tokens)
        .filter(([name]) => /^--[a-z0-9-]+$/i.test(name))
        .map(([name, value]) => `${name}:${String(value).replace(/[<>]/g, '')}`);
    return `:root{${declarations.join(';')}}`;
}

/** Высота кадра — ``scrollHeight``: ``getBoundingClientRect`` html часто равен вьюпорту iframe и залипает на min-height. */
const BOOTSTRAP = `
(() => {
  const listeners = new Set();
  const originals = new WeakMap();
  let state = {};
  const post = (message) => parent.postMessage(message, '*');
  const walk = (value, path) => path.split('.').reduce((acc, key) => (acc && typeof acc === 'object' ? acc[key] : undefined), value);
  const present = (value) => value !== undefined && value !== null && value !== '' && value !== false && !(Array.isArray(value) && value.length === 0);
  const render = () => {
    for (const el of document.querySelectorAll('[data-bind]')) {
      if (!originals.has(el)) originals.set(el, el.textContent);
      const value = walk(state, el.getAttribute('data-bind'));
      el.textContent = value === undefined || value === null ? originals.get(el) : (typeof value === 'object' ? JSON.stringify(value) : String(value));
    }
    for (const el of document.querySelectorAll('[data-show]')) {
      el.hidden = !present(walk(state, el.getAttribute('data-show')));
    }
  };
  const resize = () => post({ type: 'resize', height: Math.ceil(Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0, document.documentElement.getBoundingClientRect().height)) });
  window.flowUi = Object.freeze({
    get state() { return state; },
    onChange(cb) { if (typeof cb !== 'function') throw new TypeError('flowUi.onChange expects a function'); listeners.add(cb); return () => listeners.delete(cb); },
    send(action, payload) { if (typeof action !== 'string' || action === '') throw new TypeError('flowUi.send expects action name'); post({ type: 'action', name: action, payload: payload === undefined ? {} : payload }); },
    setValue(value) { post({ type: 'value', value: value === undefined ? null : value }); },
    resize,
    openUrl(url) { if (typeof url !== 'string' || url === '') throw new TypeError('flowUi.openUrl expects url'); post({ type: 'open_url', url }); },
  });
  window.addEventListener('message', (event) => {
    if (event.source !== parent || !event.data || typeof event.data !== 'object') return;
    if (event.data.type === 'state') { state = event.data.state && typeof event.data.state === 'object' ? event.data.state : {}; render(); for (const cb of listeners) cb(state); resize(); return; }
    if (event.data.type === 'theme') { const style = document.getElementById('flow-ui-theme'); if (style) style.textContent = event.data.css; }
  });
  window.addEventListener('error', (event) => post({ type: 'error', message: String(event.message || 'error'), stack: event.error && event.error.stack ? String(event.error.stack) : '' }));
  window.addEventListener('unhandledrejection', (event) => post({ type: 'error', message: String(event.reason && event.reason.message || event.reason || 'rejection'), stack: event.reason && event.reason.stack ? String(event.reason.stack) : '' }));
  document.addEventListener('DOMContentLoaded', () => { render(); resize(); new ResizeObserver(resize).observe(document.documentElement); });
})();
`;

/** ``srcdoc`` блока: CSP, токены темы, bootstrap ``flowUi``, затем ``source`` автора. */
export function buildHtmlSrcdoc({ source, tokens = {} }: { source: unknown; tokens?: Record<string, unknown> }): string {
    if (typeof source !== 'string') throw new Error('flow-ui: html block source must be a string');
    return `<!doctype html><html><head><meta charset="utf-8">`
        + `<meta http-equiv="Content-Security-Policy" content="${FLOW_UI_HTML_CSP}">`
        + `<style id="flow-ui-theme">${themeCss(tokens)}</style>`
        + `<style>html,body{margin:0;height:auto;background:transparent;color:var(--flow-ui-text,inherit);font:14px/1.45 system-ui,sans-serif}</style>`
        + `<script>${BOOTSTRAP}</script></head><body>${source}</body></html>`;
}

export interface HtmlSandboxBridgeHandlers {
    iframe: HTMLIFrameElement;
    onAction: (name: string, payload: unknown) => void;
    onValue: (value: unknown) => void;
    onResize: (height: number) => void;
    onError: (error: { message: string; stack: string }) => void;
    onOpenUrl: (url: string) => void;
}

/** Хостовая сторона моста; ``attach`` до установки ``srcdoc``. */
export class HtmlSandboxBridge {
    iframe: HTMLIFrameElement;
    handlers: HtmlSandboxBridgeHandlers;
    private _state: unknown;
    private _tokens: Record<string, unknown>;
    private _listener: (event: MessageEvent) => void;

    constructor(options: HtmlSandboxBridgeHandlers) {
        if (!options || !(options.iframe instanceof HTMLIFrameElement)) throw new Error('flow-ui: sandbox bridge requires iframe');
        for (const name of ['onAction', 'onValue', 'onResize', 'onError', 'onOpenUrl'] as const) {
            if (typeof options[name] !== 'function') throw new Error(`flow-ui: sandbox bridge requires ${name}`);
        }
        this.iframe = options.iframe;
        this.handlers = options;
        this._state = {};
        this._tokens = {};
        this._listener = (event: MessageEvent) => this._onMessage(event);
        window.addEventListener('message', this._listener);
    }

    private _onMessage(event: MessageEvent) {
        if (event.source !== this.iframe.contentWindow) return;
        const message = event.data;
        const messageType = isPlainRecord(message) ? message.type : undefined;
        if (!isPlainRecord(message) || !FRAME_MESSAGE_TYPES.has(String(message.type))) {
            this.handlers.onError({ message: `flow-ui: unknown sandbox message ${JSON.stringify(messageType)}`, stack: '' });
            return;
        }
        if (message.type === 'action') {
            if (typeof message.name !== 'string' || message.name === '') {
                this.handlers.onError({ message: 'flow-ui: sandbox action requires name', stack: '' });
                return;
            }
            this.handlers.onAction(message.name, message.payload && typeof message.payload === 'object' ? message.payload : {});
        } else if (message.type === 'value') {
            this.handlers.onValue(message.value === undefined ? null : message.value);
        } else if (message.type === 'resize') {
            if (typeof message.height !== 'number' || !Number.isFinite(message.height)) {
                this.handlers.onError({ message: 'flow-ui: sandbox resize requires numeric height', stack: '' });
                return;
            }
            this.handlers.onResize(Math.min(FLOW_UI_HTML_MAX_HEIGHT, Math.max(FLOW_UI_HTML_MIN_HEIGHT, Math.ceil(message.height))));
        } else if (message.type === 'open_url') {
            if (typeof message.url !== 'string' || !/^https?:\/\//i.test(message.url)) {
                this.handlers.onError({ message: 'flow-ui: sandbox open_url requires http(s) url', stack: '' });
                return;
            }
            this.handlers.onOpenUrl(message.url);
        } else {
            this.handlers.onError({
                message: typeof message.message === 'string' ? message.message : 'error',
                stack: typeof message.stack === 'string' ? message.stack : '',
            });
        }
    }

    private _post(message: Record<string, unknown>) {
        if (!HOST_MESSAGE_TYPES.has(String(message.type))) throw new Error(`flow-ui: host cannot send ${String(message.type)}`);
        if (this.iframe.contentWindow) this.iframe.contentWindow.postMessage(message, '*');
    }

    sendState(state: unknown) {
        this._state = state;
        this._post({ type: 'state', state });
    }

    sendTheme(tokens: Record<string, unknown>) {
        this._tokens = tokens;
        this._post({ type: 'theme', css: themeCss(tokens) });
    }

    /** Повторяет state и тему после загрузки нового ``srcdoc``. */
    resend() {
        this._post({ type: 'theme', css: themeCss(this._tokens) });
        this._post({ type: 'state', state: this._state });
    }

    dispose() {
        window.removeEventListener('message', this._listener);
    }
}
