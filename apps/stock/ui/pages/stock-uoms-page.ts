/**
 * Единицы измерения и упаковки — справочник из двух секций:
 * глобальные ЕИ компании (catalog_uoms, product_id IS NULL) и фасовки
 * товаров (catalog_uoms с product_id — «короб 24 шт»).
 *
 * Создание — через `stock-entity-form-modal`, удаление — только для
 * пользовательских ЕИ (reference и базовые ЕИ товаров защищены backend).
 */

import { html } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type { CatalogUom, CatalogPackagingView } from '@platform/lib/events/wire/stock.gen.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import { stockPageStyles } from '../styles/stock-page.styles.js';
import { StockEntityFormModal } from '../modals/stock-entity-form-modal.js';

const UOM_CATEGORIES = ['unit', 'weight', 'length', 'volume'];

export class StockUomsPage extends PlatformPage {
    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        stockPageStyles,
    ];

    private _uoms: OpController;
    private _uomDelete: OpController;
    private _packagings: OpController;
    private _pkgDelete: OpController;
    private _products: ResourceController;

    constructor() {
        super();
        this._uoms = this.useOp('stock/uoms_list');
        this._uomDelete = this.useOp('stock/uom_delete');
        this._packagings = this.useOp('stock/packagings_list');
        this._pkgDelete = this.useOp('stock/packaging_delete');
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._uoms.run({});
        this._packagings.run({});
    }

    private _uomItems(): CatalogUom[] {
        const result = this._uoms.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord) as CatalogUom[];
    }

    private _packagingItems(): CatalogPackagingView[] {
        const result = this._packagings.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord) as CatalogPackagingView[];
    }

    private _productName(productId: string): string {
        const row = this._products.items.find((p) => isPlainRecord(p) && p.product_id === productId);
        if (!isPlainRecord(row)) return productId;
        return typeof row.name === 'string' && row.name !== '' ? row.name : productId;
    }

    private _productOptions(): { value: string; label: string }[] {
        return this._products.items.filter(isPlainRecord).map((p) => ({
            value: p.product_id as string,
            label: (typeof p.name === 'string' && p.name !== '' ? p.name : p.product_id) as string,
        }));
    }

    private _categoryLabel(category: string): string {
        const key = `uoms.category_${category}`;
        const label = this.t(key);
        return label === key ? category : label;
    }

    private _openUomCreate(): void {
        this.openModal(StockEntityFormModal, {
            modalTitle: this.t('uoms.create_uom'),
            fields: [
                { key: 'name', label: this.t('settings.name'), required: true },
                {
                    key: 'category', label: this.t('uoms.category'), type: 'enum', required: true,
                    options: UOM_CATEGORIES.map((c) => ({ value: c, label: this._categoryLabel(c) })),
                },
                { key: 'factor', label: this.t('uoms.factor'), type: 'number', required: true },
                { key: 'weight', label: this.t('settings.max_weight'), type: 'number' },
                { key: 'volume', label: this.t('settings.max_volume'), type: 'number' },
            ],
            submitOp: 'stock/uom_create',
            initialDraft: { category: 'unit', factor: 1 },
            buildPayload: (d: Record<string, unknown>) => ({
                name: d.name,
                category: typeof d.category === 'string' ? d.category : 'unit',
                factor: Number(d.factor),
                weight: Number.isFinite(Number(d.weight)) && d.weight !== '' ? Number(d.weight) : null,
                volume: Number.isFinite(Number(d.volume)) && d.volume !== '' ? Number(d.volume) : null,
            }),
        });
    }

    private _openPackagingCreate(): void {
        this.openModal(StockEntityFormModal, {
            modalTitle: this.t('uoms.create_packaging'),
            fields: [
                {
                    key: 'product_id', label: this.t('settings.product'), type: 'enum', required: true,
                    options: this._productOptions(),
                },
                { key: 'name', label: this.t('settings.name'), required: true },
                { key: 'quantity', label: this.t('uoms.quantity'), type: 'number', required: true },
                { key: 'barcode', label: this.t('settings.barcode') },
                { key: 'weight', label: this.t('settings.max_weight'), type: 'number' },
                { key: 'volume', label: this.t('settings.max_volume'), type: 'number' },
            ],
            submitOp: 'stock/packaging_create',
            buildPayload: (d: Record<string, unknown>) => ({
                product_id: d.product_id,
                name: d.name,
                quantity: Number(d.quantity),
                barcode: typeof d.barcode === 'string' && d.barcode !== '' ? d.barcode : null,
                weight: Number.isFinite(Number(d.weight)) && d.weight !== '' ? Number(d.weight) : null,
                volume: Number.isFinite(Number(d.volume)) && d.volume !== '' ? Number(d.volume) : null,
            }),
        });
    }

    private async _deleteUom(row: CatalogUom): Promise<void> {
        const ok = await platformConfirm(this.t('uoms.confirm_delete_uom'), { confirmText: this.t('settings.delete'), confirmVariant: 'danger' });
        if (ok !== true) return;
        await this._uomDelete.run({ uom_id: row.uom_id });
    }

    private async _deletePackaging(row: CatalogPackagingView): Promise<void> {
        const ok = await platformConfirm(this.t('uoms.confirm_delete_packaging'), { confirmText: this.t('settings.delete'), confirmVariant: 'danger' });
        if (ok !== true) return;
        await this._pkgDelete.run({ packaging_id: row.packaging_id });
    }

    private _renderTable(head: TemplateResult[], rows: TemplateResult[], emptyKey: string): TemplateResult {
        return html`
            <div class="table-card"><div class="scroll">
                ${rows.length === 0
                    ? html`<platform-empty-state .message=${this.t(emptyKey)}></platform-empty-state>`
                    : html`<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`}
            </div></div>
        `;
    }

    private _renderSection(titleKey: string, onCreate: () => void, createLabel: string): TemplateResult {
        return html`
            <div class="section">
                <h2>${this.t(titleKey)}</h2>
                <platform-button variant="secondary" density="compact" @click=${onCreate}>
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${createLabel}
                </platform-button>
            </div>
        `;
    }

    private _deleteBtn(onClick: (e: Event) => void, busy: boolean): TemplateResult {
        return html`
            <button type="button" class="icon-btn danger" ?disabled=${busy}
                title=${this.t('settings.delete')} aria-label=${this.t('settings.delete')}
                @click=${onClick}
            ><platform-icon name="trash" size="14"></platform-icon></button>
        `;
    }

    override render() {
        const uoms = this._uomItems().filter((u) => u.product_id === null || u.product_id === undefined);
        const packagings = this._packagingItems();
        return html`
            <div class="wrap">
                <page-header
                    title=${this.t('uoms.title')}
                    subtitle=${this.t('uoms.subtitle')}
                    dense
                ></page-header>

                ${this._renderSection('uoms.base_title', () => this._openUomCreate(), this.t('uoms.create_uom'))}
                ${this._renderTable(
                    [
                        html`<th>${this.t('settings.name')}</th>`,
                        html`<th>${this.t('uoms.category')}</th>`,
                        html`<th class="num">${this.t('uoms.factor')}</th>`,
                        html`<th></th>`,
                    ],
                    uoms.map((u) => html`
                        <tr>
                            <td>${u.name}${u.is_reference === true ? html` <span class="num" style="text-align:left">· ${this.t('uoms.reference')}</span>` : ''}</td>
                            <td>${this._categoryLabel(u.category)}</td>
                            <td class="num">${u.factor}</td>
                            <td class="num">
                                ${u.is_reference === true ? '' : this._deleteBtn(() => { void this._deleteUom(u); }, this._uomDelete.busy)}
                            </td>
                        </tr>
                    `),
                    'uoms.empty',
                )}

                ${this._renderSection('uoms.packagings_title', () => this._openPackagingCreate(), this.t('uoms.create_packaging'))}
                ${this._renderTable(
                    [
                        html`<th>${this.t('settings.name')}</th>`,
                        html`<th>${this.t('settings.product')}</th>`,
                        html`<th class="num">${this.t('uoms.quantity')}</th>`,
                        html`<th></th>`,
                    ],
                    packagings.map((p) => html`
                        <tr>
                            <td>${p.name}</td>
                            <td>${this._productName(p.product_id)}</td>
                            <td class="num">${p.quantity}</td>
                            <td class="num">${this._deleteBtn(() => { void this._deletePackaging(p); }, this._pkgDelete.busy)}</td>
                        </tr>
                    `),
                    'uoms.empty_packagings',
                )}
            </div>
        `;
    }
}

customElements.define('stock-uoms-page', StockUomsPage);
