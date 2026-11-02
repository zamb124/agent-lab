/**
 * Номенклатура склада: продукты и метод оценки карточки.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';

export class StockProductsPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _products: ResourceController;

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
            h1 { margin: 0 0 var(--space-4); font-size: var(--text-2xl); color: var(--text-primary); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td {
                padding: var(--space-2) var(--space-3); text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary);
            }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            .num { text-align: right; font-variant-numeric: tabular-nums; }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this._products = this.useResource('stock/products', { autoload: true });
    }


    override render() {
        const items = this._products.items;
        return html`
            <div class="wrap">
                <h1>${this.t('products.title')}</h1>
                ${this._products.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                    ? html`<platform-empty-state icon="tag" title=${this.t('products.empty')}></platform-empty-state>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.sku')}</th>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.valuation_method')}</th>
                                <th class="num">${this.t('fields.standard_price')}</th>
                                <th>${this.t('fields.tracking')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row) => html`
                                    <tr>
                                        <td>${row.sku}</td>
                                        <td>${row.name}</td>
                                        <td>${row.valuation_method}</td>
                                        <td class="num">${row.standard_price}</td>
                                        <td>${row.tracking}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-products-page', StockProductsPage);
