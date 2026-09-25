/**
 * Список переводов склада.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class StockTransfersPage extends PlatformPage {
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
            tr[data-id] { cursor: pointer; }
            tr[data-id]:hover td { background: var(--surface-hover); }
            .empty { padding: var(--space-8); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._transfers = this.useResource('stock/transfers');
    }

    async onRouteActive() {
        await this._transfers.load();
    }

    _open(event) {
        const id = event.currentTarget.getAttribute('data-id');
        if (typeof id === 'string' && id !== '') {
            this.navigate('stock_transfer', { transferId: id });
        }
    }

    render() {
        const items = this._transfers.items;
        return html`
            <div class="wrap">
                <h1>${this.t('transfers.title')}</h1>
                ${items.length === 0
                    ? html`<div class="empty">${this.t('transfers.empty')}</div>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.state')}</th>
                                <th>${this.t('fields.scheduled')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row) => html`
                                    <tr data-id=${row.transfer_id} @click=${this._open}>
                                        <td>${row.name}</td>
                                        <td>${row.state}</td>
                                        <td>${row.scheduled_at || ''}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-transfers-page', StockTransfersPage);
