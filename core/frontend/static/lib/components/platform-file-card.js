/**
 * platform-file-card — карточка файла для grid view file manager.
 * События: `open` (клик — выбор), `activate` (двойной клик — открыть).
 */

import { html, css, nothing } from 'lit';
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

export class PlatformFileCard extends PlatformElement {
    static properties = {
        fileName: { type: String, attribute: 'file-name' },
        mimeType: { type: String, attribute: 'mime-type' },
        fileSize: { type: Number, attribute: 'file-size' },
        dateLabel: { type: String, attribute: 'date-label' },
        retentionLabel: { type: String, attribute: 'retention-label' },
        typeLabel: { type: String, attribute: 'type-label' },
        selected: { type: Boolean, reflect: true },
        itemKey: { type: String, attribute: 'item-key' },
        indexStatus: { type: String, attribute: 'index-status' },
        indexStatusLabel: { type: String, attribute: 'index-status-label' },
    };

    static styles = [
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
            .icon-wrap {
                width: 2.5rem;
                height: 2.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }
            .index-status {
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
        this.dateLabel = '';
        this.retentionLabel = '';
        this.typeLabel = '';
        this.selected = false;
        this.itemKey = '';
        this.indexStatus = '';
        this.indexStatusLabel = '';
    }

    _sizeLabel() {
        if (typeof this.fileSize !== 'number' || this.fileSize <= 0) {
            return '—';
        }
        return formatFileSize(this.fileSize);
    }

    _isInteractiveTarget(target) {
        return target instanceof HTMLElement && Boolean(target.closest('.actions'));
    }

    _onClick(e) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('open', { itemKey: this.itemKey });
    }

    _onDblClick(e) {
        if (this._isInteractiveTarget(e.target)) {
            return;
        }
        this.emit('activate', { itemKey: this.itemKey });
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
            >
                <platform-icon name=${iconName} size="12"></platform-icon>
            </span>
        `;
    }

    render() {
        const iconKey = resolveFileIconKey(this.fileName, this.mimeType);
        return html`
            <div class="card" @click=${this._onClick} @dblclick=${this._onDblClick}>
                <div class="actions" @click=${(e) => e.stopPropagation()}>
                    <slot name="actions"></slot>
                </div>
                <div class="icon-wrap">
                    <platform-icon file-icon name=${iconKey} size="32"></platform-icon>
                    ${this._renderIndexStatus()}
                </div>
                <div class="title" title=${this.fileName}>${this.fileName}</div>
                <div class="meta">${this._sizeLabel()} · ${this.dateLabel}</div>
                ${this.retentionLabel ? html`<div class="meta">${this.retentionLabel}</div>` : ''}
                ${this.typeLabel ? html`<div class="meta">${this.typeLabel}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('platform-file-card', PlatformFileCard);
