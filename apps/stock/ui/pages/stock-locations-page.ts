/**
 * Локации склада: плоский список с usage и родителем (первый срез).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-empty-state.js';

export class StockLocationsPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _locations: ResourceController;

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
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this._locations = this.useResource('stock/locations', { autoload: true });
    }


    override render() {
        const items = this._locations.items;
        const names = new Map<string, string>();
        for (const row of items as { location_id?: unknown; name?: unknown }[]) {
            if (typeof row.location_id === 'string' && typeof row.name === 'string') {
                names.set(row.location_id, row.name);
            }
        }
        const nameOf = (id: unknown): unknown =>
            typeof id === 'string' ? names.get(id) ?? id : '';
        return html`
            <div class="wrap">
                <h1>${this.t('locations.title')}</h1>
                ${this._locations.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                    ? html`<platform-empty-state icon="pin" title=${this.t('locations.empty')}></platform-empty-state>`
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
                                        <td>${nameOf(row.parent_id)}</td>
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
