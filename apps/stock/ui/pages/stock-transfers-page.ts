/**
 * Список переводов склада.
 */

import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-empty-state.js';
import { stockPageStyles } from '../styles/stock-page.styles.js';

export class StockTransfersPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _transfers: ResourceController;

    static override styles = [
        PlatformPage.styles,
        stockPageStyles,
    ];

    constructor() {
        super();
        this._transfers = this.useResource('stock/transfers', { autoload: true });
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
                <page-header title=${this.t('transfers.title')} dense></page-header>
                ${this._transfers.loading
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : html`
                        <div class="table-card"><div class="scroll">
                        ${items.length === 0
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
                                            <tr class="clickable" data-id=${row.transfer_id === undefined || row.transfer_id === null ? '' : String(row.transfer_id)} @click=${(event: Event) => this._open(event)}>
                                                <td>${row.name}</td>
                                                <td>${row.state}</td>
                                                <td>${typeof row.scheduled_at === 'string' ? row.scheduled_at : ''}</td>
                                            </tr>
                                        `)}
                                    </tbody>
                                </table>
                            `}
                        </div></div>
                    `}
            </div>
        `;
    }
}

customElements.define('stock-transfers-page', StockTransfersPage);
