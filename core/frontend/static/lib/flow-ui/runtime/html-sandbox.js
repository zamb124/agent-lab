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

const BINDING_ATTRIBUTES = new Set(['data-bind', 'data-show']);
// Разметка, которую HTML-парсер не читает как теги: комментарии, CDATA/декларации/PI
// и тела raw-text элементов (сами открывающие теги остаются — их атрибуты считаются).
const SKIPPED_MARKUP_RE = /<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<![^>]*>|<\?[^>]*>|(<(script|style|textarea|title)\b(?:"[^"]*"|'[^']*'|[^'">])*>)[\s\S]*?(?:<\/\2\s*>|$)/gi;
const START_TAG_RE = /<[a-zA-Z][^\s/>]*((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
const ATTRIBUTE_RE = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
const NAMED_CHAR_REFS = Object.freeze({ amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" });

function decodeCharRefs(value) {
    return value.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (reference, body) => {
        if (body[0] === '#') {
            const hex = body[1] === 'x' || body[1] === 'X';
            return String.fromCodePoint(Number.parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10));
        }
        const named = NAMED_CHAR_REFS[body.toLowerCase()];
        return named === undefined ? reference : named;
    });
}

/**
 * Пути ``data-bind`` / ``data-show`` из ``source`` в порядке появления; невалидный путь — ошибка автора.
 * Правила те же, что у ``core.flow_ui.html_bindings``: атрибуты читаются только в открывающих тегах,
 * имена без учёта регистра, ссылки на символы в значениях раскрываются, атрибут без значения — ошибка.
 */
export function htmlBoundPaths(source) {
    const paths = [];
    const invalid = [];
    const markup = String(source).replace(SKIPPED_MARKUP_RE, (skipped, rawTextStart) => rawTextStart ?? '');
    for (const tag of markup.matchAll(START_TAG_RE)) {
        for (const attribute of tag[1].matchAll(ATTRIBUTE_RE)) {
            const name = attribute[1].toLowerCase();
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
export function htmlBlockState(block, state) {
    const projection = {};
    const paths = [...(Array.isArray(block.fields) ? block.fields : []), ...htmlBoundPaths(block.source)];
    for (const path of paths) {
        const value = valueAtPath(state, path);
        if (value === undefined) continue;
        const segments = path.split('.');
        let target = projection;
        for (const segment of segments.slice(0, -1)) {
            if (target[segment] === null || typeof target[segment] !== 'object') target[segment] = {};
            target = target[segment];
        }
        target[segments[segments.length - 1]] = value;
    }
    return projection;
}

export function readThemeTokens(element) {
    const tokens = {};
    const sources = [element];
    if (typeof document !== 'undefined' && document.documentElement && document.documentElement !== element) {
        sources.push(document.documentElement);
    }
    for (const name of FLOW_UI_HTML_THEME_TOKENS) {
        for (const source of sources) {
            if (!source || typeof getComputedStyle !== 'function') continue;
            const value = getComputedStyle(source).getPropertyValue(name).trim();
            if (value !== '') {
                tokens[name] = value;
                break;
            }
        }
    }
    return tokens;
}

function themeCss(tokens) {
    const declarations = Object.entries(tokens)
        .filter(([name]) => /^--[a-z0-9-]+$/i.test(name))
        .map(([name, value]) => `${name}:${String(value).replace(/[<>]/g, '')}`);
    return `:root{${declarations.join(';')}}`;
}

const BOOTSTRAP = `
(() => {
  const listeners = new Set();
  let state = {};
  const post = (message) => parent.postMessage(message, '*');
  const walk = (value, path) => path.split('.').reduce((acc, key) => (acc && typeof acc === 'object' ? acc[key] : undefined), value);
  const present = (value) => value !== undefined && value !== null && value !== '' && value !== false && !(Array.isArray(value) && value.length === 0);
  const render = () => {
    for (const el of document.querySelectorAll('[data-bind]')) {
      const value = walk(state, el.getAttribute('data-bind'));
      el.textContent = value === undefined || value === null ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value));
    }
    for (const el of document.querySelectorAll('[data-show]')) {
      el.hidden = !present(walk(state, el.getAttribute('data-show')));
    }
  };
  const resize = () => post({ type: 'resize', height: Math.ceil(document.documentElement.getBoundingClientRect().height) });
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
    if (event.data.type === 'state') { state = event.data.state && typeof event.data.state === 'object' ? event.data.state : {}; render(); for (const cb of listeners) cb(state); return; }
    if (event.data.type === 'theme') { const style = document.getElementById('flow-ui-theme'); if (style) style.textContent = event.data.css; }
  });
  window.addEventListener('error', (event) => post({ type: 'error', message: String(event.message || 'error'), stack: event.error && event.error.stack ? String(event.error.stack) : '' }));
  window.addEventListener('unhandledrejection', (event) => post({ type: 'error', message: String(event.reason && event.reason.message || event.reason || 'rejection'), stack: event.reason && event.reason.stack ? String(event.reason.stack) : '' }));
  document.addEventListener('DOMContentLoaded', () => { render(); resize(); new ResizeObserver(resize).observe(document.documentElement); });
})();
`;

/** ``srcdoc`` блока: CSP, токены темы, bootstrap ``flowUi``, затем ``source`` автора. */
export function buildHtmlSrcdoc({ source, tokens = {} }) {
    if (typeof source !== 'string') throw new Error('flow-ui: html block source must be a string');
    return `<!doctype html><html><head><meta charset="utf-8">`
        + `<meta http-equiv="Content-Security-Policy" content="${FLOW_UI_HTML_CSP}">`
        + `<style id="flow-ui-theme">${themeCss(tokens)}</style>`
        + `<style>html,body{margin:0;background:transparent;color:var(--flow-ui-text,inherit);font:14px/1.45 system-ui,sans-serif}</style>`
        + `<script>${BOOTSTRAP}</script></head><body>${source}</body></html>`;
}

/** Хостовая сторона моста; ``attach`` до установки ``srcdoc``. */
export class HtmlSandboxBridge {
    /**
     * @param {{
     *   iframe: HTMLIFrameElement,
     *   onAction: (name: string, payload: unknown) => void,
     *   onValue: (value: unknown) => void,
     *   onResize: (height: number) => void,
     *   onError: (error: { message: string, stack: string }) => void,
     *   onOpenUrl: (url: string) => void,
     * }} options
     */
    constructor(options) {
        if (!options || !(options.iframe instanceof HTMLIFrameElement)) throw new Error('flow-ui: sandbox bridge requires iframe');
        for (const name of ['onAction', 'onValue', 'onResize', 'onError', 'onOpenUrl']) {
            if (typeof options[name] !== 'function') throw new Error(`flow-ui: sandbox bridge requires ${name}`);
        }
        this.iframe = options.iframe;
        this.handlers = options;
        this._state = {};
        this._tokens = {};
        this._listener = (event) => this._onMessage(event);
        window.addEventListener('message', this._listener);
    }

    _onMessage(event) {
        if (event.source !== this.iframe.contentWindow) return;
        const message = event.data;
        if (!message || typeof message !== 'object' || !FRAME_MESSAGE_TYPES.has(message.type)) {
            this.handlers.onError({ message: `flow-ui: unknown sandbox message ${JSON.stringify(message?.type)}`, stack: '' });
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

    _post(message) {
        if (!HOST_MESSAGE_TYPES.has(message.type)) throw new Error(`flow-ui: host cannot send ${message.type}`);
        if (this.iframe.contentWindow) this.iframe.contentWindow.postMessage(message, '*');
    }

    sendState(state) {
        this._state = state;
        this._post({ type: 'state', state });
    }

    sendTheme(tokens) {
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
