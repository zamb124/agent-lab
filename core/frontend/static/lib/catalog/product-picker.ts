/**
 * `<platform-catalog-product-picker>` — диалог «подключить или создать»:
 * поиск по каталогу компании через хостовый suggest-op
 * (`<svc>/catalog_products/suggest`), выбор существующего товара
 * (`onPick`) или переход к созданию нового (`onCreateNew` — с текстом
 * запроса как стартовым именем). Дедуп-флоу каноничен для stock и shop:
 * создать дубль вместо подключения нельзя.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformModal } from '../components/glass-modal.js';
import type { OpController } from '../base/use-resource.js';
import type { FactoryNameOfKind } from '../events/factory-registry.js';
import { isPlainRecord } from '../events/payload.js';
import { registerModalKind } from '../utils/modal-registry.js';
import '../components/fields/platform-field.js';
import '../components/platform-button.js';
import '../components/platform-icon.js';
import './product-card.js';

export interface CatalogProductPick {
    product_id: string;
    name: string;
    description: string;
    sku: string;
    image_file_ids: string[];
    is_archived: boolean;
}

export class PlatformCatalogProductPicker extends PlatformModal {
    static modalKind = 'platform.catalog_product_picker';
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        suggestOpName: { type: String, attribute: 'suggest-op-name' },
        onPick: { attribute: false },
        onCreateNew: { attribute: false },
        _query: { state: true },
        _items: { state: true },
    };

    declare suggestOpName: FactoryNameOfKind<'async-op'> | null;
    declare onPick: ((product: CatalogProductPick) => void) | null;
    declare onCreateNew: ((initialName: string) => void) | null;
    declare private _query: string;
    declare private _items: CatalogProductPick[];

    private _suggestOp: OpController | null;
    private _debounce: number | undefined;

    static override styles: CSSResultGroup = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .list { display: flex; flex-direction: column; gap: var(--space-1); margin-top: var(--space-3); }
            .row {
                border: none; background: transparent; text-align: start;
                border-radius: var(--radius-md); cursor: pointer; padding: 0;
            }
            .row:hover { background: var(--surface-2); }
            .create-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3); margin-bottom: var(--space-2);
                border: 1px dashed var(--glass-border-subtle); border-radius: var(--radius-md);
                background: transparent; cursor: pointer; width: 100%;
                color: var(--accent-primary); font-size: var(--text-sm);
            }
            .create-row:hover { border-color: var(--accent-primary); }
            .empty { color: var(--text-tertiary); font-size: var(--text-sm); padding: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.suggestOpName = null;
        this.onPick = null;
        this.onCreateNew = null;
        this._query = '';
        this._items = [];
        this._suggestOp = null;
        this._debounce = undefined;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('open') && this.open) {
            this._query = '';
            this._items = [];
            if (this.suggestOpName === null) {
                throw new Error('platform-catalog-product-picker: suggestOpName required');
            }
            if (this.onPick === null) {
                throw new Error('platform-catalog-product-picker: onPick required');
            }
            if (this._suggestOp === null) {
                this._suggestOp = this.useOp(this.suggestOpName);
            }
        }
    }

    private _onQueryChange(e: CustomEvent<{ value?: unknown }>): void {
        const raw = e.detail?.value;
        this._query = typeof raw === 'string' ? raw : '';
        window.clearTimeout(this._debounce);
        this._debounce = window.setTimeout(() => void this._runSuggest(), 250);
    }

    private async _runSuggest(): Promise<void> {
        const op = this._suggestOp;
        if (op === null) {
            throw new Error('platform-catalog-product-picker: suggest op required');
        }
        const query = this._query.trim();
        const result = await op.run({ name: query === '' ? null : query, limit: 8 });
        const items = isPlainRecord(result) && Array.isArray(result.items) ? result.items : [];
        this._items = items.filter(isPlainRecord).map((row) => ({
            product_id: typeof row.product_id === 'string' ? row.product_id : '',
            name: typeof row.name === 'string' ? row.name : '',
            description: typeof row.description === 'string' ? row.description : '',
            sku: typeof row.sku === 'string' ? row.sku : '',
            image_file_ids: Array.isArray(row.image_file_ids) ? (row.image_file_ids as string[]) : [],
            is_archived: row.is_archived === true,
        }));
    }

    private _pick(item: CatalogProductPick): void {
        if (this.onPick === null) return;
        this.onPick(item);
        this.close();
    }

    private _createNew(): void {
        if (this.onCreateNew === null) return;
        this.onCreateNew(this._query.trim());
        this.close();
    }

    override renderHeader() {
        return this.t('catalog.picker_title');
    }

    override renderBody(): TemplateResult {
        return html`
            <platform-field
                type="string" mode="edit" input-type="search"
                .placeholder=${this.t('catalog.picker_search')}
                .value=${this._query}
                @change=${this._onQueryChange}
            ></platform-field>
            <div class="list">
                ${this.onCreateNew !== null ? html`
                    <button type="button" class="create-row" data-create-new @click=${this._createNew}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('catalog.picker_create')}
                    </button>
                ` : ''}
                ${this._items.length === 0 && this._suggestOp !== null && !this._suggestOp.busy
                    ? html`<div class="empty">${this.t('catalog.picker_empty')}</div>`
                    : ''}
                ${this._items.map((item) => html`
                    <button type="button" class="row" data-product-id=${item.product_id} @click=${() => this._pick(item)}>
                        <platform-catalog-product-card
                            .name=${item.name}
                            .sku=${item.sku}
                            .barcodes=${[]}
                            ?archived=${item.is_archived}
                        ></platform-catalog-product-card>
                    </button>
                `)}
            </div>
        `;
    }
}

customElements.define('platform-catalog-product-picker', PlatformCatalogProductPicker);
registerModalKind(PlatformCatalogProductPicker.modalKind, 'platform-catalog-product-picker');
