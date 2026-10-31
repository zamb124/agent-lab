/**
 * platform-file-row — строка файла или каталога для табличного file manager.
 *
 * Presentational: icon, title, meta-колонки, optional checkbox и slot actions.
 * События: `open` (клик — выбор), `activate` (двойной клик — открыть).
 * Каталог: `itemKind=catalog`, цветная folder file-icon, обязательный `sizeLabel`.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { formatFileSize } from '../utils/format-file-size.js';
import './platform-icon.js';
import './platform-user-chip.js';

const RAG_INDEX_ICON_BY_STATUS: Readonly<Record<string, string>> = {
    ready: 'check',
    pending: 'hourglass-top',
    failed: 'alert-triangle',
    absent: 'database',
};

function checkboxChecked(event: Event): boolean {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('platform-file-row: checkbox target must be an input');
    }
    return target.checked;
}

const ITEM_KIND_FILE = 'file';
const ITEM_KIND_CATALOG = 'catalog';

export class PlatformFileRow extends PlatformElement {
    static override properties: PropertyDeclarations = {
        fileName: { type: String, attribute: 'file-name' },
        mimeType: { type: String, attribute: 'mime-type' },
        fileSize: { type: Number, attribute: 'file-size' },
        sizeLabel: { type: String, attribute: 'size-label' },
        dateLabel: { type: String, attribute: 'date-label' },
        retentionLabel: { type: String, attribute: 'retention-label' },
        typeLabel: { type: String, attribute: 'type-label' },
        authorUserId: { type: String, attribute: 'author-user-id' },
        authorName: { type: String, attribute: 'author-name' },
        selected: { type: Boolean, reflect: true },
        selectable: { type: Boolean, reflect: true },
        draggable: { type: Boolean, reflect: true },
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
    declare authorUserId: string;
    declare authorName: string;
    declare selected: boolean;
    declare selectable: boolean;
    declare draggable: boolean;
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
            .row {
                display: grid;
                grid-template-columns: var(--platform-file-row-columns, 2rem 1fr 6rem 8rem 7rem 8rem 6rem 2.5rem);
                gap: var(--space-3);
                align-items: center;
                min-height: var(--documents-explorer-table-row-height);
                padding: 0 var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: transparent;
                transition: var(--motion-transition-interactive);
                cursor: pointer;
            }
            .row:hover {
                background: var(--glass-solid-subtle);
            }
            :host([selected]) .row {
                background: var(--documents-selected-bg);
            }
            :host([drop-target]) .row {
                background: var(--documents-selected-bg);
                box-shadow: inset 0 0 0 1px var(--accent);
            }
            .cell {
                min-width: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .cell-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .cell-title-text {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .index-status,
            .hint-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                width: 1.25rem;
                height: 1.25rem;
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
            .cell-meta {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .checkbox-wrap {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .checkbox-wrap input[type="checkbox"] {
                width: 1rem;
                height: 1rem;
                cursor: pointer;
            }
            .actions {
                display: flex;
                justify-content: flex-end;
            }
            @media (max-width: 767px) {
                .row {
                    grid-template-columns: var(--platform-file-row-columns-mobile, 2rem 1fr 2.5rem);
                }
                .cell-hide-mobile {
                    display: none;
                }
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
        this.authorUserId = '';
        this.authorName = '';
        this.selected = false;
        this.selectable = false;
        this.draggable = false;
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
            throw new Error(`platform-file-row: itemKind must be file|catalog, got '${kind}'`);
        }
        return kind;
    }

    _sizeCell() {
        const kind = this._resolvedItemKind();
        if (kind === ITEM_KIND_CATALOG) {
            if (typeof this.sizeLabel !== 'string' || this.sizeLabel.length === 0) {
                throw new Error('platform-file-row: sizeLabel required for itemKind=catalog');
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

    _isInteractiveTarget(target: EventTarget | null): boolean {
        return target instanceof HTMLElement
            && Boolean(target.closest('.checkbox-wrap') || target.closest('.actions'));
    }

    _onRowClick(e: Event) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('open', { itemKey: this.itemKey });
    }

    _onRowDblClick(e: Event) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('activate', { itemKey: this.itemKey });
    }

    _onCheckboxChange(e: Event) {
        const checked = checkboxChecked(e);
        this.emit('select-toggle', { itemKey: this.itemKey, selected: checked });
    }

    _onDragStart(e: DragEvent) {
        if (!this.draggable) {
            return;
        }
        this.emit('row-dragstart', { itemKey: this.itemKey, nativeEvent: e });
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

    _onDragLeave(e: Event) {
        if (this._resolvedItemKind() !== ITEM_KIND_CATALOG) {
            return;
        }
        e.preventDefault();
        this.dropTarget = false;
        this.emit('row-dragleave', { itemKey: this.itemKey, nativeEvent: e });
    }

    _onDrop(e: Event) {
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
        const iconName = RAG_INDEX_ICON_BY_STATUS[status];
        if (!iconName) {
            return nothing;
        }
        const label = typeof this.indexStatusLabel === 'string' ? this.indexStatusLabel : '';
        return html`
            <span
                class="index-status index-status--${status}"
                role="img"
                title=${label}
                aria-label=${label}
                @click=${(e: Event) => e.stopPropagation()}
            >
                <platform-icon name=${iconName} size="14"></platform-icon>
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
            throw new Error('platform-file-row: hintIconLabel required when hintIcon is set');
        }
        return html`
            <span
                class="hint-icon"
                role="img"
                title=${label}
                aria-label=${label}
                @click=${(e: Event) => e.stopPropagation()}
            >
                <platform-icon name=${iconName} size="14"></platform-icon>
            </span>
        `;
    }

    override render(): TemplateResult {
        const iconKey = this._fileIconName();
        return html`
            <div
                class="row"
                role="row"
                ?draggable=${this.draggable}
                @dragstart=${this._onDragStart}
                @dragover=${this._onDragOver}
                @dragleave=${this._onDragLeave}
                @drop=${this._onDrop}
                @click=${this._onRowClick}
                @dblclick=${this._onRowDblClick}
            >
                <div class="cell checkbox-wrap" role="cell">
                    ${this.selectable ? html`
                        <input
                            type="checkbox"
                            .checked=${this.selected}
                            @click=${(e: Event) => e.stopPropagation()}
                            @change=${this._onCheckboxChange}
                            aria-label=${this.fileName}
                        />
                    ` : ''}
                </div>
                <div class="cell cell-title" role="cell">
                    <platform-icon file-icon name=${iconKey} size="20"></platform-icon>
                    <span class="cell-title-text">${this.fileName}</span>
                    ${this._renderHintIcon()}
                    ${this._renderIndexStatus()}
                </div>
                <div class="cell cell-meta cell-hide-mobile" role="cell">${this._sizeCell()}</div>
                <div class="cell cell-meta cell-hide-mobile" role="cell">${this.dateLabel}</div>
                <div class="cell cell-meta cell-hide-mobile" role="cell">${this.retentionLabel}</div>
                <div class="cell cell-meta cell-hide-mobile" role="cell">
                    ${this.authorUserId
                        ? html`<platform-user-chip user-id=${this.authorUserId}></platform-user-chip>`
                        : html`<span>${this.authorName}</span>`}
                </div>
                <div class="cell cell-meta cell-hide-mobile" role="cell">${this.typeLabel}</div>
                <div class="cell actions" role="cell" @click=${(e: Event) => e.stopPropagation()}>
                    <slot name="actions"></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-file-row', PlatformFileRow);
