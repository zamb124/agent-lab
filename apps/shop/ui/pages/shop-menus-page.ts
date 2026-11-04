/**
 * Меню заведения: карточки меню со статусом и счётчиками.
 *
 * Создание (пустое, импортом или агентом из каталога), переименование,
 * статус (черновик → активно → архив → черновик), удаление и порядок меню.
 * Карточка открывает редактор `shop_menu`. Список перечитывает фабрика
 * `shop/menus_list` по push `shop/menu/updated` и исходу reorder.
 */

import { html, css } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { ShopMenuResponse, ShopMenuStatus } from '@platform/lib/events/wire/shop.gen.js';
import { platformConfirm, platformPrompt } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '../components/shop-agent-jobs-banner.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import type { ShopHeadRow } from '../components/shop-page-head.js';

const STATUS_TONES: Record<ShopMenuStatus, string> = {
    draft: 'var(--text-tertiary)',
    active: 'var(--success)',
    archived: 'var(--warning)',
};

export class ShopMenusPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ControllerFor<'shop/shops'>;
    private _menus: ControllerFor<'shop/menus_list'>;
    private _menuCreate: ControllerFor<'shop/menu_create'>;
    private _menuUpdate: ControllerFor<'shop/menu_update'>;
    private _menuSetStatus: ControllerFor<'shop/menu_set_status'>;
    private _menuRemove: ControllerFor<'shop/menu_remove'>;
    private _menusReorder: ControllerFor<'shop/menus_reorder'>;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { padding: var(--space-5) var(--space-6) var(--space-10); }
            .head-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--space-3); }
            .card {
                display: flex; flex-direction: column; gap: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
            }
            .card:hover { border-color: color-mix(in srgb, var(--text-primary) 18%, transparent); }
            .card.archived { opacity: 0.7; }
            .title-row { display: flex; align-items: center; gap: var(--space-2); }
            .name {
                flex: 1; min-width: 0; text-align: left; background: none; border: none; padding: 0;
                font: inherit; font-weight: var(--font-semibold); font-size: var(--text-base);
                color: var(--text-primary); cursor: pointer;
                overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            }
            .name:hover { text-decoration: underline; }
            .status {
                font-size: var(--text-xs); font-weight: var(--font-semibold);
                padding: 1px var(--space-2); border-radius: var(--radius-full);
                background: color-mix(in srgb, currentColor 12%, transparent);
            }
            .stats { display: flex; gap: var(--space-4); color: var(--text-secondary); font-size: var(--text-sm); }
            .stats b { color: var(--text-primary); font-variant-numeric: tabular-nums; }
            .ops { display: flex; gap: var(--space-1); align-items: center; flex-wrap: wrap; }
            .ops .spacer { flex: 1; }
            platform-empty-state { margin-top: var(--space-8); }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this._shops = this.useResource('shop/shops');
        this._menus = this.useOp('shop/menus_list');
        this._menuCreate = this.useOp('shop/menu_create');
        this._menuUpdate = this.useOp('shop/menu_update');
        this._menuSetStatus = this.useOp('shop/menu_set_status');
        this._menuRemove = this.useOp('shop/menu_remove');
        this._menusReorder = this.useOp('shop/menus_reorder');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId') && this.shopId !== '') {
            this._shops.load();
            void this._menus.run({ shop_id: this.shopId });
        }
    }

    private get _rows(): ShopMenuResponse[] {
        const result = this._menus.lastResult;
        if (result === null) return [];
        return result.items.filter((menu) => menu.shop_id === this.shopId);
    }

    private _shopHead(): ShopHeadRow | null {
        return shopHeadRow(this._shops.items.find((shop) => shop.shop_id === this.shopId));
    }

    private _statusLabel(status: ShopMenuStatus): string {
        switch (status) {
            case 'draft': return this.t('menu_status.draft');
            case 'active': return this.t('menu_status.active');
            case 'archived': return this.t('menu_status.archived');
        }
    }

    private _open(menu: ShopMenuResponse): void {
        this.navigate('shop_menu', { shopId: this.shopId, menuId: menu.shop_menu_id });
    }

    private async _create(): Promise<void> {
        const name = await platformPrompt(this.t('menus.create_message'), {
            title: this.t('menus.create_title'),
            inputLabel: this.t('menus.field_name'),
            inputValue: '',
            confirmText: this.t('menus.create'),
        });
        if (name === undefined || name.trim() === '') return;
        const created = await this._menuCreate.run({ shop_id: this.shopId, name: name.trim() });
        if (created !== null) {
            this.navigate('shop_menu', { shopId: this.shopId, menuId: created.shop_menu_id });
        }
    }

    private async _rename(menu: ShopMenuResponse): Promise<void> {
        const name = await platformPrompt(this.t('menus.rename_message'), {
            title: this.t('menus.rename_title'),
            inputLabel: this.t('menus.field_name'),
            inputValue: menu.name,
            confirmText: this.t('menus.save'),
        });
        if (name === undefined || name.trim() === '' || name.trim() === menu.name) return;
        await this._menuUpdate.run({ shop_id: this.shopId, shop_menu_id: menu.shop_menu_id, name: name.trim() });
    }

    private async _setStatus(menu: ShopMenuResponse, status: ShopMenuStatus): Promise<void> {
        await this._menuSetStatus.run({ shop_id: this.shopId, shop_menu_id: menu.shop_menu_id, status });
    }

    private async _remove(menu: ShopMenuResponse): Promise<void> {
        const confirmed = await platformConfirm(this.t('menus.remove_confirm', { name: menu.name }), {
            title: this.t('menus.remove_title'),
            variant: 'warning',
            confirmText: this.t('menus.remove'),
            cancelText: this.t('product.cancel'),
        });
        if (confirmed !== true) return;
        await this._menuRemove.run({ shop_id: this.shopId, shop_menu_id: menu.shop_menu_id });
    }

    private async _move(index: number, direction: -1 | 1): Promise<void> {
        const ids = this._rows.map((menu) => menu.shop_menu_id);
        const current = ids[index];
        const swap = ids[index + direction];
        if (current === undefined || swap === undefined) return;
        ids[index] = swap;
        ids[index + direction] = current;
        await this._menusReorder.run({ shop_id: this.shopId, shop_menu_ids: ids });
    }

    private _renderStatusAction(menu: ShopMenuResponse): TemplateResult {
        switch (menu.status) {
            case 'draft':
                return html`
                    <platform-button size="sm" variant="primary" ?disabled=${menu.items.length === 0}
                        title=${menu.items.length === 0 ? this.t('menus.activate_empty') : this.t('menus.activate_hint')}
                        @click=${() => this._setStatus(menu, 'active')}>${this.t('menus.activate')}</platform-button>`;
            case 'active':
                return html`
                    <platform-button size="sm" variant="secondary"
                        @click=${() => this._setStatus(menu, 'archived')}>${this.t('menus.archive')}</platform-button>`;
            case 'archived':
                return html`
                    <platform-button size="sm" variant="secondary"
                        @click=${() => this._setStatus(menu, 'draft')}>${this.t('menus.restore')}</platform-button>`;
        }
    }

    private _renderCard(menu: ShopMenuResponse, index: number, total: number): TemplateResult {
        return html`
            <article class="card ${menu.status}">
                <div class="title-row">
                    <button type="button" class="name" title=${this.t('menus.open')} @click=${() => this._open(menu)}>${menu.name}</button>
                    <span class="status" style="color:${STATUS_TONES[menu.status]}">${this._statusLabel(menu.status)}</span>
                </div>
                <div class="stats">
                    <span>${this.t('menus.sections_count')}: <b>${menu.sections.length}</b></span>
                    <span>${this.t('menus.items_count')}: <b>${menu.items.length}</b></span>
                </div>
                <div class="ops">
                    ${this._renderStatusAction(menu)}
                    <span class="spacer"></span>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menus.move_up')}
                        ?loading=${this._menusReorder.busy} ?disabled=${index === 0} @click=${() => this._move(index, -1)}
                    ><platform-icon name="chevron-up" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menus.move_down')}
                        ?loading=${this._menusReorder.busy} ?disabled=${index === total - 1} @click=${() => this._move(index, 1)}
                    ><platform-icon name="chevron-down" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menus.rename')}
                        @click=${() => this._rename(menu)}
                    ><platform-icon name="edit" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost-danger" title=${this.t('menus.remove')}
                        @click=${() => this._remove(menu)}
                    ><platform-icon name="trash" size="14"></platform-icon></platform-button>
                </div>
            </article>
        `;
    }

    private _renderList(): TemplateResult {
        const rows = this._rows;
        if (this._menus.lastResult === null || (this._menus.busy && rows.length === 0)) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        if (rows.length === 0) {
            return html`<platform-empty-state icon="book-open" title=${this.t('menus.empty')} hint=${this.t('menus.empty_hint')}></platform-empty-state>`;
        }
        return html`<div class="grid">${rows.map((menu, index) => this._renderCard(menu, index, rows.length))}</div>`;
    }

    override render(): TemplateResult {
        return html`
            <div class="wrap">
                <shop-page-head .shop=${this._shopHead()} shop-id=${this.shopId} section=${this.t('routes.shop_menus')}>
                    <div slot="actions" class="head-actions">
                        <platform-button size="sm" variant="accent"
                            @click=${() => this.openModal('shop.menu_template', { shopId: this.shopId })}>
                            <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menus.template')}
                        </platform-button>
                        <platform-button size="sm" variant="secondary"
                            @click=${() => this.openModal('shop.menu_import', { shopId: this.shopId, target: 'new_menu', shopMenuId: null })}>
                            <platform-icon name="import" size="14"></platform-icon> ${this.t('menus.import')}
                        </platform-button>
                        <platform-button size="sm" variant="primary" ?loading=${this._menuCreate.busy} @click=${() => this._create()}>
                            <platform-icon name="plus" size="14"></platform-icon> ${this.t('menus.create')}
                        </platform-button>
                    </div>
                </shop-page-head>
                <shop-agent-jobs-banner shop-id=${this.shopId}></shop-agent-jobs-banner>
                ${this._renderList()}
            </div>
        `;
    }
}

customElements.define('shop-menus-page', ShopMenusPage);
