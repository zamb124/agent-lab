/**
 * Пульс склада: остатки со стоимостью и открытые переводы первого склада.
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/platform-empty-state.js';

interface PulseQuantRow {
    product_id?: unknown;
    location_id?: unknown;
    quantity?: unknown;
    reserved_quantity?: unknown;
    available_quantity?: unknown;
    avg_cost?: unknown;
    value?: unknown;
}

interface PulseTransferRow {
    name?: unknown;
    operation_code?: unknown;
    state?: unknown;
}

interface WarehousePulseResult {
    quants?: PulseQuantRow[];
    transfers?: PulseTransferRow[];
}

function isWarehousePulse(value: unknown): value is WarehousePulseResult {
    if (!isPlainRecord(value)) {
        return false;
    }
    if (value.quants !== undefined && !Array.isArray(value.quants)) {
        return false;
    }
    if (value.transfers !== undefined && !Array.isArray(value.transfers)) {
        return false;
    }
    return true;
}
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class StockHomePage extends PlatformPage {
    static i18nNamespace = 'stock';

    declare _warehouseId: string;
    private _warehouses: ResourceController;
    private _pulse: OpController;
    private _products: ResourceController;
    private _locations: ResourceController;

    static override properties = {
        _pulse: { state: true },
        _warehouseId: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
            h1 { margin: 0; font-size: var(--text-2xl); color: var(--text-primary); }
            .section { margin-top: var(--space-6); }
            .section-title {
                color: var(--text-tertiary); font-size: var(--text-xs);
                font-weight: var(--font-semibold); letter-spacing: var(--tracking-wide);
                text-transform: uppercase; margin-bottom: var(--space-2);
            }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td {
                padding: var(--space-2) var(--space-3); text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary);
            }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            .num { text-align: right; font-variant-numeric: tabular-nums; }
            platform-empty-state { margin-top: var(--space-8); }
            .actions { margin-top: var(--space-4); display: flex; gap: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._pulse = this.useOp('stock/warehouse_pulse');
        this._warehouseId = '';
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

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this._warehouseId === '') {
            const first = this._warehouses.items[0];
            if (first && typeof first.warehouse_id === 'string') {
                this._warehouseId = first.warehouse_id;
                void this._pulse.run({ warehouse_id: first.warehouse_id });
            }
        }
    }

    override render() {
        const rawPulse = this._pulse.lastResult;
        const pulse = isWarehousePulse(rawPulse) ? rawPulse : null;
        const names = this._nameMaps();
        return html`
            <div class="wrap">
                <h1>${this.t('home.title')}</h1>
                ${this._warehouses.loading || this._pulse.busy
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : !pulse
                    ? html`<platform-empty-state icon="box" title=${this.t('home.empty')}></platform-empty-state>`
                    : html`
                    <div class="section">
                        <div class="section-title">${this.t('home.quants')}</div>
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.product')}</th>
                                <th>${this.t('fields.location')}</th>
                                <th class="num">${this.t('fields.qty')}</th>
                                <th class="num">${this.t('fields.reserved')}</th>
                                <th class="num">${this.t('fields.available')}</th>
                                <th class="num">${this.t('fields.avg_cost')}</th>
                                <th class="num">${this.t('fields.value')}</th>
                            </tr></thead>
                            <tbody>
                                ${(pulse.quants === undefined ? [] : pulse.quants).map((row: PulseQuantRow) => html`
                                    <tr>
                                        <td>${names.products.get(String(row.product_id)) ?? row.product_id}</td>
                                        <td>${names.locations.get(String(row.location_id)) ?? row.location_id}</td>
                                        <td class="num">${row.quantity}</td>
                                        <td class="num">${row.reserved_quantity}</td>
                                        <td class="num">${row.available_quantity}</td>
                                        <td class="num">${row.avg_cost}</td>
                                        <td class="num">${row.value}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                    <div class="section">
                        <div class="section-title">${this.t('home.transfers')}</div>
                        <table>
                            <thead><tr>
                                <th>${this.t('fields.name')}</th>
                                <th>${this.t('fields.type')}</th>
                                <th>${this.t('fields.state')}</th>
                            </tr></thead>
                            <tbody>
                                ${(pulse.transfers === undefined ? [] : pulse.transfers).map((row: PulseTransferRow) => html`
                                    <tr>
                                        <td>${row.name}</td>
                                        <td>${row.operation_code}</td>
                                        <td>${row.state}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        `;
    }
}

customElements.define('stock-home-page', StockHomePage);
