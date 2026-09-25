/**
 * Локации склада: плоский список с usage и родителем (первый срез).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class StockLocationsPage extends PlatformPage {
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
            .empty { padding: var(--space-8); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._locations = this.useResource('stock/locations');
    }

    async onRouteActive() {
        await this._locations.load();
    }

    render() {
        const items = this._locations.items;
        return html`
            <div class="wrap">
                <h1>${this.t('locations.title')}</h1>
                ${items.length === 0
                    ? html`<div class="empty">${this.t('locations.empty')}</div>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.usage')}</th>
                                <th>${this.t('fields.parent')}</th>
                                <th>${this.t('fields.removal')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row) => html`
                                    <tr>
                                        <td>${row.name}</td>
                                        <td>${row.usage}</td>
                                        <td>${row.parent_id || ''}</td>
                                        <td>${row.removal_method}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-locations-page', StockLocationsPage);
