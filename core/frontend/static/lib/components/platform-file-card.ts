/**
 * platform-file-card — карточка файла или каталога для grid view file manager.
 * События: `open` (клик — выбор), `activate` (двойной клик — открыть).
 * Каталог: `itemKind=catalog`, цветная folder file-icon, обязательный `sizeLabel`.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { formatFileSize } from '../utils/format-file-size.js';
import './platform-icon.js';

const RAG_INDEX_ICON_BY_STATUS = {
    ready: 'check',
    pending: 'hourglass-top',
    failed: 'alert-triangle',
    absent: 'database',
};

function ragIndexIcon(status: string): string | undefined {
    switch (status) {
        case 'ready': return RAG_INDEX_ICON_BY_STATUS.ready;
        case 'pending': return RAG_INDEX_ICON_BY_STATUS.pending;
        case 'failed': return RAG_INDEX_ICON_BY_STATUS.failed;
        case 'absent': return RAG_INDEX_ICON_BY_STATUS.absent;
        default: return undefined;
    }
}

const ITEM_KIND_FILE = 'file';
const ITEM_KIND_CATALOG = 'catalog';

export class PlatformFileCard extends PlatformElement {
    static override properties: PropertyDeclarations = {
        fileName: { type: String, attribute: 'file-name' },
        mimeType: { type: String, attribute: 'mime-type' },
        fileSize: { type: Number, attribute: 'file-size' },
        sizeLabel: { type: String, attribute: 'size-label' },
        dateLabel: { type: String, attribute: 'date-label' },
        retentionLabel: { type: String, attribute: 'retention-label' },
        typeLabel: { type: String, attribute: 'type-label' },
        selected: { type: Boolean, reflect: true },
        dropTarget: { type: Boolean, reflect: true, attribute: 'drop-target' },
        itemKind: { type: String, attribute: 'item-kind' },
        itemKey: { type: String, attribute: 'item-key' },
        indexStatus: { type: String, attribute: 'index-status' },
        indexStatusLabel: { type: String, attribute: 'index-status-label' },
        hintIcon: { type: String, attribute: 'hint-icon' },
        hintIconLabel: { type: String, attribute: 'hint-icon-label' },
    };
    declare fileName: string;
    declare mimeType: string;
    declare fileSize: number;
    declare sizeLabel: string;
    declare dateLabel: string;
    declare retentionLabel: string;
    declare typeLabel: string;
    declare selected: boolean;
    declare dropTarget: boolean;
    declare itemKind: string;
    declare itemKey: string;
    declare indexStatus: string;
    declare indexStatusLabel: string;
    declare hintIcon: string;
    declare hintIconLabel: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .card {
                position: relative;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-4);
                min-height: 9rem;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--documents-selected-stroke, var(--glass-border-medium));
                box-shadow: var(--glass-shadow-medium);
                transform: translateY(-1px);
            }
            :host([selected]) .card {
                border-color: var(--documents-selected-stroke, var(--accent));
                background: var(--documents-selected-bg, var(--accent-subtle));
            }
            :host([drop-target]) .card {
                border-color: var(--accent);
                background: var(--documents-selected-bg, var(--accent-subtle));
                box-shadow: var(--glass-shadow-medium);
            }
            .icon-wrap {
                width: 2.5rem;
                height: 2.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }
            .index-status,
            .hint-icon {
                position: absolute;
                right: -0.25rem;
                bottom: -0.25rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.125rem;
                height: 1.125rem;
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong, var(--bg-primary, #fff));
                box-shadow: var(--glass-shadow-subtle);
                color: var(--text-tertiary);
            }
            .index-status--ready {
                color: var(--success);
            }
            .index-status--pending {
                color: var(--warning);
                animation: index-status-pulse 1.6s ease-in-out infinite;
            }
            .index-status--failed {
                color: var(--error);
            }
            .index-status--absent {
                color: var(--text-tertiary);
                opacity: 0.85;
            }
            @keyframes index-status-pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.45; }
            }
            .title {
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }
            .actions {
                position: absolute;
                top: var(--space-2);
                right: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.fileName = '';
        this.mimeType = '';
        this.fileSize = 0;
        this.sizeLabel = '';
        this.dateLabel = '';
        this.retentionLabel = '';
        this.typeLabel = '';
        this.selected = false;
        this.dropTarget = false;
        this.itemKind = ITEM_KIND_FILE;
        this.itemKey = '';
        this.indexStatus = '';
        this.indexStatusLabel = '';
        this.hintIcon = '';
        this.hintIconLabel = '';
    }

    _resolvedItemKind() {
        const kind = typeof this.itemKind === 'string' && this.itemKind.length > 0
            ? this.itemKind
            : ITEM_KIND_FILE;
        if (kind !== ITEM_KIND_FILE && kind !== ITEM_KIND_CATALOG) {
            throw new Error(`platform-file-card: itemKind must be file|catalog, got '${kind}'`);
        }
        return kind;
    }

    _sizeLabel() {
        const kind = this._resolvedItemKind();
        if (kind === ITEM_KIND_CATALOG) {
            if (typeof this.sizeLabel !== 'string' || this.sizeLabel.length === 0) {
                throw new Error('platform-file-card: sizeLabel required for itemKind=catalog');
            }
            return this.sizeLabel;
        }
        if (typeof this.fileSize !== 'number' || this.fileSize <= 0) {
            return '—';
        }
        return formatFileSize(this.fileSize);
    }

    _fileIconName() {
        if (this._resolvedItemKind() === ITEM_KIND_CATALOG) {
            return 'folder';
        }
        return resolveFileIconKey(this.fileName, this.mimeType);
    }

    _primaryMeta() {
        if (this._resolvedItemKind() === ITEM_KIND_CATALOG) {
            return `${this._sizeLabel()} · ${this.typeLabel}`;
        }
        return `${this._sizeLabel()} · ${this.dateLabel}`;
    }

    _isInteractiveTarget(target: EventTarget | null): boolean {
        return target instanceof HTMLElement && Boolean(target.closest('.actions'));
    }

    _onClick(e: Event) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('open', { itemKey: this.itemKey });
    }

    _onDblClick(e: Event) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('activate', { itemKey: this.itemKey });
    }

    _onDragOver(e: DragEvent) {
        if (this._resolvedItemKind() !== ITEM_KIND_CATALOG) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'move';
        }
        if (!this.dropTarget) {
            this.dropTarget = true;
        }
        this.emit('row-dragover', { itemKey: this.itemKey, nativeEvent: e });
    }

    _onDragLeave(e: DragEvent) {
        if (this._resolvedItemKind() !== ITEM_KIND_CATALOG) {
            return;
        }
        e.preventDefault();
        this.dropTarget = false;
        this.emit('row-dragleave', { itemKey: this.itemKey, nativeEvent: e });
    }

    _onDrop(e: DragEvent) {
        if (this._resolvedItemKind() !== ITEM_KIND_CATALOG) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        this.dropTarget = false;
        this.emit('row-drop', { itemKey: this.itemKey, nativeEvent: e });
    }

    _renderIndexStatus() {
        const status = typeof this.indexStatus === 'string' ? this.indexStatus.trim() : '';
        const iconName = ragIndexIcon(status);
        if (iconName === undefined) {
            return nothing;
        }
        const label = typeof this.indexStatusLabel === 'string' ? this.indexStatusLabel : '';
        return html`
            <span
                class="index-status index-status--${status}"
                role="img"
                title=${label}
                aria-label=${label}
            >
                <platform-icon name=${iconName} size="12"></platform-icon>
            </span>
        `;
    }

    _renderHintIcon() {
        const iconName = typeof this.hintIcon === 'string' ? this.hintIcon.trim() : '';
        if (iconName.length === 0) {
            return nothing;
        }
        const label = typeof this.hintIconLabel === 'string' ? this.hintIconLabel.trim() : '';
        if (label.length === 0) {
            throw new Error('platform-file-card: hintIconLabel required when hintIcon is set');
        }
        return html`
            <span
                class="hint-icon"
                role="img"
                title=${label}
                aria-label=${label}
            >
                <platform-icon name=${iconName} size="12"></platform-icon>
            </span>
        `;
    }

    override render(): TemplateResult {
        const iconKey = this._fileIconName();
        const kind = this._resolvedItemKind();
        return html`
            <div
                class="card"
                @click=${this._onClick}
                @dblclick=${this._onDblClick}
                @dragover=${this._onDragOver}
                @dragleave=${this._onDragLeave}
                @drop=${this._onDrop}
            >
                <div class="actions" @click=${(e: Event) => e.stopPropagation()}>
                    <slot name="actions"></slot>
                </div>
                <div class="icon-wrap">
                    <platform-icon file-icon name=${iconKey} size="32"></platform-icon>
                    ${this._renderHintIcon()}
                    ${this._renderIndexStatus()}
                </div>
                <div class="title" title=${this.fileName}>${this.fileName}</div>
                <div class="meta">${this._primaryMeta()}</div>
                ${kind === ITEM_KIND_FILE && this.retentionLabel
                    ? html`<div class="meta">${this.retentionLabel}</div>`
                    : nothing}
                ${kind === ITEM_KIND_FILE && this.typeLabel
                    ? html`<div class="meta">${this.typeLabel}</div>`
                    : nothing}
            </div>
        `;
    }
}

customElements.define('platform-file-card', PlatformFileCard);
