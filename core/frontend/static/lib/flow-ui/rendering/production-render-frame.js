import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { createFlowUIRenderContext } from './render-context.js';
import { diffFlowUIRenderContexts } from './render-fingerprint.js';
import { FLOW_UI_CATALOG_MANIFEST } from '../catalog/manifest.js';

const HANDSHAKE = 'flow-ui-parity-handshake';
const READY = 'flow-ui-parity-ready';
const SELECT = 'flow-ui-parity-select';
const DOCUMENT = 'flow-ui-parity-document';

/** Inputs that require a fresh iframe boot; everything else is a live message. */
const BOOT_INPUTS = Object.freeze([
    'display', 'profile', 'theme', 'locale', 'readonly', 'moduleUrl', 'staticBase',
]);

/**
 * Isolated production render frame: iframe prevents parent CSS cascade.
 * Child loads the same platform-flow-ui module and reports fingerprint via MessageChannel.
 */
export class FlowUIProductionRenderFrame extends LitElement {
    static properties = {
        document: { attribute: false },
        display: { type: String },
        profile: { type: String },
        theme: { type: String },
        locale: { type: String },
        readonly: { type: Boolean },
        selectedComponentId: { attribute: false },
        moduleUrl: { type: String, attribute: 'module-url' },
        staticBase: { type: String, attribute: 'static-base' },
        parityStatus: { state: true },
        childFingerprint: { state: true },
        contextDiff: { state: true },
    };

    static styles = css`
        :host { display: block; width: 100%; height: 100%; min-height: 0; position: relative; }
        iframe {
            display: block; width: 100%; height: 100%; min-height: 320px;
            border: 0; background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
        }
        .parity {
            position: absolute; inset: auto 10px 10px auto; z-index: 2;
            padding: 5px 9px; border-radius: 999px; font: 600 11px/1.2 ui-sans-serif, system-ui, sans-serif;
            background: rgba(12, 18, 32, .86); color: #c9d4ea; border: 1px solid rgba(151, 168, 205, .25);
        }
        .parity[data-status="Exact"] { color: #79dfb3; }
        .parity[data-status="Context differs"] { color: #f8bc60; }
        .parity[data-status="Loading"] { color: #9aa9c4; }
    `;

    constructor() {
        super();
        this.document = null;
        this.display = 'page';
        this.profile = 'editor_test';
        this.theme = 'auto';
        this.locale = 'ru';
        this.readonly = true;
        this.selectedComponentId = null;
        this.staticBase = '/static/core';
        this.moduleUrl = '';
        this.parityStatus = 'Loading';
        this.childFingerprint = '';
        this.contextDiff = [];
        this.childComponents = Object.freeze([]);
        this._channel = null;
        this._writeToken = 0;
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._teardownChannel();
    }

    updated(changed) {
        // Booting the frame re-imports the whole runtime bundle, fonts and tokens, so
        // only boot-level inputs may rewrite `srcdoc`. Document edits — the common case
        // while authoring — travel over the open MessageChannel to the live child.
        if (BOOT_INPUTS.some((name) => changed.has(name))) {
            this._writeFrame();
            return;
        }
        if (changed.has('document')) {
            this._pushDocument();
        }
        if (changed.has('selectedComponentId') && this._channel) {
            this._channel.port1.postMessage({
                type: SELECT,
                selectedComponentId: this.selectedComponentId,
            });
        }
    }

    _pushDocument() {
        if (!this.document) {
            this._writeFrame();
            return;
        }
        if (!this._channel) {
            this._writeFrame();
            return;
        }
        this.parityStatus = 'Loading';
        this._channel.port1.postMessage({ type: DOCUMENT, document: this.document });
    }

    firstUpdated() {
        this._writeFrame();
    }

    _teardownChannel() {
        if (this._channel) {
            this._channel.port1.onmessage = null;
            this._channel.port1.close();
            this._channel = null;
        }
    }

    _expectedContext() {
        if (!this.document) {
            throw new Error('flow-ui-production-render-frame: document required for parity');
        }
        const resolvedTheme = this.theme === 'auto'
            ? (document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark')
            : this.theme;
        return createFlowUIRenderContext({
            document: this.document,
            display: this.display,
            theme: resolvedTheme,
            locale: this.locale,
            catalogManifestChecksum: FLOW_UI_CATALOG_MANIFEST.checksum,
            targetSurfaceProfileId: `runtime.${this.display}.v1`,
        });
    }

    _writeFrame() {
        const iframe = this.renderRoot?.querySelector('iframe');
        if (!iframe) return;
        if (!this.document) {
            this.parityStatus = 'Loading';
            iframe.removeAttribute('srcdoc');
            return;
        }
        this.parityStatus = 'Loading';
        this._teardownChannel();
        this._channel = new MessageChannel();
        const token = (this._writeToken += 1);
        this._channel.port1.onmessage = (event) => {
            if (token !== this._writeToken) return;
            this._onChildMessage(event.data);
        };

        const resolvedTheme = this.theme === 'auto'
            ? (document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark')
            : this.theme;
        if (resolvedTheme !== 'light' && resolvedTheme !== 'dark') {
            throw new Error(`flow-ui-production-render-frame: unsupported theme ${JSON.stringify(this.theme)}`);
        }

        const staticBase = String(this.staticBase || '/static/core').replace(/\/+$/, '');
        const assetsBase = `${staticBase}/assets`;
        const libBase = `${staticBase}/lib`;

        const boot = {
            document: this.document,
            display: this.display,
            profile: this.profile,
            theme: resolvedTheme,
            locale: this.locale,
            readonly: this.readonly === true,
            selectedComponentId: this.selectedComponentId,
            moduleUrl: this.moduleUrl || `${libBase}/flow-ui/components/platform-flow-ui.js`,
            inspectionModuleUrl: `${libBase}/flow-ui/rendering/renderer-inspection-bridge.js`,
            handshake: HANDSHAKE,
            ready: READY,
            catalogChecksum: FLOW_UI_CATALOG_MANIFEST.checksum,
        };

        const onChildReady = (event) => {
            if (token !== this._writeToken || !this._channel) return;
            if (event.source !== iframe.contentWindow) return;
            if (!event.data || event.data.type !== 'flow-ui-parity-child-ready') return;
            window.removeEventListener('message', onChildReady);
            iframe.contentWindow.postMessage(
                { type: HANDSHAKE },
                '*',
                [this._channel.port2],
            );
        };
        window.addEventListener('message', onChildReady);

        if (typeof this.locale !== 'string' || this.locale.trim() === '') {
            throw new Error('flow-ui-production-render-frame: locale required');
        }
        const safeLocale = this.locale.replace(/"/g, '');
        const fontsHref = `${window.location.origin}${assetsBase}/fonts/platform-fonts.css`;
        const tokensHref = `${window.location.origin}${assetsBase}/css/tokens.css`;
        iframe.srcdoc = `<!doctype html>
<html lang="${safeLocale}" data-theme="${resolvedTheme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="${fontsHref}">
<link rel="stylesheet" href="${tokensHref}">
<script type="importmap">
{
  "imports": {
    "lit": "${assetsBase}/js/lit/lit.min.js",
    "lit/": "${assetsBase}/js/lit/",
    "lit/decorators.js": "${assetsBase}/js/lit/decorators.min.js",
    "lit/directives/class-map.js": "${assetsBase}/js/lit/directives/class-map.min.js",
    "lit/directives/repeat.js": "${assetsBase}/js/lit/directives/repeat.min.js",
    "lit/directives/unsafe-html.js": "${assetsBase}/js/lit/directives/unsafe-html.min.js",
    "lit/directives/when.js": "${assetsBase}/js/lit/directives/when.min.js",
    "lit/directives/guard.js": "${assetsBase}/js/lit/directives/guard.min.js",
    "@platform/lib/": "${libBase}/",
    "@capacitor/app": "${assetsBase}/js/vendor/@capacitor/app/index.js",
    "@capacitor/core": "${assetsBase}/js/vendor/@capacitor/core/index.js",
    "@capacitor/splash-screen": "${assetsBase}/js/vendor/@capacitor/splash-screen/index.js",
    "@capacitor/push-notifications": "${assetsBase}/js/vendor/@capacitor/push-notifications/index.js"
  }
}
</script>
<style>html,body{margin:0;width:100%;height:100%;background:var(--flow-ui-page-background,var(--bg-primary,#16213e))}#host,platform-flow-ui,flow-ui-surface{display:block;width:100%;height:100%;min-height:100%}#host{display:block}</style>
</head>
<body>
<div id="host"></div>
<script type="module">
const boot = ${JSON.stringify(boot)};
const CHILD_READY = 'flow-ui-parity-child-ready';
const RENDER_TIMEOUT_MS = 15000;
let host = null;
let collectFlowUIInspection = null;

/** Mount once. The document is assigned before append so the first session starts local. */
async function ensureHost(uiDocument) {
  if (host) return host;
  await import(boot.moduleUrl);
  ({ collectFlowUIInspection } = await import(boot.inspectionModuleUrl));
  await document.fonts.load('14px Inter');
  const mount = document.getElementById('host');
  mount.replaceChildren();
  const el = document.createElement('platform-flow-ui');
  el.initialDocument = uiDocument;
  el.display = boot.display;
  el.profile = boot.profile;
  el.theme = boot.theme;
  el.locale = boot.locale;
  el.readonly = boot.readonly;
  el.selectedComponentId = boot.selectedComponentId;
  mount.appendChild(el);
  host = el;
  return host;
}

/** Wait for the runtime to commit the given revision (hydration is async). */
function renderCommitted(el, revision) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      el.removeEventListener('flow-ui-render-committed', onCommit);
      reject(new Error('flow-ui-frame: render fingerprint timeout'));
    }, RENDER_TIMEOUT_MS);
    function onCommit(event) {
      if (typeof revision === 'number' && event.detail?.revision !== revision) return;
      clearTimeout(timer);
      el.removeEventListener('flow-ui-render-committed', onCommit);
      resolve();
    }
    el.addEventListener('flow-ui-render-committed', onCommit);
  });
}

async function renderDocument(uiDocument) {
  const mounted = host !== null;
  const el = await ensureHost(uiDocument);
  const committed = renderCommitted(el, uiDocument?.revision);
  if (mounted) el.initialDocument = uiDocument;
  await el.updateComplete;
  if (typeof el.renderFingerprint !== 'string'
    || !el.renderFingerprint.startsWith('fnv1a:')
    || el.controller?.document?.revision !== uiDocument?.revision) {
    await committed;
  }
  await document.fonts.load('14px Inter');
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  return el;
}

function measure(el) {
  if (typeof el.getRenderContext !== 'function') {
    throw new Error('flow-ui-frame: getRenderContext missing');
  }
  const context = el.getRenderContext();
  if (!context || typeof context !== 'object') {
    throw new Error('flow-ui-frame: render context missing');
  }
  const fingerprint = typeof el.renderFingerprint === 'string' ? el.renderFingerprint : '';
  if (!fingerprint.startsWith('fnv1a:')) {
    throw new Error('flow-ui-frame: render fingerprint missing');
  }
  const surfaceRoot = el.renderRoot || el.shadowRoot;
  if (!surfaceRoot) throw new Error('flow-ui-frame: host shadow missing');
  const surface = surfaceRoot.querySelector('flow-ui-surface');
  if (!surface) throw new Error('flow-ui-frame: flow-ui-surface missing');
  const componentRoot = surface.renderRoot || surface.shadowRoot;
  if (!componentRoot) throw new Error('flow-ui-frame: surface shadow missing');
  return { fingerprint, context, components: collectFlowUIInspection(componentRoot) };
}

window.addEventListener('message', async (event) => {
  if (!event.data || event.data.type !== boot.handshake) return;
  const port = event.ports && event.ports[0];
  if (!port) throw new Error('flow-ui-frame: MessageChannel port missing');
  let pending = Promise.resolve();
  const publish = (uiDocument) => {
    // Serialize renders: a burst of edits must not interleave measurements.
    pending = pending.then(async () => {
      try {
        const el = await renderDocument(uiDocument);
        port.postMessage({
          type: boot.ready,
          catalogChecksum: boot.catalogChecksum,
          ...measure(el),
        });
      } catch (error) {
        port.postMessage({
          type: boot.ready,
          error: error instanceof Error ? error.message : String(error),
          fingerprint: '',
          context: null,
          catalogChecksum: boot.catalogChecksum,
          components: [],
        });
      }
    });
    return pending;
  };
  port.onmessage = (messageEvent) => {
    const payload = messageEvent.data;
    if (!payload) return;
    if (payload.type === '${SELECT}') {
      if (host) host.selectedComponentId = payload.selectedComponentId;
      return;
    }
    if (payload.type === '${DOCUMENT}') {
      void publish(payload.document);
    }
  };
  await publish(boot.document);
}, { once: true });
window.parent.postMessage({ type: CHILD_READY }, '*');
</script>
</body>
</html>`;
    }

    _onChildMessage(data) {
        if (!data || data.type !== READY) return;
        this.childComponents = Array.isArray(data.components)
            ? Object.freeze(data.components)
            : Object.freeze([]);
        if (typeof data.error === 'string' && data.error) {
            this.parityStatus = 'Context differs';
            this.childFingerprint = '';
            this.contextDiff = [{ field: 'frame_error', expected: null, actual: data.error }];
            this.dispatchEvent(new CustomEvent('parity-ready', {
                detail: Object.freeze({
                    status: this.parityStatus,
                    fingerprint: '',
                    diff: this.contextDiff,
                    components: this.childComponents,
                    assetsReady: false,
                    error: data.error,
                }),
                bubbles: true,
                composed: true,
            }));
            return;
        }
        if (typeof data.fingerprint !== 'string' || !data.fingerprint.startsWith('fnv1a:')) {
            this.parityStatus = 'Context differs';
            this.childFingerprint = '';
            this.contextDiff = [{
                field: 'fingerprint',
                expected: 'fnv1a:*',
                actual: data.fingerprint ?? null,
            }];
            this.dispatchEvent(new CustomEvent('parity-ready', {
                detail: Object.freeze({
                    status: this.parityStatus,
                    fingerprint: '',
                    diff: this.contextDiff,
                    components: this.childComponents,
                    assetsReady: false,
                    error: 'child fingerprint missing',
                }),
                bubbles: true,
                composed: true,
            }));
            return;
        }
        if (!data.context || typeof data.context !== 'object') {
            this.parityStatus = 'Context differs';
            this.childFingerprint = data.fingerprint;
            this.contextDiff = [{ field: 'context', expected: 'object', actual: null }];
            this.dispatchEvent(new CustomEvent('parity-ready', {
                detail: Object.freeze({
                    status: this.parityStatus,
                    fingerprint: this.childFingerprint,
                    diff: this.contextDiff,
                    components: this.childComponents,
                    assetsReady: false,
                    error: 'child context missing',
                }),
                bubbles: true,
                composed: true,
            }));
            return;
        }
        const expected = this._expectedContext();
        this.childFingerprint = data.fingerprint;
        this.contextDiff = diffFlowUIRenderContexts(expected, data.context);
        this.parityStatus = this.contextDiff.length === 0 ? 'Exact' : 'Context differs';
        this.dispatchEvent(new CustomEvent('parity-ready', {
            detail: Object.freeze({
                status: this.parityStatus,
                fingerprint: this.childFingerprint,
                diff: this.contextDiff,
                components: this.childComponents,
                expectedContext: expected,
                actualContext: data.context,
                assetsReady: true,
            }),
            bubbles: true,
            composed: true,
        }));
    }

    inspect() {
        return Object.freeze({
            status: this.parityStatus,
            fingerprint: this.childFingerprint,
            diff: this.contextDiff,
            components: this.childComponents,
        });
    }

    render() {
        return html`
            <iframe title="Flow UI production frame" sandbox="allow-scripts allow-same-origin"></iframe>
            <div class="parity" data-status=${this.parityStatus}>
                ${this.parityStatus}${this.childFingerprint ? html` · ${this.childFingerprint}` : nothing}
            </div>
        `;
    }
}

if (!customElements.get('flow-ui-production-render-frame')) {
    customElements.define('flow-ui-production-render-frame', FlowUIProductionRenderFrame);
}
