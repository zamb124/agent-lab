/**
 * platform-file-card — карточка файла для grid view file manager.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { formatFileSize } from '../utils/format-file-size.js';
import './platform-icon.js';

export class PlatformFileCard extends PlatformElement {
    static properties = {
        fileName: { type: String, attribute: 'file-name' },
        mimeType: { type: String, attribute: 'mime-type' },
        fileSize: { type: Number, attribute: 'file-size' },
        dateLabel: { type: String, attribute: 'date-label' },
        typeLabel: { type: String, attribute: 'type-label' },
        selected: { type: Boolean, reflect: true },
        itemKey: { type: String, attribute: 'item-key' },
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
        this.typeLabel = '';
        this.selected = false;
        this.itemKey = '';
    }

    _sizeLabel() {
        if (typeof this.fileSize !== 'number' || this.fileSize <= 0) {
            return '—';
        }
        return formatFileSize(this.fileSize);
    }

    _onClick(e) {
        if (e.target instanceof HTMLElement && e.target.closest('.actions')) {
            return;
        }
        this.emit('open', { itemKey: this.itemKey });
    }

    render() {
        const iconKey = resolveFileIconKey(this.fileName, this.mimeType);
        return html`
            <div class="card" @click=${this._onClick}>
                <div class="actions" @click=${(e) => e.stopPropagation()}>
                    <slot name="actions"></slot>
                </div>
                <div class="icon-wrap">
                    <platform-icon file-icon name=${iconKey} size="32"></platform-icon>
                </div>
                <div class="title" title=${this.fileName}>${this.fileName}</div>
                <div class="meta">${this._sizeLabel()} · ${this.dateLabel}</div>
                ${this.typeLabel ? html`<div class="meta">${this.typeLabel}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('platform-file-card', PlatformFileCard);
