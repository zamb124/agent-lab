/**
 * `<platform-catalog-product-card>` — компактная карточка товара каталога:
 * обложка (или иконка-заглушка), имя, SKU и чипы штрихкодов. Используется
 * в picker'е «подключить или создать» и везде, где товар показывается
 * компактно вне списка фасета.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import '../components/platform-icon.js';

export class PlatformCatalogProductCard extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        name: { type: String },
        sku: { type: String },
        imageUrl: { type: String, attribute: 'image-url' },
        barcodes: { type: Array },
        archived: { type: Boolean },
    };

    declare name: string;
    declare sku: string;
    declare imageUrl: string;
    declare barcodes: string[];
    declare archived: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .card {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            .thumb {
                width: 40px; height: 40px; flex-shrink: 0;
                border-radius: var(--radius-sm); overflow: hidden;
                background: var(--surface-2); color: var(--text-tertiary);
                display: flex; align-items: center; justify-content: center;
            }
            .thumb img { width: 100%; height: 100%; object-fit: cover; }
            .info { min-width: 0; flex: 1; }
            .name {
                font-size: var(--text-sm); font-weight: var(--font-medium);
                color: var(--text-primary);
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .name .archived { color: var(--text-tertiary); font-weight: var(--font-normal); }
            .meta {
                display: flex; align-items: center; gap: var(--space-2);
                font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px;
            }
            .codes { display: flex; gap: var(--space-1); flex-wrap: wrap; }
            .code {
                padding: 0 var(--space-1); border-radius: var(--radius-sm);
                background: var(--glass-tint-medium); font-variant-numeric: tabular-nums;
            }
        `,
    ];

    constructor() {
        super();
        this.name = '';
        this.sku = '';
        this.imageUrl = '';
        this.barcodes = [];
        this.archived = false;
    }

    override render(): TemplateResult {
        return html`
            <div class="card">
                <div class="thumb">
                    ${this.imageUrl !== ''
                        ? html`<img src=${this.imageUrl} alt="" />`
                        : html`<platform-icon name="tag" size="18"></platform-icon>`}
                </div>
                <div class="info">
                    <div class="name">
                        ${this.name}
                        ${this.archived ? html`<span class="archived">· ${this.t('catalog.archived')}</span>` : ''}
                    </div>
                    <div class="meta">
                        ${this.sku !== '' ? html`<span>${this.sku}</span>` : ''}
                        ${this.barcodes.length > 0
                            ? html`<span class="codes">${this.barcodes.map(
                                  (code) => html`<span class="code">${code}</span>`,
                              )}</span>`
                            : ''}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-catalog-product-card', PlatformCatalogProductCard);
