/**
 * Список переводов склада.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-empty-state.js';

export class StockTransfersPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _transfers: ResourceController;

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
            tr[data-id] { cursor: pointer; }
            tr[data-id]:hover td { background: var(--surface-hover); }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this._transfers = this.useResource('stock/transfers');
    }

    async onRouteActive(): Promise<void> {
        await this._transfers.load();
    }

    private _open(event: Event) {
        const target = event.currentTarget;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const id = target.getAttribute('data-id');
        if (typeof id === 'string' && id !== '') {
            this.navigate('stock_transfer', { transferId: id });
        }
    }

    override render() {
        const items = this._transfers.items;
        return html`
            <div class="wrap">
                <h1>${this.t('transfers.title')}</h1>
                ${this._transfers.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : items.length === 0
                    ? html`<platform-empty-state icon="truck" title=${this.t('transfers.empty')}></platform-empty-state>`
                    : html`
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.state')}</th>
                                <th>${this.t('fields.scheduled')}</th>
                            </tr></thead>
                            <tbody>
                                ${items.map((row) => html`
                                    <tr data-id=${row.transfer_id === undefined || row.transfer_id === null ? '' : String(row.transfer_id)} @click=${(event: Event) => this._open(event)}>
                                        <td>${row.name}</td>
                                        <td>${row.state}</td>
                                        <td>${typeof row.scheduled_at === 'string' ? row.scheduled_at : ''}</td>
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
