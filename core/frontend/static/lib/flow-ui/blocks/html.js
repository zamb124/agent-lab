/**
 * Блок ``html``: ``<flow-ui-html-block>`` держит iframe sandbox и мост. Новый ``source`` —
 * новый ``srcdoc``; новое состояние — сообщение ``state`` без перезагрузки iframe.
 * Мост вешается при каждом подключении: модалка-портал в ``document.body`` перезагружает iframe.
 */

import { css, html, LitElement } from '../../lit-shim.js';
import {
    FLOW_UI_HTML_MIN_HEIGHT,
    FLOW_UI_HTML_SANDBOX,
    HtmlSandboxBridge,
    buildHtmlSrcdoc,
    htmlBlockState,
    readThemeTokens,
} from '../runtime/html-sandbox.js';

export class FlowUIHtmlBlock extends LitElement {
    static properties = {
        block: { attribute: false },
        state: { attribute: false },
        readonly: { type: Boolean },
        onAction: { attribute: false },
        onValue: { attribute: false },
        onOpenUrl: { attribute: false },
        onBridgeEvent: { attribute: false },
        _height: { state: true },
        _error: { state: true },
    };

    static styles = css`
        :host { display: block; min-height: var(--flow-ui-html-min-height, 0); }
        iframe {
            display: block; width: 100%; min-height: var(--flow-ui-html-min-height, 0);
            border: 0; border-radius: var(--flow-ui-radius-md, 12px); background: transparent;
        }
        .error { margin-top: 6px; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--error, #ff718d) 14%, transparent); color: var(--error, #ff718d); font-size: 12px; white-space: pre-wrap; font-family: var(--font-mono); }
    `;

    constructor() {
        super();
        this.block = null;
        this.state = {};
        this.readonly = false;
        this.onAction = null;
        this.onValue = null;
        this.onOpenUrl = null;
        this.onBridgeEvent = null;
        this._height = FLOW_UI_HTML_MIN_HEIGHT;
        this._error = '';
        this._bridge = null;
        this._srcdoc = '';
        this._sourceKey = '';
        this._reloadSeq = 0;
        this._onFrameLoad = () => this.pushHost();
    }

    /** Тема и state в уже загруженный iframe; безопасна при битых ``data-bind``. */
    pushHost() {
        if (this._bridge === null || this.block === null) return;
        this._bridge.sendTheme(readThemeTokens(this));
        try {
            this._bridge.sendState(htmlBlockState(this.block, this.state));
        } catch (error) {
            this._error = error.message;
        }
    }

    /** Принудительный новый ``srcdoc`` даже при том же ``source`` (зависший скрипт автора). */
    reload() {
        this._reloadSeq += 1;
        this._sourceKey = '';
        this._refreshSrcdoc();
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.hasUpdated) this._bindFrame();
    }

    disconnectedCallback() {
        this._unbindFrame();
        super.disconnectedCallback();
    }

    firstUpdated() {
        this._bindFrame();
        this._refreshSrcdoc();
    }

    updated(changed) {
        if (!this._bridge) return;
        if (changed.has('block')) this._refreshSrcdoc();
        if (changed.has('state') || changed.has('block')) this.pushHost();
    }

    _iframe() {
        return this.renderRoot.querySelector('iframe');
    }

    _bindFrame() {
        const iframe = this._iframe();
        if (!(iframe instanceof HTMLIFrameElement)) return;
        this._unbindFrame();
        this._bridge = new HtmlSandboxBridge({
            iframe,
            onAction: (name, payload) => {
                this._emit('action', { name, payload });
                if (this.readonly) return;
                if (typeof this.onAction !== 'function') throw new Error('flow-ui: html block has no action handler');
                this.onAction(name, payload);
            },
            onValue: (value) => {
                this._emit('value', { value });
                if (this.readonly || this.block.field === null) return;
                if (typeof this.onValue !== 'function') throw new Error('flow-ui: html block has no value handler');
                this.onValue(value);
            },
            onResize: (height) => {
                if (this.block.height === 'auto') this._height = height;
            },
            onError: (error) => {
                this._error = error.stack !== '' ? `${error.message}\n${error.stack}` : error.message;
                this._emit('error', error);
            },
            onOpenUrl: (url) => {
                this._emit('open_url', { url });
                if (this.readonly) return;
                if (typeof this.onOpenUrl !== 'function') throw new Error('flow-ui: html block has no open_url handler');
                this.onOpenUrl(url);
            },
        });
        iframe.addEventListener('load', this._onFrameLoad);
    }

    _unbindFrame() {
        const iframe = this._iframe();
        if (iframe) iframe.removeEventListener('load', this._onFrameLoad);
        if (this._bridge) this._bridge.dispose();
        this._bridge = null;
    }

    _emit(kind, detail) {
        if (typeof this.onBridgeEvent === 'function') this.onBridgeEvent({ kind, ...detail });
    }

    _refreshSrcdoc() {
        const key = this.block.source;
        if (key === this._sourceKey) return;
        this._sourceKey = key;
        this._error = '';
        const stamp = this._reloadSeq > 0 ? `<!--r${this._reloadSeq}-->` : '';
        this._srcdoc = `${buildHtmlSrcdoc({ source: this.block.source, tokens: readThemeTokens(this) })}${stamp}`;
        this.requestUpdate();
    }

    render() {
        const height = this.block.height === 'auto' ? this._height : this.block.height;
        return html`<iframe
            sandbox=${FLOW_UI_HTML_SANDBOX}
            referrerpolicy="no-referrer"
            allow=""
            title="html"
            style=${`height:${height}px`}
            .srcdoc=${this._srcdoc}
        ></iframe>
        ${this._error !== '' ? html`<div class="error" role="alert">${this._error}</div>` : ''}`;
    }
}

if (!customElements.get('flow-ui-html-block')) customElements.define('flow-ui-html-block', FlowUIHtmlBlock);

export const HTML_BLOCKS = Object.freeze({
    html(block, ctx) {
        return html`<flow-ui-html-block
            .block=${block}
            .state=${ctx.state}
            .readonly=${ctx.readonly}
            .onAction=${(name, payload) => ctx.onAction(block, { name, payload })}
            .onValue=${(value) => ctx.onFieldChange(block.field, value)}
            .onOpenUrl=${(url) => ctx.onOpenUrl(url)}
            .onBridgeEvent=${ctx.onHtmlBridgeEvent}
        ></flow-ui-html-block>`;
    },
});
