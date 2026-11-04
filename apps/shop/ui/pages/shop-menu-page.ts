/**
 * Редактор одного меню заведения: дерево разделов слева, позиции справа.
 *
 * Меню — элемент `shop/menus_list` (разделы по sort, позиции по разделу и
 * sort); блюдо позиции — `shop/products_list`. Обе фабрики перечитываются
 * push-событиями `shop/menu/updated` и `shop/catalog/changed`, страница
 * мутирует только командами `shop/menu_*`. Позиция переопределяет цену и
 * доступность блюда каталога; карточка блюда — `shop.product`, похожее
 * блюдо — `shop.product_merge`.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type {
    ShopBadgeResponse,
    ShopMenuItemResponse,
    ShopMenuResponse,
    ShopMenuSection,
    ShopMenuSectionReorderItem,
    ShopMenuStatus,
    ShopProductResponse,
} from '@platform/lib/events/wire/shop.gen.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/shop-agent-jobs-banner.js';
import '../components/shop-section-tree.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import type { ShopHeadRow } from '../components/shop-page-head.js';
import { formatShopMeasure, formatShopPrice, shopBadgeSvg, shopFileUrl, shopPriceMinor } from '../_helpers/shop-format.js';

interface SectionGroup {
    section: ShopMenuSection;
    items: ShopMenuItemResponse[];
}

function sectionParentId(section: ShopMenuSection): string | null {
    return section.parent_id === undefined ? null : section.parent_id;
}

const STATUS_TONES: Record<ShopMenuStatus, string> = {
    draft: 'var(--text-tertiary)',
    active: 'var(--success)',
    archived: 'var(--warning)',
};

export class ShopMenuPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare menuId: string;

    private _shops: ControllerFor<'shop/shops'>;
    private _menusOp: ControllerFor<'shop/menus_list'>;
    private _productsOp: ControllerFor<'shop/products_list'>;
    private _menuUpdateOp: ControllerFor<'shop/menu_update'>;
    private _menuStatusOp: ControllerFor<'shop/menu_set_status'>;
    private _sectionCreateOp: ControllerFor<'shop/menu_section_create'>;
    private _sectionUpdateOp: ControllerFor<'shop/menu_section_update'>;
    private _sectionRemoveOp: ControllerFor<'shop/menu_section_remove'>;
    private _sectionsReorderOp: ControllerFor<'shop/menu_sections_reorder'>;
    private _itemAddOp: ControllerFor<'shop/menu_item_add'>;
    private _itemUpdateOp: ControllerFor<'shop/menu_item_update'>;
    private _itemMoveOp: ControllerFor<'shop/menu_item_move'>;
    private _itemRemoveOp: ControllerFor<'shop/menu_item_remove'>;
    private _itemsReorderOp: ControllerFor<'shop/menu_items_reorder'>;
    private _locale: SelectController<string>;

    declare _activeSectionId: string | null;
    declare _moveEditId: string;
    declare _addOpen: boolean;
    declare _addQuery: string;
    declare _renaming: boolean;
    declare _nameDraft: string;
    declare _priceEditId: string;
    declare _priceDraft: string;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        menuId: { type: String, attribute: 'menu-id' },
        _activeSectionId: { state: true },
        _moveEditId: { state: true },
        _addOpen: { state: true },
        _addQuery: { state: true },
        _renaming: { state: true },
        _nameDraft: { state: true },
        _priceEditId: { state: true },
        _priceDraft: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { padding: var(--space-5) var(--space-6) var(--space-10); }
            .head-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
            .status { font-size: var(--text-xs); font-weight: var(--font-semibold); }

            .panel {
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                background: var(--bg-surface); padding: var(--space-4); margin-bottom: var(--space-4);
                display: flex; flex-direction: column; gap: var(--space-3);
            }
            .panel-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .panel-hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
            .panel-row { display: flex; gap: var(--space-2); align-items: flex-end; flex-wrap: wrap; }
            .panel-row platform-field { flex: 1; min-width: 220px; }
            .catalog-list { display: flex; flex-direction: column; gap: var(--space-1); max-height: 320px; overflow-y: auto; }
            .catalog-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--text-secondary); padding: var(--space-1) 0; }
            .catalog-row .grow { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

            .readonly-note {
                display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;
                padding: var(--space-3); margin-bottom: var(--space-4); border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--warning) 10%, transparent);
                color: var(--text-secondary); font-size: var(--text-sm);
            }
            .readonly-note span { flex: 1; min-width: 0; }

            .layout { display: grid; grid-template-columns: 248px minmax(0, 1fr); gap: var(--space-5); align-items: start; }
            .rail {
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                background: var(--bg-surface); padding: var(--space-2);
                position: sticky; top: var(--space-4); min-width: 0;
            }
            .groups { display: flex; flex-direction: column; gap: var(--space-5); min-width: 0; }
            .group-title {
                font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary);
                text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--space-2);
            }
            .group-empty { font-size: var(--text-xs); color: var(--text-tertiary); }
            .list { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: var(--space-3); }
            .card {
                display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                background: var(--bg-surface); padding: var(--space-3);
            }
            .card:hover { border-color: color-mix(in srgb, var(--text-primary) 18%, transparent); }
            .card.off { opacity: 0.55; }
            .thumb { width: 56px; height: 56px; border-radius: var(--radius-md); object-fit: cover; display: block; flex-shrink: 0; }
            .thumb-empty {
                width: 56px; height: 56px; border-radius: var(--radius-md); flex-shrink: 0;
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                display: flex; align-items: center; justify-content: center; color: var(--text-tertiary);
            }
            .pinfo { flex: 1; min-width: 0; }
            .pname {
                display: flex; align-items: center; gap: var(--space-1); flex-wrap: wrap;
                font-weight: var(--font-semibold); color: var(--text-primary); font-size: var(--text-sm); line-height: 1.3;
            }
            .measure { color: var(--text-tertiary); font-size: var(--text-xs); font-weight: var(--font-normal); }
            .ptag {
                display: inline-flex; align-items: center; gap: 2px; padding: 1px var(--space-2);
                border-radius: var(--radius-full); border: 0; font: inherit;
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent); font-size: 10px; font-weight: var(--font-bold);
            }
            button.ptag { cursor: pointer; }
            .ptag.warn { background: color-mix(in srgb, var(--warning) 14%, transparent); color: var(--warning); }
            .ptag svg { width: 11px; height: 11px; fill: currentColor; }
            .price-box { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
            .price {
                font-variant-numeric: tabular-nums; font-weight: var(--font-semibold); color: var(--text-primary);
                white-space: nowrap; border: 0; background: transparent; font: inherit; cursor: pointer; padding: 0;
            }
            .price::after { content: ' ₽'; font-weight: var(--font-normal); color: var(--text-tertiary); }
            .price.override { color: var(--accent); }
            .catalog-price { font-size: var(--text-2xs, 10px); color: var(--text-tertiary); text-decoration: line-through; font-variant-numeric: tabular-nums; }
            .price-edit { display: flex; align-items: flex-end; gap: 2px; width: 100%; }
            .price-edit platform-field { flex: 1; }
            .ops { display: flex; gap: 2px; align-items: center; margin-left: auto; opacity: 0; transition: opacity 0.15s; }
            .card:hover .ops, .card:focus-within .ops { opacity: 1; }

            platform-empty-state { margin-top: var(--space-8); }

            @media (max-width: 900px) {
                .layout { grid-template-columns: 1fr; }
                .rail { position: static; }
                .list { grid-template-columns: 1fr; }
            }
            @media (max-width: 640px) {
                .ops { opacity: 1; }
            }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this.menuId = '';
        this._activeSectionId = null;
        this._moveEditId = '';
        this._addOpen = false;
        this._addQuery = '';
        this._renaming = false;
        this._nameDraft = '';
        this._priceEditId = '';
        this._priceDraft = '';
        this._shops = this.useResource('shop/shops');
        this._menusOp = this.useOp('shop/menus_list');
        this._productsOp = this.useOp('shop/products_list');
        this._menuUpdateOp = this.useOp('shop/menu_update');
        this._menuStatusOp = this.useOp('shop/menu_set_status');
        this._sectionCreateOp = this.useOp('shop/menu_section_create');
        this._sectionUpdateOp = this.useOp('shop/menu_section_update');
        this._sectionRemoveOp = this.useOp('shop/menu_section_remove');
        this._sectionsReorderOp = this.useOp('shop/menu_sections_reorder');
        this._itemAddOp = this.useOp('shop/menu_item_add');
        this._itemUpdateOp = this.useOp('shop/menu_item_update');
        this._itemMoveOp = this.useOp('shop/menu_item_move');
        this._itemRemoveOp = this.useOp('shop/menu_item_remove');
        this._itemsReorderOp = this.useOp('shop/menu_items_reorder');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._load();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const prevShopId = changed.get('shopId');
        const prevMenuId = changed.get('menuId');
        const shopChanged = typeof prevShopId === 'string' && prevShopId !== this.shopId;
        const menuChanged = typeof prevMenuId === 'string' && prevMenuId !== this.menuId;
        if (shopChanged || menuChanged) {
            this._activeSectionId = null;
            this._moveEditId = '';
            this._addOpen = false;
            this._renaming = false;
            this._priceEditId = '';
            if (shopChanged) void this._load();
        }
        const menu = this._menu();
        if (menu !== null) {
            if (this._activeSectionId !== null
                && !menu.sections.some((s) => s.shop_menu_section_id === this._activeSectionId)) {
                this._activeSectionId = null;
            }
        }
    }

    private async _load(): Promise<void> {
        if (this.shopId === '') return;
        await Promise.all([
            this._menusOp.run({ shop_id: this.shopId }),
            this._productsOp.run({ shop_id: this.shopId }),
            this._shops.load(),
        ]);
    }

    private _shopRow(): ShopHeadRow | null {
        return shopHeadRow(this._shops.items.find((s) => s.shop_id === this.shopId));
    }

    private _badgeDefs(): ShopBadgeResponse[] {
        const shop = this._shops.items.find((s) => s.shop_id === this.shopId);
        return shop === undefined ? [] : shop.badges;
    }

    private _menu(): ShopMenuResponse | null {
        const result = this._menusOp.lastResult;
        if (result === null) return null;
        const menu = result.items.find((m) => m.shop_menu_id === this.menuId);
        return menu === undefined || menu.shop_id !== this.shopId ? null : menu;
    }

    private _productsById(): Map<string, ShopProductResponse> {
        const result = this._productsOp.lastResult;
        const map = new Map<string, ShopProductResponse>();
        if (result === null) return map;
        for (const product of result.items) {
            if (product.shop_id === this.shopId) map.set(product.shop_product_id, product);
        }
        return map;
    }

    private _money(minor: number): string {
        return formatShopPrice(minor, this._locale.value);
    }

    private _statusLabel(status: ShopMenuStatus): string {
        switch (status) {
            case 'draft': return this.t('menu_status.draft');
            case 'active': return this.t('menu_status.active');
            case 'archived': return this.t('menu_status.archived');
        }
    }

    /** Разделы в порядке обхода дерева (depth-first, siblings по порядку сервера). */
    private _orderedSections(menu: ShopMenuResponse): ShopMenuSection[] {
        const ids = new Set(menu.sections.map((s) => s.shop_menu_section_id));
        const children = new Map<string | null, ShopMenuSection[]>();
        for (const section of menu.sections) {
            const declared = sectionParentId(section);
            const parent = declared !== null && ids.has(declared) ? declared : null;
            const list = children.get(parent);
            if (list === undefined) children.set(parent, [section]);
            else list.push(section);
        }
        const out: ShopMenuSection[] = [];
        const walk = (parentId: string | null) => {
            for (const section of children.get(parentId) ?? []) {
                out.push(section);
                walk(section.shop_menu_section_id);
            }
        };
        walk(null);
        return out;
    }

    private _subtreeIds(menu: ShopMenuResponse, rootId: string): Set<string> {
        const out = new Set<string>([rootId]);
        let grew = true;
        while (grew) {
            grew = false;
            for (const section of menu.sections) {
                const parent = sectionParentId(section);
                if (parent !== null && out.has(parent) && !out.has(section.shop_menu_section_id)) {
                    out.add(section.shop_menu_section_id);
                    grew = true;
                }
            }
        }
        return out;
    }

    private _subtreeCounts(menu: ShopMenuResponse): Record<string, number> {
        const counts: Record<string, number> = {};
        for (const section of menu.sections) {
            const subtree = this._subtreeIds(menu, section.shop_menu_section_id);
            counts[section.shop_menu_section_id] = menu.items.filter((i) => subtree.has(i.shop_menu_section_id)).length;
        }
        return counts;
    }

    private _groups(menu: ShopMenuResponse): SectionGroup[] {
        const visible = this._activeSectionId === null ? null : this._subtreeIds(menu, this._activeSectionId);
        return this._orderedSections(menu)
            .filter((section) => visible === null || visible.has(section.shop_menu_section_id))
            .map((section) => ({
                section,
                items: menu.items.filter((i) => i.shop_menu_section_id === section.shop_menu_section_id),
            }));
    }

    // --- Меню ---

    private async _setStatus(status: ShopMenuStatus): Promise<void> {
        await this._menuStatusOp.run({ shop_id: this.shopId, shop_menu_id: this.menuId, status });
    }

    private _beginRename(menu: ShopMenuResponse): void {
        this._nameDraft = menu.name;
        this._renaming = true;
    }

    private async _commitRename(): Promise<void> {
        const name = this._nameDraft.trim();
        if (name === '') return;
        const updated = await this._menuUpdateOp.run({ shop_id: this.shopId, shop_menu_id: this.menuId, name });
        if (updated !== null) this._renaming = false;
    }

    private _openImport(): void {
        this.openModal('shop.menu_import', { shopId: this.shopId, target: 'into_menu', shopMenuId: this.menuId });
    }

    // --- Разделы ---

    private async _createSection(parentId: string | null, name: string): Promise<void> {
        const created = await this._sectionCreateOp.run({
            shop_id: this.shopId,
            shop_menu_id: this.menuId,
            name,
            parent_id: parentId,
        });
        if (created !== null) this._activeSectionId = created.shop_menu_section_id;
    }

    private async _renameSection(sectionId: string, name: string): Promise<void> {
        await this._sectionUpdateOp.run({ shop_id: this.shopId, shop_menu_section_id: sectionId, name });
    }

    private async _removeSection(sectionId: string): Promise<void> {
        await this._sectionRemoveOp.run({ shop_id: this.shopId, shop_menu_section_id: sectionId });
    }

    private async _reorderSections(items: ShopMenuSectionReorderItem[]): Promise<void> {
        await this._sectionsReorderOp.run({ shop_id: this.shopId, shop_menu_id: this.menuId, items });
    }

    // --- Позиции ---

    private async _addItem(product: ShopProductResponse): Promise<void> {
        if (this._activeSectionId === null) return;
        await this._itemAddOp.run({
            shop_id: this.shopId,
            shop_menu_id: this.menuId,
            shop_menu_section_id: this._activeSectionId,
            shop_product_id: product.shop_product_id,
        });
    }

    private async _moveItem(item: ShopMenuItemResponse, sectionId: string): Promise<void> {
        if (sectionId === item.shop_menu_section_id) return;
        const moved = await this._itemMoveOp.run({
            shop_id: this.shopId,
            shop_menu_item_id: item.shop_menu_item_id,
            shop_menu_section_id: sectionId,
        });
        if (moved !== null) this._moveEditId = '';
    }

    private _renderMove(menu: ShopMenuResponse, item: ShopMenuItemResponse): TemplateResult {
        const values = this._orderedSections(menu).map((s) => ({ value: s.shop_menu_section_id, label: s.name }));
        return html`
            <div class="price-edit">
                <platform-field type="enum" mode="edit" density="compact" label=${this.t('menu_editor.item_section')}
                    .config=${{ values }}
                    .value=${item.shop_menu_section_id}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const v = e.detail.value;
                        if (typeof v === 'string') void this._moveItem(item, v);
                    }}
                ></platform-field>
                <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu_editor.cancel')}
                    @click=${() => { this._moveEditId = ''; }}
                ><platform-icon name="close" size="12"></platform-icon></platform-button>
            </div>`;
    }

    private async _toggleItemAvailable(item: ShopMenuItemResponse, enabled: boolean): Promise<void> {
        await this._itemUpdateOp.run({ shop_id: this.shopId, shop_menu_item_id: item.shop_menu_item_id, is_available: enabled });
    }

    private _beginPriceEdit(item: ShopMenuItemResponse): void {
        this._priceEditId = item.shop_menu_item_id;
        this._priceDraft = item.price_minor_override === null ? '' : String(item.price_minor_override / 100);
    }

    private async _commitPrice(item: ShopMenuItemResponse): Promise<void> {
        const text = this._priceDraft.trim();
        const override = text === '' ? null : shopPriceMinor(text);
        if (text !== '' && override === null) return;
        const updated = await this._itemUpdateOp.run({
            shop_id: this.shopId,
            shop_menu_item_id: item.shop_menu_item_id,
            price_minor_override: override,
        });
        if (updated !== null) this._priceEditId = '';
    }

    private async _reorderItem(group: SectionGroup, item: ShopMenuItemResponse, dir: -1 | 1): Promise<void> {
        const ids = group.items.map((i) => i.shop_menu_item_id);
        const index = ids.indexOf(item.shop_menu_item_id);
        const swap = ids[index + dir];
        if (index === -1 || swap === undefined) return;
        ids[index] = swap;
        ids[index + dir] = item.shop_menu_item_id;
        await this._itemsReorderOp.run({
            shop_id: this.shopId,
            shop_menu_section_id: group.section.shop_menu_section_id,
            shop_menu_item_ids: ids,
        });
    }

    private async _removeItem(item: ShopMenuItemResponse): Promise<void> {
        await this._itemRemoveOp.run({ shop_id: this.shopId, shop_menu_item_id: item.shop_menu_item_id });
    }

    private _openProduct(product: ShopProductResponse): void {
        this.openModal('shop.product', { shopId: this.shopId, product, badgeDefs: this._badgeDefs() });
    }

    private _openMerge(product: ShopProductResponse): void {
        this.openModal('shop.product_merge', { shopId: this.shopId, product });
    }

    // --- Рендер ---

    private _renderHeadActions(menu: ShopMenuResponse, editable: boolean): TemplateResult {
        const busy = this._menuStatusOp.busy;
        return html`
            <div slot="actions" class="head-actions">
                <span class="status" style="color:${STATUS_TONES[menu.status]}">${this._statusLabel(menu.status)}</span>
                ${menu.status === 'draft' ? html`
                    <platform-button size="sm" variant="primary" ?loading=${busy} ?disabled=${menu.items.length === 0}
                        title=${menu.items.length === 0 ? this.t('menus.activate_empty') : this.t('menus.activate')}
                        @click=${() => this._setStatus('active')}
                    ><platform-icon name="play" size="14"></platform-icon> ${this.t('menus.activate')}</platform-button>
                    <platform-button size="sm" variant="ghost" ?loading=${busy} @click=${() => this._setStatus('archived')}
                    >${this.t('menus.archive')}</platform-button>` : nothing}
                ${menu.status === 'active' ? html`
                    <platform-button size="sm" variant="secondary" ?loading=${busy} @click=${() => this._setStatus('draft')}
                    ><platform-icon name="pause" size="14"></platform-icon> ${this.t('menus.deactivate')}</platform-button>` : nothing}
                ${editable ? html`
                    <platform-button size="sm" variant="secondary" @click=${() => this._beginRename(menu)}
                    ><platform-icon name="edit" size="14"></platform-icon> ${this.t('menus.rename')}</platform-button>
                    <platform-button size="sm" variant="secondary" @click=${() => this._openImport()}
                    ><platform-icon name="import" size="14"></platform-icon> ${this.t('menus.import')}</platform-button>
                    <platform-button size="sm" variant="primary" @click=${() => { this._addOpen = !this._addOpen; }}
                    ><platform-icon name="plus" size="14"></platform-icon> ${this.t('menu_editor.add_product')}</platform-button>` : nothing}
            </div>`;
    }

    private _renderRename(): TemplateResult {
        return html`
            <div class="panel">
                <div class="panel-row">
                    <platform-field type="string" mode="edit" label=${this.t('menus.field_name')} .value=${this._nameDraft}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._nameDraft = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); void this._commitRename(); } }}
                    ></platform-field>
                    <platform-button size="sm" variant="secondary" @click=${() => { this._renaming = false; }}>${this.t('menu_editor.cancel')}</platform-button>
                    <platform-button size="sm" variant="primary" ?loading=${this._menuUpdateOp.busy} ?disabled=${this._nameDraft.trim() === ''}
                        @click=${() => this._commitRename()}>${this.t('menus.save')}</platform-button>
                </div>
            </div>`;
    }

    private _renderAddPanel(menu: ShopMenuResponse, products: Map<string, ShopProductResponse>): TemplateResult {
        const inMenu = new Set(menu.items.map((i) => i.shop_product_id));
        const query = this._addQuery.trim().toLowerCase();
        const candidates = [...products.values()]
            .filter((p) => !inMenu.has(p.shop_product_id))
            .filter((p) => query === '' || p.name.toLowerCase().includes(query));
        const activeSection = menu.sections.find((s) => s.shop_menu_section_id === this._activeSectionId);
        return html`
            <div class="panel">
                <div class="panel-title">${this.t('menu_editor.add_product')}</div>
                <div class="panel-hint">
                    ${activeSection === undefined
                        ? this.t('menu_editor.add_pick_section')
                        : this.t('menu_editor.add_into', { section: activeSection.name })}
                </div>
                <platform-field type="string" mode="edit" label=${this.t('catalog.search')} .value=${this._addQuery}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._addQuery = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                ${candidates.length === 0
                    ? html`<div class="panel-hint">${this.t('menu_editor.add_empty')}</div>`
                    : html`
                        <div class="catalog-list">
                            ${candidates.map((p) => html`
                                <div class="catalog-row">
                                    <span class="grow" title=${p.name}>${p.name}</span>
                                    <span>${this._money(p.price_minor)} ₽</span>
                                    <platform-button icon-only density="compact" variant="ghost"
                                        title=${this.t('menu_editor.add')}
                                        ?disabled=${activeSection === undefined}
                                        ?loading=${this._itemAddOp.busy}
                                        @click=${() => this._addItem(p)}
                                    ><platform-icon name="plus" size="14"></platform-icon></platform-button>
                                </div>`)}
                        </div>`}
            </div>`;
    }

    private _renderTags(product: ShopProductResponse): TemplateResult {
        const badgeDefs = this._badgeDefs();
        return html`
            ${product.badges.map((key) => {
                const def = badgeDefs.find((b) => b.key === key);
                return def === undefined ? nothing : html`<span class="ptag" title=${def.label}>${shopBadgeSvg(def.icon_path)}</span>`;
            })}
            ${product.ai_unverified ? html`<span class="ptag warn" title=${this.t('catalog.ai_hint')}>AI</span>` : nothing}
            ${product.similar_shop_product_id !== null ? html`
                <button type="button" class="ptag warn" title=${this.t('catalog.similar_hint')}
                    @click=${() => this._openMerge(product)}
                ><platform-icon name="git-compare" size="10"></platform-icon> ${this.t('catalog.similar_badge')}</button>` : nothing}
        `;
    }

    private _renderPrice(item: ShopMenuItemResponse, product: ShopProductResponse, editable: boolean): TemplateResult {
        if (this._priceEditId === item.shop_menu_item_id) {
            return html`
                <div class="price-edit">
                    <platform-field type="number" mode="edit" density="compact" label=${this.t('menu_editor.price_override')}
                        .value=${this._priceDraft}
                        .hint=${this.t('menu_editor.catalog_price', { price: this._money(product.price_minor) })}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const v = e.detail.value;
                            this._priceDraft = typeof v === 'number' ? String(v) : typeof v === 'string' ? v : '';
                        }}
                        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); void this._commitPrice(item); } }}
                    ></platform-field>
                    <platform-button icon-only density="compact" variant="primary" title=${this.t('menus.save')}
                        ?loading=${this._itemUpdateOp.busy} @click=${() => this._commitPrice(item)}
                    ><platform-icon name="check" size="12"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu_editor.cancel')}
                        @click=${() => { this._priceEditId = ''; }}
                    ><platform-icon name="close" size="12"></platform-icon></platform-button>
                </div>`;
        }
        const overridden = item.price_minor_override !== null;
        return html`
            <span class="price-box">
                <button type="button" class="price ${overridden ? 'override' : ''}" ?disabled=${!editable}
                    title=${this.t('menu_editor.price_override')}
                    @click=${() => this._beginPriceEdit(item)}
                >${this._money(item.effective_price_minor)}</button>
                ${overridden ? html`<span class="catalog-price">${this._money(product.price_minor)}</span>` : nothing}
            </span>`;
    }

    private _renderItem(menu: ShopMenuResponse, group: SectionGroup, item: ShopMenuItemResponse, index: number, product: ShopProductResponse | undefined, editable: boolean): TemplateResult {
        if (product === undefined) {
            return html`<div class="card"><span class="pinfo">${this.t('menu_editor.product_missing')}</span></div>`;
        }
        const measure = formatShopMeasure(product.measure, product.measure_unit, (key) => this.t(key));
        const off = !item.is_available || !product.is_available;
        return html`
            <div class="card ${off ? 'off' : ''}">
                ${product.photo_file_id !== null
                    ? html`<img class="thumb" src=${shopFileUrl(product.photo_file_id)} alt="" loading="lazy">`
                    : html`<span class="thumb-empty"><platform-icon name="image" size="18"></platform-icon></span>`}
                <div class="pinfo">
                    <div class="pname">
                        ${product.name}
                        ${measure === '' ? nothing : html`<span class="measure">${measure}</span>`}
                        ${this._renderTags(product)}
                    </div>
                </div>
                ${this._renderPrice(item, product, editable)}
                <platform-switch
                    title=${this.t('menu_editor.item_available')}
                    ?checked=${item.is_available}
                    ?disabled=${!editable}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._toggleItemAvailable(item, e.detail.value === true)}
                ></platform-switch>
                ${editable ? html`
                    <div class="ops">
                        <platform-button icon-only density="compact" variant="ghost" title=${this.t('menus.move_up')}
                            ?loading=${this._itemsReorderOp.busy} ?disabled=${index === 0}
                            @click=${() => this._reorderItem(group, item, -1)}
                        ><platform-icon name="chevron-up" size="14"></platform-icon></platform-button>
                        <platform-button icon-only density="compact" variant="ghost" title=${this.t('menus.move_down')}
                            ?loading=${this._itemsReorderOp.busy} ?disabled=${index === group.items.length - 1}
                            @click=${() => this._reorderItem(group, item, 1)}
                        ><platform-icon name="chevron-down" size="14"></platform-icon></platform-button>
                        <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu_editor.item_section')}
                            ?disabled=${menu.sections.length < 2}
                            @click=${() => { this._moveEditId = item.shop_menu_item_id; }}
                        ><platform-icon name="drag-handle" size="14"></platform-icon></platform-button>
                        <platform-button icon-only density="compact" variant="ghost" title=${this.t('catalog.edit')}
                            @click=${() => this._openProduct(product)}
                        ><platform-icon name="edit" size="14"></platform-icon></platform-button>
                        <platform-button icon-only density="compact" variant="ghost-danger" title=${this.t('menu_editor.item_remove')}
                            ?loading=${this._itemRemoveOp.busy}
                            @click=${() => this._removeItem(item)}
                        ><platform-icon name="trash" size="14"></platform-icon></platform-button>
                    </div>` : nothing}
                ${editable && this._moveEditId === item.shop_menu_item_id ? this._renderMove(menu, item) : nothing}
            </div>`;
    }

    private _renderGroups(menu: ShopMenuResponse, products: Map<string, ShopProductResponse>, editable: boolean): TemplateResult {
        if (menu.sections.length === 0) {
            return html`<platform-empty-state icon="book-open" title=${this.t('menu_editor.no_sections')}></platform-empty-state>`;
        }
        const groups = this._groups(menu);
        return html`
            <div class="groups">
                ${groups.map((group) => html`
                    <section>
                        <div class="group-title">${group.section.name} · ${group.items.length}</div>
                        ${group.items.length === 0
                            ? html`<div class="group-empty">${this.t('menu_editor.section_empty')}</div>`
                            : html`<div class="list">
                                ${group.items.map((item, index) => this._renderItem(menu, group, item, index, products.get(item.shop_product_id), editable))}
                            </div>`}
                    </section>`)}
            </div>`;
    }

    override render(): TemplateResult {
        const menu = this._menu();
        const shop = this._shopRow();
        if (menu === null) {
            return html`
                <div class="wrap">
                    <shop-page-head .shop=${shop} shop-id=${this.shopId} nested section=${this.t('routes.shop_menu')}></shop-page-head>
                    ${this._menusOp.busy || this._menusOp.lastResult === null
                        ? html`<platform-empty-state loading></platform-empty-state>`
                        : html`<platform-empty-state icon="book-open" title=${this.t('menu_editor.not_found')}></platform-empty-state>`}
                </div>`;
        }
        const editable = menu.status !== 'archived';
        const products = this._productsById();
        return html`
            <div class="wrap">
                <shop-page-head .shop=${shop} shop-id=${this.shopId} nested section=${menu.name}>
                    ${this._renderHeadActions(menu, editable)}
                </shop-page-head>
                <shop-agent-jobs-banner shop-id=${this.shopId}></shop-agent-jobs-banner>
                ${editable ? nothing : html`
                    <div class="readonly-note">
                        <span>${this.t('menu_editor.archived_hint')}</span>
                        <platform-button size="sm" variant="secondary" ?loading=${this._menuStatusOp.busy}
                            @click=${() => this._setStatus('draft')}
                        ><platform-icon name="history" size="14"></platform-icon> ${this.t('menus.restore')}</platform-button>
                    </div>`}
                ${this._renaming && editable ? this._renderRename() : nothing}
                ${this._addOpen && editable ? this._renderAddPanel(menu, products) : nothing}
                <div class="layout">
                    <div class="rail">
                        <shop-section-tree
                            .sections=${menu.sections}
                            .counts=${this._subtreeCounts(menu)}
                            .allCount=${menu.items.length}
                            .selectedId=${this._activeSectionId}
                            @section-select=${(e: CustomEvent<{ id: string | null }>) => { this._activeSectionId = e.detail.id; }}
                            @section-create=${(e: CustomEvent<{ parentId: string | null; name: string }>) => {
                                if (editable) void this._createSection(e.detail.parentId, e.detail.name);
                            }}
                            @section-rename=${(e: CustomEvent<{ id: string; name: string }>) => {
                                if (editable) void this._renameSection(e.detail.id, e.detail.name);
                            }}
                            @section-remove=${(e: CustomEvent<{ id: string }>) => {
                                if (editable) void this._removeSection(e.detail.id);
                            }}
                            @section-reorder=${(e: CustomEvent<{ items: ShopMenuSectionReorderItem[] }>) => {
                                if (editable) void this._reorderSections(e.detail.items);
                            }}
                        ></shop-section-tree>
                    </div>
                    ${this._renderGroups(menu, products, editable)}
                </div>
            </div>
        `;
    }
}

customElements.define('shop-menu-page', ShopMenuPage);
