/**
 * Дерево JSON: ключи, значения листьев, типы; base64-картинки — inline-превью.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { isPlainRecord } from '../events/payload.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { formatJsonLeafPreview, resolveJsonImage } from '../utils/base64-image.js';
import { jsonTreeChildPath } from '../utils/json-tree-path.js';
import './platform-icon.js';

type JsonTreeKind = 'null' | 'boolean' | 'number' | 'string' | 'array' | 'object';

interface JsonTreeClassification {
    kind: JsonTreeKind;
    size: number | null;
}

function classifyJsonTreeValue(value: unknown): JsonTreeClassification {
    if (value === null) {
        return { kind: 'null', size: null };
    }
    if (typeof value === 'boolean') {
        return { kind: 'boolean', size: null };
    }
    if (typeof value === 'number' || typeof value === 'bigint') {
        return { kind: 'number', size: null };
    }
    if (typeof value === 'string') {
        return { kind: 'string', size: null };
    }
    if (Array.isArray(value)) {
        return { kind: 'array', size: value.length };
    }
    if (isPlainRecord(value)) {
        return { kind: 'object', size: Object.keys(value).length };
    }
    throw new Error(`platform-json-tree: unsupported value type ${typeof value}`);
}

export class PlatformJsonTree extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { attribute: false },
        rootPath: { type: String, attribute: 'root-path' },
        selectedPath: { type: String, attribute: 'selected-path' },
        _expanded: { state: true },
        _imageOpen: { state: true },
    };

    declare value: unknown;
    declare rootPath: string;
    declare selectedPath: string;
    declare _expanded: Set<string>;
    declare _imageOpen: Set<string>;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                font-family: var(--font-sans);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .empty {
                margin: 0;
                padding: var(--space-4);
                color: var(--text-tertiary);
            }
            .row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                cursor: pointer;
                min-width: 0;
            }
            .row:hover {
                background: var(--glass-solid-subtle);
            }
            .row[data-selected='true'] {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .chevron {
                flex-shrink: 0;
                width: 16px;
                height: 16px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }
            .chevron[data-leaf='true'] {
                visibility: hidden;
            }
            .key {
                font-family: var(--font-mono);
                font-weight: var(--font-semibold);
                flex-shrink: 0;
                max-width: 40%;
                word-break: break-word;
            }
            .preview {
                font-family: var(--font-mono);
                font-weight: var(--font-normal);
                color: var(--text-secondary);
                min-width: 0;
                flex: 1 1 auto;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .row[data-selected='true'] .preview {
                color: var(--accent);
            }
            .kind {
                flex-shrink: 0;
                margin-left: auto;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .image-toggle {
                flex-shrink: 0;
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                padding: 0;
            }
            .image-toggle:hover,
            .image-toggle:focus-visible,
            .image-toggle[aria-pressed='true'] {
                color: var(--accent);
                border-color: var(--accent);
                outline: none;
            }
            .children {
                padding-left: var(--space-4);
            }
            .image-preview {
                margin: 0 0 var(--space-2) calc(16px + var(--space-1) + var(--space-2));
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-solid-subtle);
                max-width: min(100%, 420px);
            }
            .image-preview img {
                display: block;
                max-width: 100%;
                max-height: 280px;
                object-fit: contain;
                border-radius: var(--radius-sm);
            }
            .image-meta {
                margin-top: var(--space-1);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                font-family: var(--font-mono);
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.rootPath = '';
        this.selectedPath = '';
        this._expanded = new Set<string>();
        this._imageOpen = new Set<string>();
    }

    _onSelectableKeydown(event: KeyboardEvent, handler: () => void): void {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    _isExpandable(value: unknown): boolean {
        if (value === null || typeof value !== 'object') {
            return false;
        }
        if (Array.isArray(value)) {
            return value.length > 0;
        }
        return Object.keys(value).length > 0;
    }

    _kindLabel(classified: JsonTreeClassification): string {
        if (classified.kind === 'null') {
            return this.t('json_tree.type_null');
        }
        if (classified.kind === 'boolean') {
            return this.t('json_tree.type_boolean');
        }
        if (classified.kind === 'number') {
            return this.t('json_tree.type_number');
        }
        if (classified.kind === 'string') {
            return this.t('json_tree.type_string');
        }
        if (classified.kind === 'array') {
            if (classified.size === null) {
                throw new Error('platform-json-tree: array kind requires size');
            }
            return this.t('json_tree.type_array', { count: String(classified.size) });
        }
        if (classified.kind === 'object') {
            if (classified.size === null) {
                throw new Error('platform-json-tree: object kind requires size');
            }
            return this.t('json_tree.type_object', { count: String(classified.size) });
        }
        throw new Error(`platform-json-tree: unknown kind ${classified.kind}`);
    }

    _select(path: string, value: unknown): void {
        this.emit('select', { path, value });
        if (!this._isExpandable(value)) {
            return;
        }
        const next = new Set(this._expanded);
        if (next.has(path)) {
            next.delete(path);
        } else {
            next.add(path);
        }
        this._expanded = next;
    }

    _toggleImage(event: Event, path: string): void {
        event.stopPropagation();
        const next = new Set(this._imageOpen);
        if (next.has(path)) {
            next.delete(path);
        } else {
            next.add(path);
        }
        this._imageOpen = next;
    }

    _renderRow(label: string, childValue: unknown, path: string): TemplateResult {
        const expandable = this._isExpandable(childValue);
        const expanded = this._expanded.has(path);
        const classified = classifyJsonTreeValue(childValue);
        const kindLabel = this._kindLabel(classified);
        const selected = this.selectedPath === path;
        const leafPreview = formatJsonLeafPreview(childValue);
        const image = resolveJsonImage(childValue);
        const imageOpen = image !== null && this._imageOpen.has(path);
        return html`
            <article
                class="row"
                role="button"
                tabindex="0"
                data-path=${path}
                data-selected=${selected ? 'true' : 'false'}
                @click=${() => this._select(path, childValue)}
                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._select(path, childValue))}
            >
                <span class="chevron" data-leaf=${expandable ? 'false' : 'true'}>
                    <platform-icon name=${expanded ? 'chevron-down' : 'chevron-right'} size="12"></platform-icon>
                </span>
                <span class="key">${label}</span>
                ${leafPreview !== null ? html`<span class="preview" title=${leafPreview}>${leafPreview}</span>` : nothing}
                ${image !== null ? html`
                    <button
                        type="button"
                        class="image-toggle"
                        aria-pressed=${imageOpen ? 'true' : 'false'}
                        title=${imageOpen
                            ? this.t('json_tree.hide_image')
                            : this.t('json_tree.show_image')}
                        aria-label=${imageOpen
                            ? this.t('json_tree.hide_image')
                            : this.t('json_tree.show_image')}
                        @click=${(event: Event) => this._toggleImage(event, path)}
                    >
                        <platform-icon name="image" size="14"></platform-icon>
                    </button>
                ` : nothing}
                <span class="kind">${kindLabel}</span>
            </article>
            ${imageOpen && image !== null ? html`
                <div class="image-preview">
                    <img src=${image.src} alt=${this.t('json_tree.image_alt', { path })} />
                    <div class="image-meta">${image.mimeType} · ${formatFileSize(image.byteLength)}</div>
                </div>
            ` : nothing}
            ${expandable && expanded ? html`<div class="children">${this._renderChildren(childValue, path)}</div>` : nothing}
        `;
    }

    _renderChildren(value: unknown, parentPath: string): TemplateResult[] {
        if (Array.isArray(value)) {
            const items: unknown[] = [];
            for (const item of value) {
                items.push(item);
            }
            return items.map((item, index) => this._renderRow(
                String(index),
                item,
                jsonTreeChildPath(parentPath, index, true),
            ));
        }
        if (!isPlainRecord(value)) {
            throw new Error('platform-json-tree: children require object or array');
        }
        return Object.keys(value).map((key) => this._renderRow(
            key,
            value[key],
            jsonTreeChildPath(parentPath, key, false),
        ));
    }

    override render(): TemplateResult {
        const value = this.value;
        if (value === null || typeof value !== 'object') {
            throw new Error('platform-json-tree: value must be an object or array');
        }
        const empty = Array.isArray(value) ? value.length === 0 : Object.keys(value).length === 0;
        if (empty) {
            return html`<p class="empty">${this.t('json_tree.empty')}</p>`;
        }
        const rootPath = typeof this.rootPath === 'string' ? this.rootPath : '';
        return html`${this._renderChildren(value, rootPath)}`;
    }
}

customElements.define('platform-json-tree', PlatformJsonTree);
