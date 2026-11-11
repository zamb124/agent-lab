/**
 * Карточка «что я отсканировал» (`stock/tsd_entity` bottom sheet).
 *
 * Скан любой метки на рабочем столе открывает лист: товар — фото,
 * название, штрихкоды и остатки по ячейкам (грузятся асинхронно);
 * ячейка/контейнер — содержимое; накладная — вход в исполнение;
 * техника — привязка ресурса к оператору. Действия листа запускают
 * скан-сессии (`count` без документа, `scan/open` по документу).
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import { buildPlatformFileDownloadUrl } from '@platform/lib/utils/platform-files-url.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type {
    StockLocation,
    StockProductView,
    StockQuant,
    StockResource,
    StockScanOpenResponse,
    StockTransferDetail,
} from '@platform/lib/events/wire/stock.gen.js';
import type { StockTsdContextState } from '../../events/resources/stock-tsd.resource.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';

export class StockTsdEntitySheet extends PlatformBottomSheet {
    static i18nNamespace = 'stock_tsd';
    static bottomSheetKind = 'stock/tsd_entity';

    static override properties: PropertyDeclarations = {
        ...PlatformBottomSheet.properties,
        barcode: { type: String },
        entity_kind: { type: String },
        entity_id: { type: String },
        product_id: { type: String },
        warehouse_id: { type: String },
        _product: { state: true },
        _location: { state: true },
        _transfer: { state: true },
        _resource: { state: true },
        _containerQuants: { state: true },
        _failed: { state: true },
    };

    declare barcode: string;
    declare entity_kind: string;
    declare entity_id: string;
    declare product_id: string;
    declare warehouse_id: string;
    declare private _product: StockProductView | null;
    declare private _location: StockLocation | null;
    declare private _transfer: StockTransferDetail | null;
    declare private _resource: StockResource | null;
    declare private _containerQuants: StockQuant[];
    declare private _failed: boolean;

    private _contextSel: SelectController<StockTsdContextState>;
    private _quants: ControllerFor<'stock/quants'>;
    private _products: ControllerFor<'stock/products'>;
    private _productItem: ControllerFor<'stock/product_item'>;
    private _locationItem: ControllerFor<'stock/location_item'>;
    private _containerItem: ControllerFor<'stock/container_item'>;
    private _transferItem: ControllerFor<'stock/transfer_item'>;
    private _resourceLogin: ControllerFor<'stock/resource_login'>;
    private _scanOpen: ControllerFor<'stock/scan_open'>;
    private _session: ControllerFor<'stock/tsd_session'>;
    private _context: ControllerFor<'stock/tsd_context'>;

    static override styles = [
        PlatformBottomSheet.styles,
        css`
            .entity {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding-bottom: var(--space-2);
            }
            .head {
                display: flex;
                align-items: center;
                gap: var(--space-4);
            }
            .photo {
                width: 84px;
                height: 84px;
                border-radius: var(--radius-xl);
                background: var(--bg-secondary);
                object-fit: cover;
                flex-shrink: 0;
            }
            .photo-placeholder {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 84px;
                height: 84px;
                border-radius: var(--radius-xl);
                background: var(--bg-secondary);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }
            .head-body {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
            }
            .kind {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
            }
            .name {
                font-size: var(--text-xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                word-break: break-word;
            }
            .code {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                font-variant-numeric: tabular-nums;
            }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .quant-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .quant-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-xl);
                background: var(--bg-surface);
            }
            .quant-loc {
                flex: 1;
                min-width: 0;
                font-weight: var(--font-medium);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .quant-qty {
                font-weight: var(--font-bold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .quant-res {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .skeleton {
                height: 52px;
                border-radius: var(--radius-xl);
                background: linear-gradient(90deg, var(--bg-secondary) 25%, var(--bg-surface) 50%, var(--bg-secondary) 75%);
                background-size: 200% 100%;
                animation: tsd-shimmer 1.4s ease-in-out infinite;
            }
            @keyframes tsd-shimmer {
                from { background-position: 200% 0; }
                to { background-position: -200% 0; }
            }
            .actions {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .action {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                min-height: var(--tsd-touch-lg);
                border: none;
                border-radius: var(--radius-2xl);
                background: var(--accent);
                color: var(--text-inverse);
                font-size: var(--tsd-text-body);
                font-weight: var(--font-bold);
                cursor: pointer;
                -webkit-tap-highlight-color: transparent;
            }
            .action.secondary {
                border: 1px solid var(--border-default);
                background: var(--bg-surface);
                color: var(--text-primary);
            }
            .action:disabled { opacity: 0.6; }
            .empty {
                padding: var(--space-4);
                text-align: center;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this._contextSel = this.select((s) => s.stockTsdContext as StockTsdContextState);
        this._quants = this.useResource('stock/quants');
        this._products = this.useResource('stock/products');
        this._productItem = this.useOp('stock/product_item');
        this._locationItem = this.useOp('stock/location_item');
        this._containerItem = this.useOp('stock/container_item');
        this._transferItem = this.useOp('stock/transfer_item');
        this._resourceLogin = this.useOp('stock/resource_login');
        this._scanOpen = this.useOp('stock/scan_open');
        this._session = this.useSlice('stock/tsd_session');
        this._context = this.useSlice('stock/tsd_context');
        this._product = null;
        this._location = null;
        this._transfer = null;
        this._resource = null;
        this._containerQuants = [];
        this._failed = false;
    }

    override updated(changed: PropertyValues): void {
        if (changed.has('entity_id') && this.entity_id !== '') {
            void this._load();
        }
    }

    private async _load(): Promise<void> {
        this._product = null;
        this._location = null;
        this._transfer = null;
        this._resource = null;
        this._containerQuants = [];
        this._failed = false;
        const kind = this.entity_kind;
        try {
            if (kind === 'product' || kind === 'packaging' || kind === 'lot') {
                const productId = this.product_id !== '' ? this.product_id : this.entity_id;
                const product = await this._productItem.run({ product_id: productId });
                this._product = product;
                this._loadQuants({ product_id: productId });
            } else if (kind === 'location') {
                this._location = await this._locationItem.run({ location_id: this.entity_id });
                this._loadQuants({ location_id: this.entity_id });
            } else if (kind === 'container') {
                const contents = await this._containerItem.run({ container_id: this.entity_id });
                this._location = contents === null ? null : contents.container;
                this._containerQuants = contents === null ? [] : contents.quants;
            } else if (kind === 'document') {
                this._transfer = await this._transferItem.run({ transfer_id: this.entity_id });
            }
        } catch {
            this._failed = true;
        }
    }

    private _loadQuants(query: Record<string, unknown>): void {
        this._quants.load(query);
    }

    private _locationName(locationId: string): string {
        if (this._location !== null && this._location.location_id === locationId) {
            return this._location.complete_name ?? this._location.name;
        }
        return locationId;
    }

    private _productName(productId: string): string {
        if (this._product !== null && this._product.product_id === productId) {
            return this._product.name;
        }
        const row = this._products.items.find((item) => item.product_id === productId);
        return row === undefined ? productId : row.name;
    }

    private _renderQuantRow(quant: StockQuant): TemplateResult {
        const qty = quant.quantity ?? 0;
        const reserved = quant.reserved_quantity ?? 0;
        return html`
            <div class="quant-row">
                <span class="quant-loc">
                    ${this.entity_kind === 'product' || this.entity_kind === 'packaging' || this.entity_kind === 'lot'
                        ? this._locationName(quant.location_id)
                        : this._productName(quant.product_id)}
                </span>
                <span class="quant-res">${Number(reserved) > 0 ? this.t('entity.reserved', { qty: String(reserved) }) : ''}</span>
                <span class="quant-qty">${qty}</span>
            </div>
        `;
    }

    private _renderQuants(): TemplateResult | string {
        if (!['product', 'packaging', 'lot', 'location', 'container'].includes(this.entity_kind)) return '';
        const items = this.entity_kind === 'container' ? this._containerQuants : this._quants.items.filter((q) => {
            if (this.entity_kind === 'location' || this.entity_kind === 'container') {
                return q.location_id === this.entity_id;
            }
            const productId = this.product_id !== '' ? this.product_id : this.entity_id;
            return q.product_id === productId;
        });
        return html`
            <div class="section-title">${this.t('entity.stock_title')}</div>
            ${this._quants.loading ? html`
                <div class="quant-list">
                    <div class="skeleton"></div>
                    <div class="skeleton"></div>
                </div>
            ` : items.length === 0 ? html`
                <div class="empty">${this.t('entity.stock_empty')}</div>
            ` : html`
                <div class="quant-list">
                    ${items.map((quant) => this._renderQuantRow(quant))}
                </div>
            `}
        `;
    }

    private async _startCount(): Promise<void> {
        const locationId = this.entity_kind === 'location' || this.entity_kind === 'container' ? this.entity_id : '';
        this._session.stepApplied({
            context: { flow: 'count', step: 'start', source_id: locationId === '' ? null : locationId },
            resolution: null,
            barcode: '',
            error: null,
            hint: '',
            expected: null,
        });
        this.requestPlatformClose();
    }

    private async _openDocument(): Promise<void> {
        const warehouseId = this._contextSel.value.warehouse_id;
        const opened: StockScanOpenResponse | null = await this._scanOpen.run({
            warehouse_id: warehouseId,
            move_id: null,
            transfer_id: this.entity_id,
        });
        if (opened === null) return;
        this._session.runOpened({
            context: opened.context,
            move_id: opened.move_id,
            expected: opened.expected ?? null,
        });
        this.requestPlatformClose();
    }

    private async _bindResource(): Promise<void> {
        const warehouseId = this._contextSel.value.warehouse_id;
        const resource = await this._resourceLogin.run({
            warehouse_id: warehouseId,
            barcode: this.barcode,
            resource_id: null,
            idempotency_key: null,
        });
        if (resource === null) return;
        this._resource = resource;
        this._context.setResource({ resource_id: resource.resource_id, resource_code: resource.code });
        this.toast('entity.resource_bound', { type: 'success', vars: { code: resource.code } });
        this.requestPlatformClose();
    }

    private _renderActions(): TemplateResult | string {
        const kind = this.entity_kind;
        if (kind === 'document') {
            return html`
                <div class="actions">
                    <button class="action" ?disabled=${this._scanOpen.busy} @click=${() => void this._openDocument()}>
                        ${this._scanOpen.busy ? html`<platform-spinner size="s"></platform-spinner>` : html`<platform-icon name="play" size="20"></platform-icon>`}
                        ${this.t('entity.action_open_document')}
                    </button>
                </div>
            `;
        }
        if (kind === 'resource') {
            return html`
                <div class="actions">
                    <button class="action" ?disabled=${this._resourceLogin.busy} @click=${() => void this._bindResource()}>
                        ${this._resourceLogin.busy ? html`<platform-spinner size="s"></platform-spinner>` : html`<platform-icon name="link" size="20"></platform-icon>`}
                        ${this.t('entity.action_bind_resource')}
                    </button>
                </div>
            `;
        }
        if (['product', 'packaging', 'lot', 'location', 'container'].includes(kind)) {
            return html`
                <div class="actions">
                    <button class="action" @click=${() => void this._startCount()}>
                        <platform-icon name="clipboard-list" size="20"></platform-icon>
                        ${this.t('entity.action_count')}
                    </button>
                </div>
            `;
        }
        return '';
    }

    override renderBody(): TemplateResult {
        const kind = this.entity_kind;
        const product = this._product;
        const photoId = product !== null && product.image_file_ids.length > 0 ? (product.image_file_ids[0] ?? null) : null;
        const title = product !== null
            ? product.name
            : this._location !== null
              ? (this._location.complete_name ?? this._location.name)
              : this._transfer !== null
                ? this._transfer.transfer.name
                : this._resource !== null
                  ? this._resource.code
                  : this.barcode;
        const meta = product !== null
            ? (product.sku ?? this.barcode)
            : this._transfer !== null
              ? this.t('entity.document_meta', { lines: String(this._transfer.lines.length) })
              : this.barcode;
        return html`
            <div class="entity">
                <div class="head">
                    ${photoId !== null
                        ? html`<img class="photo" src=${buildPlatformFileDownloadUrl(photoId)} alt="">`
                        : html`<div class="photo-placeholder"><platform-icon name=${this._kindIcon(kind)} size="34"></platform-icon></div>`}
                    <div class="head-body">
                        <span class="kind">${this.t(`entity.kind_${kind}`)}</span>
                        <span class="name">${title}</span>
                        <span class="code">${meta}</span>
                    </div>
                </div>
                ${this._failed ? html`<div class="empty">${this.t('entity.load_failed')}</div>` : ''}
                ${this._renderQuants()}
                ${this._renderActions()}
            </div>
        `;
    }

    private _kindIcon(kind: string): string {
        switch (kind) {
            case 'product': return 'package';
            case 'packaging': return 'boxes';
            case 'lot': return 'layers';
            case 'serial': return 'hash';
            case 'location': return 'map-pin';
            case 'container': return 'box';
            case 'document': return 'file-text';
            case 'resource': return 'truck';
            default: return 'qr-code';
        }
    }
}

customElements.define('stock-tsd-entity-sheet', StockTsdEntitySheet);
registerBottomSheetKind(StockTsdEntitySheet.bottomSheetKind, 'stock-tsd-entity-sheet');
