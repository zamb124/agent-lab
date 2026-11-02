/**
 * Заказы магазина: доска по статусам, действия перехода по матрице backend'а.
 * Список живёт в `lastResult` опа `shop/orders_list`: push `shop/order/*`
 * перезапускает его в фабрике — доска обновляется realtime без ручного state.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import type { ShopHeadRow } from '../components/shop-page-head.js';

const COLUMNS = ['new', 'accepted', 'preparing', 'delivering', 'done', 'cancelled'] as const;
const NEXT: Record<string, string[]> = {
    new: ['accepted', 'cancelled'],
    accepted: ['preparing', 'cancelled'],
    preparing: ['delivering', 'done', 'cancelled'],
    delivering: ['done'],
};

interface OrderItemRow {
    product_id: string;
    name: string;
    qty: number;
    price_minor: number;
}

interface OrderRow {
    shop_order_id: string;
    public_code: string;
    status: string;
    customer_name: string;
    customer_phone: string;
    delivery_type: string;
    table_label: string;
    address: string;
    comment: string;
    items_total_minor: number;
    delivery_fee_minor: number;
    total_minor: number;
    currency: string;
    created_at?: string;
    items: OrderItemRow[];
}

interface OrdersPage {
    items?: OrderRow[];
}

export class ShopOrdersPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _listOp: OpController;
    private _statusOp: OpController;
    private _locale: SelectController<string>;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .wrap { height: 100%; display: flex; flex-direction: column; padding: var(--space-5) var(--space-6) 0; }
            .board {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: repeat(6, minmax(210px, 1fr));
                gap: var(--space-3);
                overflow-x: auto;
                padding-bottom: var(--space-6);
            }
            .col {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow-y: auto;
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--text-primary) 3%, transparent);
                padding: var(--space-2);
            }
            .col-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                padding: var(--space-1) var(--space-2);
            }
            .col-title.new { color: var(--color-primary, var(--text-secondary)); }
            .card {
                background: var(--bg-surface);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                box-shadow: var(--shadow-xs, 0 1px 2px rgb(0 0 0 / 0.05));
            }
            .card-top { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }
            .code { font-weight: var(--font-semibold); color: var(--text-primary); font-variant-numeric: tabular-nums; }
            .time { font-size: var(--text-2xs, 10px); color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
            .meta { font-size: var(--text-xs); color: var(--text-tertiary); }
            .comment { font-size: var(--text-xs); color: var(--text-secondary); font-style: italic; }
            .items { font-size: var(--text-xs); color: var(--text-secondary); }
            .items div { display: flex; justify-content: space-between; gap: var(--space-2); }
            .totals { display: flex; flex-direction: column; gap: 2px; border-top: 1px solid var(--glass-border-subtle); padding-top: var(--space-2); }
            .fee { font-size: var(--text-2xs, 10px); color: var(--text-tertiary); display: flex; justify-content: space-between; }
            .total { font-weight: var(--font-semibold); color: var(--text-primary); font-variant-numeric: tabular-nums; display: flex; justify-content: space-between; }
            .card-actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            @media (max-width: 1100px) {
                .board { grid-template-columns: repeat(6, 230px); }
            }
        `,
    ];

    constructor() {
        super();
        this._shops = this.useResource('shop/shops');
        this._listOp = this.useOp('shop/orders_list');
        this._statusOp = this.useOp('shop/order_set_status');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._loadOrders();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const prevShopId = changed.get('shopId');
        if (typeof prevShopId === 'string' && prevShopId !== this.shopId) void this._loadOrders();
    }

    private async _loadOrders(): Promise<void> {
        if (this.shopId === '') return;
        await Promise.all([
            this._listOp.run({ shop_id: this.shopId, limit: 200 }),
            this._shops.load(),
        ]);
    }

    private _shop(): ShopHeadRow | null {
        const row = this._shops.items.find((s) => (s as { shop_id?: string }).shop_id === this.shopId);
        return shopHeadRow(row);
    }

    private _orders(): OrderRow[] {
        const result = this._listOp.lastResult as OrdersPage | null;
        return Array.isArray(result?.items) ? result.items : [];
    }

    private _money(minor: number, currency: string): string {
        return `${formatPlatformNumber(minor / 100, this._locale.value, { minimumFractionDigits: 0, maximumFractionDigits: 2 })} ${currency}`;
    }

    private _time(iso: string | undefined): string {
        if (iso === undefined || iso === '') return '';
        const date = new Date(iso);
        return Number.isNaN(date.getTime()) ? '' : formatPlatformDateTime(date, this._locale.value);
    }

    private async _setStatus(order: OrderRow, status: string) {
        await this._statusOp.run({
            shop_id: this.shopId,
            shop_order_id: order.shop_order_id,
            status,
        });
    }

    private _card(order: OrderRow) {
        const fee = order.delivery_fee_minor;
        return html`
            <div class="card">
                <div class="card-top">
                    <span class="code">#${order.public_code}</span>
                    <span class="time">${this._time(order.created_at)}</span>
                </div>
                <span class="meta">${order.customer_phone === '' ? order.customer_name : `${order.customer_name} · ${order.customer_phone}`}</span>
                <span class="meta">
                    ${this.t(`orders.delivery.${order.delivery_type}`)}${order.delivery_type === 'onsite' && order.table_label !== '' ? ` · ${order.table_label}` : ''}${order.delivery_type === 'delivery' && order.address !== '' ? ` · ${order.address}` : ''}
                </span>
                ${order.comment === '' ? nothing : html`<span class="comment">«${order.comment}»</span>`}
                <div class="items">
                    ${order.items.map((item) => html`
                        <div><span>${item.qty}× ${item.name}</span><span>${this._money(item.price_minor * item.qty, order.currency)}</span></div>
                    `)}
                </div>
                <div class="totals">
                    ${fee === 0 ? nothing : html`<span class="fee"><span>${this.t('orders.fee')}</span><span>${this._money(fee, order.currency)}</span></span>`}
                    <span class="total"><span>${this.t('orders.total')}</span><span>${this._money(order.total_minor, order.currency)}</span></span>
                </div>
                <div class="card-actions">
                    ${(NEXT[order.status] ?? [])
                        .filter((next) => !(order.delivery_type === 'onsite' && next === 'delivering'))
                        .map((next) => html`
                        <platform-button
                            size="sm"
                            variant=${next === 'cancelled' ? 'ghost-danger' : 'primary'}
                            ?loading=${this._statusOp.busy}
                            @click=${() => this._setStatus(order, next)}
                        >${this.t(`orders.action.${next}`)}</platform-button>
                        `)}
                </div>
            </div>
        `;
    }

    override render() {
        const orders = this._orders();
        return html`
            <div class="wrap">
                <shop-page-head
                    .shop=${this._shop()}
                    shop-id=${this.shopId}
                    section=${this.t('routes.shop_orders')}
                ></shop-page-head>
                ${this._listOp.busy && orders.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : orders.length === 0
                    ? html`<platform-empty-state icon="scroll-text" title=${this.t('orders.empty')}></platform-empty-state>`
                    : html`
                        <div class="board">
                            ${COLUMNS.map((col) => {
                                const rows = orders.filter((o) => o.status === col);
                                return html`
                                    <div class="col">
                                        <div class="col-title ${col}">${this.t(`orders.status.${col}`)} · ${rows.length}</div>
                                        ${rows.map((o) => this._card(o))}
                                    </div>
                                `;
                            })}
                        </div>
                    `}
            </div>
        `;
    }
}

customElements.define('shop-orders-page', ShopOrdersPage);
