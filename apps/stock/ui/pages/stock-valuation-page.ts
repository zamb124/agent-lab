/**
 * Журнал оценки: append-only лента `StockValueLayer` (аудит).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-empty-state.js';

export class StockValuationPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _layers: ResourceController;

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1200px; margin: 0 auto; padding: var(--space-6); }
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
        this._layers = this.useResource('stock/valuation', { autoload: true });
    }


    override render() {
        const items = this._layers.items;
        return html`
            <div class="wrap">
                <h1>${this.t('valuation.title')}</h1>
                ${this._layers.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                    ? html`<platform-empty-state icon="chart" title=${this.t('valuation.empty')}></platform-empty-state>`
                    : html`
                        <table>
                            <thead><tr>
                                <th class="num">${this.t('fields.entry_no')}</th>
                                <th>${this.t('fields.kind')}</th>
                                <th>${this.t('fields.product')}</th>
                                <th class="num">${this.t('fields.qty')}</th>
                                <th class="num">${this.t('fields.unit_cost')}</th>
                                <th class="num">${this.t('fields.value')}</th>
                                <th class="num">${this.t('fields.qty_after')}</th>
                                <th class="num">${this.t('fields.value_after')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row: Record<string, unknown>) => html`
                                    <tr>
                                        <td class="num">${row.entry_no}</td>
                                        <td>${row.entry_kind}</td>
                                        <td>${row.product_id}</td>
                                        <td class="num">${row.quantity}</td>
                                        <td class="num">${row.unit_cost}</td>
                                        <td class="num">${row.value}</td>
                                        <td class="num">${row.qty_after}</td>
                                        <td class="num">${row.value_after}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-valuation-page', StockValuationPage);
