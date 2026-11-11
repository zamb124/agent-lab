/**
 * Создание/редактирование товара склада.
 *
 * Create — `stock/product_create` (мастер-карта каталога + складской
 * фасет одной командой). Edit — базовые поля (имя/SKU/вес/объём) идут в
 * мастер-карту `stock/catalog_product_update` (общие для всех сервисов),
 * складская политика и набор штрихкодов — `stock/product_update`.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { StockProductView } from '@platform/lib/events/wire/stock.gen.js';
import type { CatalogProductPick } from '@platform/lib/catalog/product-picker.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/catalog/product-card.js';

function _str(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

const VALUATION_METHODS = ['standard', 'average', 'fifo', 'unvalued'];
const TRACKING_KINDS = ['none', 'lot', 'serial'];

export class StockProductModal extends PlatformModal {
    static modalKind = 'stock.product';
    static i18nNamespace = 'stock';

    declare product: StockProductView | null;
    declare attachProduct: CatalogProductPick | null;
    declare initialName: string;
    declare onSaved: (() => void) | null;

    private _uomsOp: OpController;
    private _createOp: OpController;
    private _updateOp: OpController;
    private _catalogUpdateOp: OpController;

    declare _name: string;
    declare _sku: string;
    declare _uomId: string;
    declare _valuationMethod: string;
    declare _standardPrice: string;
    declare _tracking: string;
    declare _isStorable: boolean;
    declare _isActive: boolean;
    declare _category: string;
    declare _barcodes: string[];
    declare _weight: string;
    declare _volume: string;

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        product: { attribute: false },
        attachProduct: { attribute: false },
        initialName: { type: String, attribute: 'initial-name' },
        onSaved: { attribute: false },
        _name: { state: true },
        _sku: { state: true },
        _uomId: { state: true },
        _valuationMethod: { state: true },
        _standardPrice: { state: true },
        _tracking: { state: true },
        _isStorable: { state: true },
        _isActive: { state: true },
        _category: { state: true },
        _barcodes: { state: true },
        _weight: { state: true },
        _volume: { state: true },
    };

    static override styles: CSSResultGroup = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-3); }
            .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.product = null;
        this.attachProduct = null;
        this.initialName = '';
        this.onSaved = null;
        this._uomsOp = this.useOp('stock/uoms_list');
        this._createOp = this.useOp('stock/product_create');
        this._updateOp = this.useOp('stock/product_update');
        this._catalogUpdateOp = this.useOp('stock/catalog_product_update');
        this._name = '';
        this._sku = '';
        this._uomId = '';
        this._valuationMethod = 'fifo';
        this._standardPrice = '0';
        this._tracking = 'none';
        this._isStorable = true;
        this._isActive = true;
        this._category = '';
        this._barcodes = [];
        this._weight = '';
        this._volume = '';
    }

    private get _editing(): boolean {
        return this.product !== null;
    }

    private get _attaching(): boolean {
        return this.attachProduct !== null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._uomsOp.run({});
        if (this._attaching && this.attachProduct !== null) {
            this._name = this.attachProduct.name;
            this._sku = this.attachProduct.sku;
        } else if (this.initialName !== '') {
            this._name = this.initialName;
        }
        const p = this.product;
        if (p !== null) {
            this._name = p.name;
            this._sku = typeof p.sku === 'string' ? p.sku : '';
            this._uomId = p.uom_id;
            this._valuationMethod = p.valuation_method;
            this._standardPrice = String(p.standard_price ?? '0');
            this._tracking = p.tracking;
            this._isStorable = p.is_storable !== false;
            this._isActive = p.is_active !== false;
            this._category = typeof p.category === 'string' ? p.category : '';
            this._barcodes = Array.isArray(p.barcodes) ? [...p.barcodes] : [];
            this._weight = p.weight !== null && p.weight !== undefined ? String(p.weight) : '';
            this._volume = p.volume !== null && p.volume !== undefined ? String(p.volume) : '';
        }
    }

    private get _saving(): boolean {
        return this._createOp.busy || this._updateOp.busy || this._catalogUpdateOp.busy;
    }

    private _valid(): boolean {
        return this._name.trim() !== '' && (this._editing || this._uomId !== '');
    }

    private _uomOptions(): { values: { value: string; label: string }[] } {
        const result = this._uomsOp.lastResult;
        const items = isPlainRecord(result) && Array.isArray(result.items) ? result.items : [];
        const values: { value: string; label: string }[] = [];
        for (const item of items) {
            if (isPlainRecord(item) && typeof item.uom_id === 'string' && item.product_id === undefined) {
                values.push({ value: item.uom_id, label: typeof item.name === 'string' ? item.name : item.uom_id });
            }
        }
        return { values };
    }

    private _num(value: string): number | null {
        const n = Number(value.replace(',', '.'));
        return value.trim() !== '' && Number.isFinite(n) ? n : null;
    }

    private async _save(): Promise<void> {
        if (!this._valid() || this._saving) return;
        const barcodes = this._barcodes.map((b) => b.trim()).filter((b) => b !== '');
        let ok = true;
        if (this._editing && this.product !== null) {
            const p = this.product;
            const base: Record<string, unknown> = { product_id: p.product_id };
            if (this._name.trim() !== p.name) base.name = this._name.trim();
            const sku = this._sku.trim();
            if (sku !== (typeof p.sku === 'string' ? p.sku : '')) base.sku = sku;
            const weight = this._num(this._weight);
            if (weight !== (typeof p.weight === 'number' || typeof p.weight === 'string' ? Number(p.weight) : null)) base.weight = weight;
            const volume = this._num(this._volume);
            if (volume !== (typeof p.volume === 'number' || typeof p.volume === 'string' ? Number(p.volume) : null)) base.volume = volume;
            if (Object.keys(base).length > 1) {
                ok = (await this._catalogUpdateOp.run(base)) !== null;
            }
            const facet: Record<string, unknown> = { product_id: p.product_id };
            if (this._valuationMethod !== p.valuation_method) facet.valuation_method = this._valuationMethod;
            const price = this._num(this._standardPrice) ?? 0;
            if (String(price) !== String(p.standard_price)) facet.standard_price = String(price);
            if (this._tracking !== p.tracking) facet.tracking = this._tracking;
            if (this._isStorable !== (p.is_storable !== false)) facet.is_storable = this._isStorable;
            if (this._isActive !== (p.is_active !== false)) facet.is_active = this._isActive;
            if (this._category !== (typeof p.category === 'string' ? p.category : '')) facet.category = this._category;
            const prev = Array.isArray(p.barcodes) ? p.barcodes : [];
            if (JSON.stringify(barcodes) !== JSON.stringify(prev)) facet.barcodes = barcodes;
            if (ok && Object.keys(facet).length > 1) {
                ok = (await this._updateOp.run(facet)) !== null;
            }
        } else {
            ok = (await this._createOp.run({
                product_id: this._attaching && this.attachProduct !== null ? this.attachProduct.product_id : null,
                name: this._name.trim(),
                sku: this._sku.trim() === '' ? null : this._sku.trim(),
                uom_id: this._uomId,
                valuation_method: this._valuationMethod,
                standard_price: String(this._num(this._standardPrice) ?? 0),
                tracking: this._tracking,
                is_storable: this._isStorable,
                category: this._category,
                barcodes,
                weight: this._num(this._weight),
                volume: this._num(this._volume),
            })) !== null;
        }
        if (!ok) return;
        this.onSaved?.();
        this.close();
    }

    override renderHeader() {
        return this.t(this._editing ? 'modal.product_edit' : 'modal.product_new');
    }

    override renderBody(): TemplateResult {
        const set = (fn: (v: string) => void) => (e: CustomEvent<{ value?: unknown }>) => fn(_str(e));
        const enumConfig = (options: string[]) => ({ values: options.map((o) => ({ value: o, label: o })) });
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); void this._save(); }}>
                ${this._attaching && this.attachProduct !== null ? html`
                    <platform-catalog-product-card
                        .name=${this.attachProduct.name}
                        .sku=${this.attachProduct.sku}
                    ></platform-catalog-product-card>
                ` : html`
                    <platform-field type="string" mode="edit" .label=${this.t('fields.name')}
                        .value=${this._name} required @change=${set((v) => { this._name = v; })}></platform-field>
                    <div class="row2">
                        <platform-field type="string" mode="edit" .label=${this.t('fields.sku')}
                            .value=${this._sku} @change=${set((v) => { this._sku = v; })}></platform-field>
                        <platform-field type="enum" mode="edit" .label=${this.t('fields.uom')}
                            .value=${this._uomId} .config=${this._uomOptions()} ?required=${!this._editing}
                            ?disabled=${this._editing}
                            @change=${set((v) => { this._uomId = v; })}></platform-field>
                    </div>
                `}
                <platform-field type="array" mode="edit" .label=${this.t('fields.barcodes')}
                    .value=${this._barcodes}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        this._barcodes = Array.isArray(e.detail.value) ? (e.detail.value as string[]) : [];
                    }}></platform-field>
                <div class="row2">
                    <platform-field type="enum" mode="edit" .label=${this.t('fields.valuation_method')}
                        .value=${this._valuationMethod} .config=${enumConfig(VALUATION_METHODS)}
                        @change=${set((v) => { this._valuationMethod = v; })}></platform-field>
                    <platform-field type="enum" mode="edit" .label=${this.t('fields.tracking')}
                        .value=${this._tracking} .config=${enumConfig(TRACKING_KINDS)}
                        @change=${set((v) => { this._tracking = v; })}></platform-field>
                </div>
                <div class="row2">
                    <platform-field type="number" mode="edit" .label=${this.t('fields.standard_price')}
                        .value=${this._standardPrice} @change=${set((v) => { this._standardPrice = v; })}></platform-field>
                    <platform-field type="string" mode="edit" .label=${this.t('fields.category')}
                        .value=${this._category} @change=${set((v) => { this._category = v; })}></platform-field>
                </div>
                <div class="row2">
                    <platform-field type="number" mode="edit" .label=${this.t('fields.weight')}
                        .value=${this._weight} @change=${set((v) => { this._weight = v; })}></platform-field>
                    <platform-field type="number" mode="edit" .label=${this.t('fields.volume')}
                        .value=${this._volume} @change=${set((v) => { this._volume = v; })}></platform-field>
                </div>
                <platform-field type="boolean" mode="edit" .label=${this.t('fields.is_storable')}
                    .value=${this._isStorable}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._isStorable = e.detail.value === true; }}></platform-field>
                ${this._editing ? html`
                    <platform-field type="boolean" mode="edit" .label=${this.t('settings.is_active')}
                        .value=${this._isActive}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._isActive = e.detail.value === true; }}></platform-field>
                ` : ''}
                <div style="display:flex; gap: var(--space-2); justify-content: flex-end;">
                    <platform-button variant="secondary" @click=${() => this.close()}>${this.t('settings.cancel')}</platform-button>
                    <platform-button variant="primary" ?loading=${this._saving} ?disabled=${!this._valid()}
                        @click=${() => void this._save()}>
                        <platform-icon name="check" size="14"></platform-icon> ${this.t('settings.save')}
                    </platform-button>
                </div>
            </form>
        `;
    }
}

customElements.define('stock-product-modal', StockProductModal);
registerModalKind(StockProductModal.modalKind, 'stock-product-modal');
