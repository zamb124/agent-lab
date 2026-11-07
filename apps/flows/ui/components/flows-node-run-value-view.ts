/**
 * Типизированный просмотр значения результата ноды.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-code-editor.js';
import '@platform/lib/components/platform-json-editor.js';
import '@platform/lib/components/platform-json-tree.js';
import '@platform/lib/components/platform-markdown-editor.js';
import '@platform/lib/components/platform-segmented-control.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import { collectJsonImages, resolveBase64Image } from '@platform/lib/utils/base64-image.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import {
    classifyNodeRunValue,
    serializeNodeRunValue,
} from '../_helpers/flows-node-run-result.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';

type StructureView = 'tree' | 'json' | 'images';
type StringView = 'text' | 'image';

export class FlowsNodeRunValueView extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        value: { attribute: false },
        rootPath: { type: String, attribute: 'root-path' },
        _structureView: { state: true },
        _treePath: { state: true },
        _stringView: { state: true },
    };

    declare value: unknown;
    declare rootPath: string;
    declare _structureView: StructureView;
    declare _treePath: string;
    declare _stringView: StringView;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-width: 0;
                min-height: 0;
                flex: 1;
            }
            .empty {
                margin: 0;
                padding: var(--space-6);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }
            .scalar {
                margin: 0;
                padding: var(--space-6);
                font-family: var(--font-mono);
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                word-break: break-word;
            }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .viewer {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: auto;
            }
            .status-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
            }
            .status-card {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }
            .status-card[data-ok='true'] {
                border-color: var(--success-border);
                background: var(--success-bg);
            }
            .status-card[data-ok='false'] {
                border-color: var(--error-border);
                background: var(--error-bg);
            }
            .status-key {
                font-weight: var(--font-semibold);
                min-width: 0;
                word-break: break-word;
            }
            .status-state {
                margin-left: auto;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }
            .status-latency {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .image-gallery {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-3);
            }
            .image-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                max-width: 640px;
            }
            .image-card-meta {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                word-break: break-word;
            }
            .image-card img {
                display: block;
                max-width: 100%;
                max-height: 360px;
                object-fit: contain;
                border-radius: var(--radius-sm);
                background: var(--bg-primary);
            }
            platform-markdown-editor,
            platform-code-editor,
            platform-json-editor,
            platform-json-tree {
                flex: 1 1 auto;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.rootPath = '';
        this._structureView = 'tree';
        this._treePath = '';
        this._stringView = 'image';
    }

    /**
     * @param {CustomEvent<{ path?: unknown, value?: unknown }>} event
     */
    _onTreeSelect(event: CustomEvent): void {
        const detail = event.detail;
        if (detail === null || typeof detail !== 'object' || typeof detail.path !== 'string') {
            throw new Error('flows-node-run-value-view: tree select requires detail.path');
        }
        this._treePath = detail.path;
        this.emit('select', { path: detail.path, value: detail.value });
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} event
     */
    _onStructureChange(event: CustomEvent): void {
        const next = event.detail && event.detail.value;
        if (next !== 'tree' && next !== 'json' && next !== 'images') {
            throw new Error('flows-node-run-value-view: structure view must be tree, json or images');
        }
        this._structureView = next;
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} event
     */
    _onStringViewChange(event: CustomEvent): void {
        const next = event.detail && event.detail.value;
        if (next !== 'text' && next !== 'image') {
            throw new Error('flows-node-run-value-view: string view must be text or image');
        }
        this._stringView = next;
    }

    _renderImageGallery(parsed: unknown): TemplateResult {
        const rootPath = typeof this.rootPath === 'string' ? this.rootPath : '';
        const images = collectJsonImages(parsed, rootPath);
        if (images.length === 0) {
            return html`<p class="empty">${this.t('node_run_result_modal.images_empty')}</p>`;
        }
        return html`
            <div class="image-gallery">
                ${images.map((image) => html`
                    <article class="image-card" data-path=${image.path}>
                        <div class="image-card-meta">${image.path} · ${image.mimeType} · ${formatFileSize(image.byteLength)}</div>
                        <img src=${image.src} alt=${image.path} />
                    </article>
                `)}
            </div>
        `;
    }

    /**
     * @param {unknown} parsed
     */
    _renderStructure(parsed: unknown): TemplateResult {
        const rootPath = typeof this.rootPath === 'string' ? this.rootPath : '';
        const hasImages = collectJsonImages(parsed, rootPath).length > 0;
        const structureView: StructureView = this._structureView === 'images' && !hasImages
            ? 'tree'
            : this._structureView;
        const items = [
            { value: 'tree', label: this.t('node_run_result_modal.view_tree') },
            { value: 'json', label: this.t('node_run_result_modal.view_json') },
        ];
        if (hasImages) {
            items.push({ value: 'images', label: this.t('node_run_result_modal.view_images') });
        }
        return html`
            <div class="toolbar">
                <platform-segmented-control
                    density="dense"
                    .value=${structureView}
                    .items=${items}
                    @change=${this._onStructureChange}
                ></platform-segmented-control>
            </div>
            <div class="viewer">
                ${structureView === 'json' ? html`
                    <platform-json-editor
                        readonly
                        fill-parent
                        .showToolbar=${false}
                        .value=${formatJsonPretty(parsed)}
                    ></platform-json-editor>
                ` : structureView === 'images' ? this._renderImageGallery(parsed) : html`
                    <platform-json-tree
                        .value=${parsed}
                        .rootPath=${rootPath}
                        .selectedPath=${this._treePath}
                        @select=${this._onTreeSelect}
                    ></platform-json-tree>
                `}
            </div>
        `;
    }

    /**
     * @param {Record<string, unknown>} value
     */
    _renderStatusMap(value: Record<string, unknown>): TemplateResult {
        const entries = Object.entries(value);
        return html`
            <div class="status-list">
                ${entries.map(([key, entry]) => {
                    if (!isPlainObject(entry)) {
                        throw new Error('flows-node-run-value-view: status entry must be an object');
                    }
                    const ok = entry.ok === true;
                    const latencyMs = entry.latency_ms;
                    return html`
                        <div class="status-card" data-ok=${ok ? 'true' : 'false'}>
                            <span class="status-key">${key}</span>
                            <span class="status-state">${ok
                                ? this.t('node_run_result_modal.status_ok')
                                : this.t('node_run_result_modal.status_fail')}</span>
                            ${typeof latencyMs === 'number' && Number.isFinite(latencyMs) ? html`
                                <span class="status-latency">${this.t('canvas_run_result.duration_ms', {
                                    ms: String(Math.round(latencyMs)),
                                })}</span>
                            ` : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }

    _renderString(parsed: string): TemplateResult {
        const image = resolveBase64Image(parsed);
        if (image === null) {
            return html`
                <platform-code-editor
                    language="text"
                    readonly
                    fill-parent
                    .value=${parsed}
                ></platform-code-editor>
            `;
        }
        return html`
            <div class="toolbar">
                <platform-segmented-control
                    density="dense"
                    .value=${this._stringView}
                    .items=${[
                        { value: 'image', label: this.t('node_run_result_modal.view_images') },
                        { value: 'text', label: this.t('node_run_result_modal.view_text') },
                    ]}
                    @change=${this._onStringViewChange}
                ></platform-segmented-control>
            </div>
            <div class="viewer">
                ${this._stringView === 'text' ? html`
                    <platform-code-editor
                        language="text"
                        readonly
                        fill-parent
                        .value=${parsed}
                    ></platform-code-editor>
                ` : html`
                    <div class="image-gallery">
                        <article class="image-card">
                            <div class="image-card-meta">${image.mimeType} · ${formatFileSize(image.byteLength)}</div>
                            <img src=${image.src} alt=${this.t('node_run_result_modal.image_alt')} />
                        </article>
                    </div>
                `}
            </div>
        `;
    }

    override render(): TemplateResult {
        const classified = classifyNodeRunValue(this.value);
        if (classified.kind === 'null' || classified.kind === 'empty') {
            return html`<p class="empty">${this.t('node_run_result_modal.empty_value')}</p>`;
        }
        if (classified.kind === 'boolean') {
            const text = classified.parsed === true
                ? this.t('canvas_run_result.value_true')
                : this.t('canvas_run_result.value_false');
            return html`<p class="scalar">${text}</p>`;
        }
        if (classified.kind === 'number') {
            return html`<p class="scalar">${serializeNodeRunValue(this.value)}</p>`;
        }
        if (classified.kind === 'string') {
            if (typeof classified.parsed !== 'string') {
                throw new Error('flows-node-run-value-view: string requires string parsed');
            }
            return this._renderString(classified.parsed);
        }
        if (classified.kind === 'markdown') {
            if (typeof classified.parsed !== 'string') {
                throw new Error('flows-node-run-value-view: markdown requires string parsed');
            }
            return html`
                <platform-markdown-editor
                    readonly
                    view-mode="preview"
                    .showHeader=${false}
                    .showHint=${false}
                    .value=${classified.parsed}
                ></platform-markdown-editor>
            `;
        }
        if (classified.kind === 'status_map') {
            if (!isPlainObject(classified.parsed)) {
                throw new Error('flows-node-run-value-view: status map requires an object');
            }
            return this._renderStatusMap(classified.parsed);
        }
        if (classified.kind === 'json_string' || classified.kind === 'array' || classified.kind === 'object') {
            return this._renderStructure(classified.parsed);
        }
        throw new Error(`flows-node-run-value-view: unsupported kind ${classified.kind}`);
    }
}

customElements.define('flows-node-run-value-view', FlowsNodeRunValueView);
