/**
 * Номенклатура склада: продукты и метод оценки карточки.
 *
 * «Новый товар» открывает picker каталога — подключить существующий
 * (`stock/product_create` с `product_id`) или создать новый в модалке.
 * Клик по строке — правка карточки.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { buildPlatformFileDownloadUrl } from '@platform/lib/utils/platform-files-url.js';
import type { StockProductView } from '@platform/lib/events/wire/stock.gen.js';
import { PlatformCatalogProductPicker } from '@platform/lib/catalog/product-picker.js';
import type { CatalogProductPick } from '@platform/lib/catalog/product-picker.js';
import { StockProductModal } from '../modals/stock-product-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-empty-state.js';
import { stockPageStyles } from '../styles/stock-page.styles.js';

export class StockProductsPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _products: ResourceController;

    static override styles = [
        PlatformPage.styles,
        stockPageStyles,
        css`
            tbody tr { cursor: pointer; }
            tbody tr.off td { opacity: 0.45; }
            .ptag {
                display: inline-flex; align-items: center; gap: 3px; margin-left: var(--space-2);
                padding: 1px var(--space-2); border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--text-primary) 10%, transparent);
                color: var(--text-secondary); font-size: 10px; font-weight: var(--font-bold);
                vertical-align: middle;
            }
            .ptag platform-icon { color: var(--text-secondary); }
            .pimg {
                width: 28px; height: 28px; border-radius: var(--radius-md);
                object-fit: cover; display: block; background: var(--bg-muted);
            }
            .pimg-ph {
                width: 28px; height: 28px; border-radius: var(--radius-md);
                display: flex; align-items: center; justify-content: center;
                background: var(--bg-muted); color: var(--text-tertiary);
            }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this._products = this.useResource('stock/products', { autoload: true });
    }

    private _openCreate(): void {
        this.openModal(PlatformCatalogProductPicker, {
            suggestOpName: 'stock/catalog_products_suggest',
            onPick: (item: CatalogProductPick) => {
                this.openModal(StockProductModal, {
                    product: null,
                    attachProduct: item,
                    onSaved: () => this._products.load(),
                });
            },
            onCreateNew: (initialName: string) => {
                this.openModal(StockProductModal, {
                    product: null,
                    initialName,
                    onSaved: () => this._products.load(),
                });
            },
        });
    }

    private _openEdit(row: unknown): void {
        if (!isPlainRecord(row) || typeof row.product_id !== 'string') return;
        this.openModal(StockProductModal, {
            product: row as unknown as StockProductView,
            onSaved: () => this._products.load(),
        });
    }

    private _productImage(row: unknown) {
        const fileId = isPlainRecord(row) && Array.isArray(row.image_file_ids)
            ? row.image_file_ids[0] : null;
        return typeof fileId === 'string' && fileId !== ''
            ? html`<img class="pimg" src=${buildPlatformFileDownloadUrl(fileId)} alt="">`
            : html`<div class="pimg-ph"><platform-icon name="package" size="14"></platform-icon></div>`;
    }

    override render() {
        const items = this._products.items;
        return html`
            <div class="wrap">
                <page-header title=${this.t('products.title')} dense>
                    <platform-button slot="actions" variant="primary" @click=${this._openCreate}>
                        <platform-icon name="plus" size="14"></platform-icon> ${this.t('products.create')}
                    </platform-button>
                </page-header>
                ${this._products.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                    ? html`<platform-empty-state icon="tag" title=${this.t('products.empty')}></platform-empty-state>`
                    : html`
                        <div class="table-card"><div class="scroll"><table>
                            <thead><tr>
                                <th></th>
                                <th>${this.t('fields.sku')}</th>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.barcodes')}</th>
                                <th>${this.t('fields.valuation_method')}</th>
                                <th class="num">${this.t('fields.standard_price')}</th>
                                <th>${this.t('fields.tracking')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row) => html`
                                    <tr class=${row.is_archived || row.is_active === false ? 'off' : ''}
                                        data-product-id=${isPlainRecord(row) ? String(row.product_id ?? '') : ''}
                                        @click=${() => this._openEdit(row)}>
                                        <td>${this._productImage(row)}</td>
                                        <td>${row.sku}</td>
                                        <td>${row.name}${row.is_archived
                                            ? html`<span class="ptag"><platform-icon name="box" size="11"></platform-icon>${this.t('products.archived')}</span>`
                                            : nothing}${row.is_active === false
                                            ? html`<span class="ptag">${this.t('products.inactive')}</span>`
                                            : nothing}</td>
                                        <td>${Array.isArray(row.barcodes) ? (row.barcodes as string[]).join(', ') : ''}</td>
                                        <td>${row.valuation_method}</td>
                                        <td class="num">${row.standard_price}</td>
                                        <td>${row.tracking}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table></div></div>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-products-page', StockProductsPage);
