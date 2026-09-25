/**
 * Карточка перевода: строки движений и действия confirm/assign/validate/cancel.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-button.js';

export class StockTransferPage extends PlatformPage {
    static i18nNamespace = 'stock';

    static properties = {
        transferId: { attribute: 'transfer-id' },
        _detail: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
            h1 { margin: 0; font-size: var(--text-2xl); color: var(--text-primary); }
            .state { color: var(--text-secondary); margin: var(--space-2) 0 var(--space-4); }
            .actions { display: flex; gap: var(--space-2); margin-bottom: var(--space-4); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td {
                padding: var(--space-2) var(--space-3); text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary);
            }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            .num { text-align: right; font-variant-numeric: tabular-nums; }
        `,
    ];

    constructor() {
        super();
        this.transferId = '';
        this._item = this.useOp('stock/transfer_item');
        this._confirm = this.useOp('stock/transfer_confirm');
        this._assign = this.useOp('stock/transfer_assign');
        this._validate = this.useOp('stock/transfer_validate');
        this._cancel = this.useOp('stock/transfer_cancel');
    }

    async onRouteActive() {
        await this._reload();
    }

    async _reload() {
        if (this.transferId === '') return;
        this._detail = await this._item.run({ transfer_id: this.transferId });
    }

    async _act(op, event) {
        event.preventDefault();
        await op.run({ transfer_id: this.transferId });
        await this._reload();
    }

    render() {
        const detail = this._detail;
        if (!detail || !detail.transfer) {
            return html`<div class="wrap"><h1>${this.t('transfer.loading')}</h1></div>`;
        }
        const transfer = detail.transfer;
        const lines = detail.lines || [];
        return html`
            <div class="wrap">
                <h1>${transfer.name}</h1>
                <div class="state">${this.t('fields.state')}: ${transfer.state}</div>
                <div class="actions">
                    <platform-button @click=${(e) => this._act(this._confirm, e)}>${this.t('transfer.confirm')}</platform-button>
                    <platform-button @click=${(e) => this._act(this._assign, e)}>${this.t('transfer.assign')}</platform-button>
                    <platform-button @click=${(e) => this._act(this._validate, e)}>${this.t('transfer.validate')}</platform-button>
                    <platform-button @click=${(e) => this._act(this._cancel, e)}>${this.t('transfer.cancel')}</platform-button>
                </div>
                <table>
                    <thead><tr>
                        <th>${this.t('fields.product')}</th>
                        <th>${this.t('fields.from')}</th>
                        <th>${this.t('fields.to')}</th>
                        <th class="num">${this.t('fields.reserved')}</th>
                        <th class="num">${this.t('fields.done_qty')}</th>
                    </tr></thead>
                    <tbody>
                        ${lines.map((line) => html`
                            <tr>
                                <td>${line.product_id}</td>
                                <td>${line.location_id}</td>
                                <td>${line.location_dest_id}</td>
                                <td class="num">${line.quantity}</td>
                                <td class="num">${line.done_quantity}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }
}

customElements.define('stock-transfer-page', StockTransferPage);
