/**
 * platform-mermaid-host — Mermaid SVG в Lit (lazy script, antiscript, platform theme).
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';

const MERMAID_URL = '/static/core/assets/js/mermaid/mermaid.min.js';

let _mermaidPromise = null;
let _mermaidInitialized = false;
let _renderSeq = 0;

function loadMermaid() {
    if (typeof window !== 'undefined' && window.mermaid) {
        return Promise.resolve(window.mermaid);
    }
    if (_mermaidPromise) {
        return _mermaidPromise;
    }
    _mermaidPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = MERMAID_URL;
        script.async = true;
        script.dataset.platformMermaid = '1';
        script.onload = () => {
            if (!window.mermaid) {
                reject(new Error('mermaid global missing after load'));
                return;
            }
            resolve(window.mermaid);
        };
        script.onerror = () => reject(new Error(`mermaid load failed: ${MERMAID_URL}`));
        document.head.appendChild(script);
    });
    return _mermaidPromise;
}

function ensureMermaidInit(mermaid) {
    if (_mermaidInitialized) {
        return;
    }
    const styles = getComputedStyle(document.documentElement);
    const pick = (name, fallback) => {
        const value = styles.getPropertyValue(name).trim();
        return value.length > 0 ? value : fallback;
    };
    const primary = pick('--text-primary', '#e2e8f0');
    const secondary = pick('--text-secondary', '#94a3b8');
    const surface = pick('--glass-solid-medium', '#1e293b');
    const accent = pick('--accent', '#3b82f6');
    const border = pick('--glass-border-subtle', '#334155');
    mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'antiscript',
        theme: 'base',
        themeVariables: {
            primaryColor: surface,
            primaryTextColor: primary,
            primaryBorderColor: border,
            lineColor: secondary,
            secondaryColor: accent,
            tertiaryColor: surface,
            background: 'transparent',
            mainBkg: surface,
            nodeBorder: border,
            clusterBkg: surface,
            titleColor: primary,
            edgeLabelBackground: surface,
        },
    });
    _mermaidInitialized = true;
}

export class PlatformMermaidHost extends PlatformElement {
    static properties = {
        source: { type: String },
        suspended: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                width: 100%;
                overflow: auto;
            }
            :host([compact]) {
                flex: none;
                max-height: 320px;
            }
            .diagram {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-3);
                min-height: 120px;
            }
            .diagram svg {
                max-width: 100%;
                height: auto;
            }
            .state {
                display: flex;
                flex: 1;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                padding: var(--space-4);
            }
            .state-error {
                color: var(--danger);
                white-space: pre-wrap;
            }
        `,
    ];

    constructor() {
        super();
        this.source = '';
        this.suspended = false;
        this.compact = false;
        this._svgHtml = '';
        this._loadError = '';
        this._bootToken = 0;
    }

    updated(changed) {
        if (changed.has('source') || changed.has('suspended')) {
            void this._renderDiagram();
        }
    }

    connectedCallback() {
        super.connectedCallback();
        void this._renderDiagram();
    }

    async _renderDiagram() {
        const token = ++this._bootToken;
        if (this.suspended) {
            return;
        }
        const source = typeof this.source === 'string' ? this.source.trim() : '';
        if (source.length === 0) {
            this._svgHtml = '';
            this._loadError = 'mermaid source required';
            this.requestUpdate();
            return;
        }
        this._loadError = '';
        try {
            const mermaid = await loadMermaid();
            if (token !== this._bootToken) {
                return;
            }
            ensureMermaidInit(mermaid);
            const renderId = `platform-mermaid-${++_renderSeq}`;
            const { svg } = await mermaid.render(renderId, source);
            if (token !== this._bootToken) {
                return;
            }
            this._svgHtml = svg;
            this.requestUpdate();
        } catch (error) {
            this._svgHtml = '';
            this._loadError = error instanceof Error ? error.message : String(error);
            this.requestUpdate();
            this.emit('editor-error', { code: 'mermaid_render_failed', message: this._loadError });
        }
    }

    exportSvgMarkup() {
        if (typeof this._svgHtml !== 'string' || this._svgHtml.length === 0) {
            throw new Error('mermaid svg not ready');
        }
        return this._svgHtml;
    }

    render() {
        if (this._loadError) {
            return html`<div class="state state-error">${this._loadError}</div>`;
        }
        if (!this._svgHtml) {
            return html`<div class="state">Rendering…</div>`;
        }
        return html`<div class="diagram" .innerHTML=${this._svgHtml}></div>`;
    }
}

customElements.define('platform-mermaid-host', PlatformMermaidHost);
