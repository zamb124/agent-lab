/**
 * Номенклатура склада: продукты и метод оценки карточки.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-button.js';

export class StockProductsPage extends PlatformPage {
    static i18nNamespace = 'stock';

    static styles = [
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
            .empty { padding: var(--space-8); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._products = this.useResource('stock/products');
    }

    async onRouteActive() {
        await this._products.load();
    }

    render() {
        const items = this._products.items;
        return html`
            <div class="wrap">
                <h1>${this.t('products.title')}</h1>
                ${items.length === 0
                    ? html`<div class="empty">${this.t('products.empty')}</div>`
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
