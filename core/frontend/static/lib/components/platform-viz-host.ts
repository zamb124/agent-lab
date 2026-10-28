/**
 * platform-viz-host — switch ECharts / Mermaid по document/openConfig.
 *
 * Входы:
 * - `.document` — VizDocument JSON ({ kind, engine, title, spec })
 * - или `.openConfig` с handler=viz и payload.viz
 * - `compact` — для chat inline
 */
import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { isPlainRecord } from '../events/payload.js';
import './platform-echarts-host.js';
import './platform-mermaid-host.js';

interface VizOpenConfig extends Record<string, unknown> {
    handler?: string;
    viz?: { document?: Record<string, unknown> };
    file_id?: string;
    title?: string;
}

interface VizDocument {
    engine?: string;
    kind?: string;
    title?: string;
    file_id?: string;
    spec?: { option?: unknown; source?: string };
    [key: string]: unknown;
}

interface VizEngineHost extends Element {
    exportPngDataUrl?: () => string;
    exportSvgMarkup?: () => string;
}

function isVizDocument(value: unknown): value is VizDocument {
    return isPlainRecord(value);
}

function vizPayloadFromOpenConfig(openConfig: VizOpenConfig | null | undefined): Record<string, unknown> | null {
    if (!isPlainRecord(openConfig) || openConfig.handler !== 'viz') {
        return null;
    }
    const payload = openConfig.viz;
    if (!isPlainRecord(payload)) {
        return null;
    }
    return payload;
}

function resolveDocument(
    openConfig: VizOpenConfig | null,
    documentProp: VizDocument | null,
): VizDocument | null {
    if (isVizDocument(documentProp)) {
        return documentProp;
    }
    const payload = vizPayloadFromOpenConfig(openConfig);
    if (payload === null) {
        return null;
    }
    const document = payload.document;
    if (!isVizDocument(document)) {
        return null;
    }
    return document;
}

export class PlatformVizHost extends PlatformElement {
    static override properties: PropertyDeclarations = {
        openConfig: { type: Object, attribute: false },
        document: { type: Object, attribute: false },
        fileId: { type: String, attribute: 'file-id' },
        suspended: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
    };
    declare openConfig: VizOpenConfig | null;
    declare document: VizDocument | null;
    declare fileId: string;
    declare suspended: boolean;
    declare compact: boolean;
    declare showToolbar: boolean;

    static override styles: CSSResultGroup = [
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

    _onEngineError(event: CustomEvent<unknown>): void {
        const detail = event.detail;
        this.emit('editor-error', detail === undefined || detail === null || detail === false || detail === 0 || detail === '' ? {} : detail);
    }

    _openFullscreen(): void {
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

    _export(): void {
        const doc = resolveDocument(this.openConfig, this.document);
        if (!doc) {
            return;
        }
        const engine = doc.engine;
        try {
            if (engine === 'echarts') {
                const host = this.renderRoot?.querySelector<VizEngineHost>('platform-echarts-host');
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
                const host = this.renderRoot?.querySelector<VizEngineHost>('platform-mermaid-host');
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

    override render(): TemplateResult {
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
        let body: TemplateResult | typeof nothing = nothing;
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
