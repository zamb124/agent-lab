/**
 * platform-viz-host — switch ECharts / Mermaid по document/openConfig.
 *
 * Входы:
 * - `.document` — VizDocument JSON ({ kind, engine, title, spec })
 * - или `.openConfig` с handler=viz и payload.viz
 * - `compact` — для chat inline
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-echarts-host.js';
import './platform-mermaid-host.js';

function vizPayloadFromOpenConfig(openConfig) {
    if (!openConfig || typeof openConfig !== 'object') {
        return null;
    }
    if (openConfig.handler !== 'viz') {
        return null;
    }
    const payload = openConfig.viz;
    if (!payload || typeof payload !== 'object') {
        return null;
    }
    return payload;
}

function resolveDocument(openConfig, documentProp) {
    if (documentProp && typeof documentProp === 'object') {
        return documentProp;
    }
    const payload = vizPayloadFromOpenConfig(openConfig);
    if (payload?.document && typeof payload.document === 'object') {
        return payload.document;
    }
    return null;
}

export class PlatformVizHost extends PlatformElement {
    static properties = {
        openConfig: { type: Object, attribute: false },
        document: { type: Object, attribute: false },
        fileId: { type: String, attribute: 'file-id' },
        suspended: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                width: 100%;
                background: var(--glass-solid-subtle, transparent);
            }
            :host([compact]) {
                flex: none;
                min-height: 240px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
            }
            .title {
                flex: 1;
                min-width: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            button {
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                border-radius: var(--radius-sm);
                padding: 4px 10px;
                font: inherit;
                font-size: var(--text-xs);
                cursor: pointer;
            }
            button:hover {
                color: var(--text-primary);
            }
            .body {
                display: flex;
                flex: 1;
                min-height: 0;
                min-width: 0;
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
            }
        `,
    ];

    constructor() {
        super();
        this.openConfig = null;
        this.document = null;
        this.fileId = '';
        this.suspended = false;
        this.compact = false;
        this.showToolbar = true;
    }

    _onEngineError(event) {
        this.emit('editor-error', event.detail || {});
    }

    _openFullscreen() {
        const fileId =
            (typeof this.fileId === 'string' && this.fileId.length > 0 && this.fileId) ||
            (typeof this.openConfig?.file_id === 'string' && this.openConfig.file_id) ||
            (typeof this.document?.file_id === 'string' && this.document.file_id) ||
            '';
        if (fileId.length === 0) {
            return;
        }
        const title =
            (typeof this.document?.title === 'string' && this.document.title) ||
            (typeof this.openConfig?.title === 'string' && this.openConfig.title) ||
            'visualization.viz';
        this.openFile(
            {
                file_id: fileId,
                original_name: title.endsWith('.viz') ? title : `${title}.viz`,
                content_type: 'application/vnd.platform.viz+json',
            },
            { source: 'platform_viz_host' },
        );
    }

    _export() {
        const doc = resolveDocument(this.openConfig, this.document);
        if (!doc) {
            return;
        }
        const engine = doc.engine;
        try {
            if (engine === 'echarts') {
                const host = this.renderRoot?.querySelector('platform-echarts-host');
                if (!host || typeof host.exportPngDataUrl !== 'function') {
                    throw new Error('echarts host not ready');
                }
                const dataUrl = host.exportPngDataUrl();
                const link = document.createElement('a');
                link.href = dataUrl;
                link.download = `${doc.title || 'chart'}.png`;
                link.click();
                return;
            }
            if (engine === 'mermaid') {
                const host = this.renderRoot?.querySelector('platform-mermaid-host');
                if (!host || typeof host.exportSvgMarkup !== 'function') {
                    throw new Error('mermaid host not ready');
                }
                const svg = host.exportSvgMarkup();
                const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `${doc.title || 'diagram'}.svg`;
                link.click();
                URL.revokeObjectURL(url);
                return;
            }
            throw new Error(`unknown engine: ${engine}`);
        } catch (error) {
            this.emit('editor-error', {
                code: 'viz_export_failed',
                message: error instanceof Error ? error.message : String(error),
            });
        }
    }

    render() {
        const doc = resolveDocument(this.openConfig, this.document);
        if (!doc) {
            return html`<div class="state state-error">viz document required</div>`;
        }
        const engine = doc.engine;
        const title = typeof doc.title === 'string' ? doc.title : 'Viz';
        const kind = typeof doc.kind === 'string' ? doc.kind : '';
        const showBar = this.showToolbar === true && this.compact !== true;
        const fileId =
            (typeof this.fileId === 'string' && this.fileId) ||
            (typeof this.openConfig?.file_id === 'string' && this.openConfig.file_id) ||
            '';
        let body = nothing;
        if (engine === 'echarts') {
            const option = doc.spec?.option;
            body = html`
                <platform-echarts-host
                    .option=${option}
                    ?suspended=${this.suspended}
                    ?compact=${this.compact}
                    @editor-error=${this._onEngineError}
                ></platform-echarts-host>
            `;
        } else if (engine === 'mermaid') {
            const source = typeof doc.spec?.source === 'string' ? doc.spec.source : '';
            body = html`
                <platform-mermaid-host
                    .source=${source}
                    ?suspended=${this.suspended}
                    ?compact=${this.compact}
                    @editor-error=${this._onEngineError}
                ></platform-mermaid-host>
            `;
        } else {
            body = html`<div class="state state-error">Unsupported engine: ${engine}</div>`;
        }
        return html`
            ${showBar
                ? html`
                      <div class="toolbar">
                          <div class="title">${title}</div>
                          <span class="meta">${kind} · ${engine}</span>
                          <button type="button" @click=${this._export}>Export</button>
                          ${fileId
                              ? html`<button type="button" @click=${this._openFullscreen}>Open</button>`
                              : nothing}
                      </div>
                  `
                : nothing}
            <div class="body">${body}</div>
        `;
    }
}

customElements.define('platform-viz-host', PlatformVizHost);
