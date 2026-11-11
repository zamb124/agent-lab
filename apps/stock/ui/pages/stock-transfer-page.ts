/**
 * Карточка перевода: строки движений и действия confirm/assign/validate/cancel.
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

interface TransferDetail {
    transfer?: { name?: unknown; state?: unknown };
    lines?: {
        product_id?: unknown;
        location_id?: unknown;
        location_dest_id?: unknown;
        quantity?: unknown;
        done_quantity?: unknown;
    }[];
}

function isTransferDetail(value: unknown): value is TransferDetail {
    return isPlainRecord(value);
}
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';

export class StockTransferPage extends PlatformPage {
    static i18nNamespace = 'stock';

    declare transferId: string;
    declare _detail: TransferDetail | null;
    private _item: OpController;
    private _confirm: OpController;
    private _assign: OpController;
    private _validate: OpController;
    private _cancel: OpController;
    private _products: ResourceController;
    private _locations: ResourceController;

    static override properties = {
        transferId: { attribute: 'transfer-id' },
        _detail: { state: true },
    };

    static override styles = [
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
        this._detail = null;
        this._item = this.useOp('stock/transfer_item');
        this._confirm = this.useOp('stock/transfer_confirm');
        this._assign = this.useOp('stock/transfer_assign');
        this._validate = this.useOp('stock/transfer_validate');
        this._cancel = this.useOp('stock/transfer_cancel');
        this._products = this.useResource('stock/products', { autoload: true });
        this._locations = this.useResource('stock/locations', { autoload: true });
    }

    /** Имена по справочникам; у внешних псевдо-локаций (partner:*) записи нет — показываем id. */
    private _nameMaps(): { products: Map<string, string>; locations: Map<string, string> } {
        const products = new Map<string, string>();
        for (const row of this._products.items as { product_id?: unknown; name?: unknown }[]) {
            if (typeof row.product_id === 'string' && typeof row.name === 'string') {
                products.set(row.product_id, row.name);
            }
        }
        const locations = new Map<string, string>();
        for (const row of this._locations.items as { location_id?: unknown; name?: unknown }[]) {
            if (typeof row.location_id === 'string' && typeof row.name === 'string') {
                locations.set(row.location_id, row.name);
            }
        }
        return { products, locations };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._reload();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const prevTransferId = changed.get('transferId');
        if (typeof prevTransferId === 'string' && prevTransferId !== this.transferId) void this._reload();
    }

    private async _reload(): Promise<void> {
        if (this.transferId === '') return;
        const detail = await this._item.run({ transfer_id: this.transferId });
        this._detail = isTransferDetail(detail) ? detail : null;
    }

    private async _act(op: OpController, event: Event): Promise<void> {
        event.preventDefault();
        await op.run({ transfer_id: this.transferId });
        await this._reload();
    }

    override render() {
        const detail = this._detail;
        if (!detail || !detail.transfer) {
            return html`<div class="wrap"><platform-empty-state loading></platform-empty-state></div>`;
        }
        const transfer = detail.transfer;
        const lines: NonNullable<TransferDetail['lines']> = detail.lines === undefined ? [] : detail.lines;
        const names = this._nameMaps();
        return html`
            <div class="wrap">
                <h1>${transfer.name}</h1>
                <div class="state">${this.t('fields.state')}: ${transfer.state}</div>
                <div class="actions">
                    <platform-button @click=${(e: Event) => this._act(this._confirm, e)}>${this.t('transfer.confirm')}</platform-button>
                    <platform-button @click=${(e: Event) => this._act(this._assign, e)}>${this.t('transfer.assign')}</platform-button>
                    <platform-button @click=${(e: Event) => this._act(this._validate, e)}>${this.t('transfer.validate')}</platform-button>
                    <platform-button @click=${(e: Event) => this._act(this._cancel, e)}>${this.t('transfer.cancel')}</platform-button>
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
                                <td>${names.products.get(String(line.product_id)) ?? line.product_id}</td>
                                <td>${names.locations.get(String(line.location_id)) ?? line.location_id}</td>
                                <td>${names.locations.get(String(line.location_dest_id)) ?? line.location_dest_id}</td>
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
