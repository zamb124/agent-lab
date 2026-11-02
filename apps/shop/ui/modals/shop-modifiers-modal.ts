/**
 * ShopModifiersModal — редактор групп модификаторов товара.
 *
 * Поток:
 *   1. `modifier_groups_list` грузит библиотеку групп магазина (с product_ids).
 *   2. Прикреплённые к товару группы — сверху, библиотека — ниже с «Прикрепить».
 *   3. Группа раскрывается: настройки (режим, лимиты, цена) + опции
 *      (имя, цена, default, доступность, удалить) + inline-добавление.
 *   4. «AI-предложить» — `ai_suggest_options` по названию блюда, найденные
 *      опции создаются в группе одним проходом.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

interface OptionRow {
    shop_modifier_option_id: string;
    name: string;
    price_minor: number;
    is_default: boolean;
    is_available: boolean;
    max_per_option: number;
    nested_group_id: string | null;
}

interface GroupRow {
    shop_modifier_group_id: string;
    name: string;
    kind: string;
    selection_mode: string;
    min_selected: number;
    max_selected: number | null;
    price_mode: string;
    is_active: boolean;
    product_ids: string[];
    options: OptionRow[];
}

interface SuggestionItem {
    name: string;
    price_minor: number;
}

function _str(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

export class ShopModifiersModal extends PlatformModal {
    static modalKind = 'shop.modifiers';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare productId: string;
    declare productName: string;

    private _groupsOp: OpController;
    private _groupCreateOp: OpController;
    private _groupUpdateOp: OpController;
    private _groupRemoveOp: OpController;
    private _optionCreateOp: OpController;
    private _optionUpdateOp: OpController;
    private _optionRemoveOp: OpController;
    private _attachOp: OpController;
    private _detachOp: OpController;
    private _suggestOp: OpController;
    private _locale: SelectController<string>;

    private _groups: GroupRow[] = [];
    private _openGroupId = '';
    private _newGroupName = '';
    private _newOptionName = '';
    private _newOptionPrice = '';
    private _suggestBusyFor = '';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        productId: { type: String, attribute: 'product-id' },
        productName: { type: String, attribute: 'product-name' },
        _groups: { state: true },
        _openGroupId: { state: true },
        _newGroupName: { state: true },
        _newOptionName: { state: true },
        _newOptionPrice: { state: true },
        _suggestBusyFor: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
            .create-row { display: flex; gap: var(--space-2); align-items: end; }
            .create-row platform-field { flex: 1; }
            .group {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: hidden;
            }
            .group.attached { border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
            .group-head {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-3);
                cursor: pointer;
            }
            .group-head:hover { background: color-mix(in srgb, var(--text-primary) 4%, transparent); }
            .group-head .name { flex: 1; font-weight: var(--font-semibold); color: var(--text-primary); font-size: var(--text-sm); }
            .badges { display: flex; gap: var(--space-1); flex-wrap: wrap; }
            .badge {
                font-size: var(--text-xs); padding: 2px 8px; border-radius: 999px;
                background: color-mix(in srgb, var(--text-primary) 8%, transparent);
                color: var(--text-secondary); white-space: nowrap;
            }
            .badge.req { background: color-mix(in srgb, var(--warning) 18%, transparent); color: var(--warning); }
            .badge.abs { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); }
            .group-body { border-top: 1px solid var(--glass-border-subtle); padding: var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
            .settings { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--space-2); align-items: end; }
            .opt-row {
                display: grid; grid-template-columns: 2fr 90px auto auto auto;
                gap: var(--space-2); align-items: center;
                padding: var(--space-1) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .opt-row:last-child { border-bottom: 0; }
            .opt-add { display: grid; grid-template-columns: 2fr 90px auto; gap: var(--space-2); align-items: end; margin-top: var(--space-2); }
            .sec-title { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .group-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            .lib-note { font-size: var(--text-xs); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._groupsOp = this.useOp('shop/modifier_groups_list');
        this._groupCreateOp = this.useOp('shop/modifier_group_create');
        this._groupUpdateOp = this.useOp('shop/modifier_group_update');
        this._groupRemoveOp = this.useOp('shop/modifier_group_remove');
        this._optionCreateOp = this.useOp('shop/modifier_option_create');
        this._optionUpdateOp = this.useOp('shop/modifier_option_update');
        this._optionRemoveOp = this.useOp('shop/modifier_option_remove');
        this._attachOp = this.useOp('shop/product_modifier_attach');
        this._detachOp = this.useOp('shop/product_modifier_detach');
        this._suggestOp = this.useOp('shop/ai_suggest_options');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopModifiersModal: prop "shopId" required');
        }
        if (typeof this.productId !== 'string' || this.productId.length === 0) {
            throw new Error('ShopModifiersModal: prop "productId" required');
        }
        void this._reload();
    }

    private async _reload() {
        const result = await this._groupsOp.run({ shop_id: this.shopId });
        if (result !== null && typeof result === 'object' && 'groups' in (result as Record<string, unknown>)) {
            const groups = (result as { groups?: unknown }).groups;
            this._groups = Array.isArray(groups) ? (groups as GroupRow[]) : [];
        }
    }

    private _money(minor: number): string {
        return formatPlatformNumber(minor / 100, this._locale.value, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    private _attached(g: GroupRow): boolean {
        return g.product_ids.includes(this.productId);
    }

    private async _createGroup() {
        const name = this._newGroupName.trim();
        if (name === '') return;
        const result = await this._groupCreateOp.run({ shop_id: this.shopId, name });
        if (result !== null) {
            this._newGroupName = '';
            const created = result as Record<string, unknown>;
            if (typeof created.shop_modifier_group_id === 'string') this._openGroupId = created.shop_modifier_group_id;
            await this._reload();
        }
    }

    private async _patchGroup(g: GroupRow, patch: Record<string, unknown>) {
        await this._groupUpdateOp.run({
            shop_id: this.shopId,
            shop_modifier_group_id: g.shop_modifier_group_id,
            ...patch,
        });
        await this._reload();
    }

    private async _removeGroup(g: GroupRow) {
        await this._groupRemoveOp.run({
            shop_id: this.shopId,
            shop_modifier_group_id: g.shop_modifier_group_id,
        });
        await this._reload();
    }

    private async _attach(g: GroupRow) {
        await this._attachOp.run({
            shop_id: this.shopId,
            product_id: this.productId,
            group_id: g.shop_modifier_group_id,
        });
        await this._reload();
    }

    private async _detach(g: GroupRow) {
        await this._detachOp.run({
            shop_id: this.shopId,
            product_id: this.productId,
            group_id: g.shop_modifier_group_id,
        });
        await this._reload();
    }

    private async _addOption(g: GroupRow) {
        const name = this._newOptionName.trim();
        const price = Math.round(parseFloat(this._newOptionPrice.replace(',', '.') || '0') * 100);
        if (name === '' || !Number.isFinite(price) || price < 0) return;
        const result = await this._optionCreateOp.run({
            shop_id: this.shopId,
            group_id: g.shop_modifier_group_id,
            name,
            price_minor: price,
        });
        if (result !== null) {
            this._newOptionName = '';
            this._newOptionPrice = '';
            await this._reload();
        }
    }

    private async _patchOption(o: OptionRow, patch: Record<string, unknown>) {
        await this._optionUpdateOp.run({
            shop_id: this.shopId,
            shop_modifier_option_id: o.shop_modifier_option_id,
            ...patch,
        });
        await this._reload();
    }

    private async _removeOption(o: OptionRow) {
        await this._optionRemoveOp.run({
            shop_id: this.shopId,
            shop_modifier_option_id: o.shop_modifier_option_id,
        });
        await this._reload();
    }

    private async _suggest(g: GroupRow) {
        this._suggestBusyFor = g.shop_modifier_group_id;
        try {
            const result = await this._suggestOp.run({
                shop_id: this.shopId,
                product_name: this.productName,
                group_name: g.name,
            });
            if (result !== null && typeof result === 'object' && 'items' in (result as Record<string, unknown>)) {
                const items = (result as { items?: unknown }).items;
                if (Array.isArray(items)) {
                    for (const item of items as SuggestionItem[]) {
                        await this._optionCreateOp.run({
                            shop_id: this.shopId,
                            group_id: g.shop_modifier_group_id,
                            name: item.name,
                            price_minor: item.price_minor,
                        });
                    }
                }
            }
        } finally {
            this._suggestBusyFor = '';
            await this._reload();
        }
    }

    private _badges(g: GroupRow): TemplateResult {
        const parts: TemplateResult[] = [];
        if (g.min_selected > 0) parts.push(html`<span class="badge req">${this.t('modifiers.required')}</span>`);
        if (g.price_mode === 'absolute') parts.push(html`<span class="badge abs">${this.t('modifiers.variant')}</span>`);
        if (g.kind === 'remove') parts.push(html`<span class="badge">${this.t('modifiers.remove_kind')}</span>`);
        parts.push(html`<span class="badge">${g.selection_mode === 'single' ? this.t('modifiers.single') : this.t('modifiers.multi')}</span>`);
        if (g.max_selected !== null) parts.push(html`<span class="badge">≤ ${g.max_selected}</span>`);
        return html`${parts}`;
    }

    private _renderGroup(g: GroupRow): TemplateResult {
        const attached = this._attached(g);
        const open = this._openGroupId === g.shop_modifier_group_id;
        return html`
            <div class="group ${attached ? 'attached' : ''}">
                <div class="group-head" @click=${() => { this._openGroupId = open ? '' : g.shop_modifier_group_id; }}>
                    <platform-icon name=${open ? 'chevron-down' : 'chevron-right'} size="14"></platform-icon>
                    <span class="name">${g.name}</span>
                    <span class="badges">${this._badges(g)}</span>
                    ${attached
                        ? html`<platform-button size="sm" variant="ghost" @click=${(e: Event) => { e.stopPropagation(); void this._detach(g); }}>${this.t('modifiers.detach')}</platform-button>`
                        : html`<platform-button size="sm" @click=${(e: Event) => { e.stopPropagation(); void this._attach(g); }}>${this.t('modifiers.attach')}</platform-button>`}
                </div>
                ${open ? this._renderGroupBody(g, attached) : ''}
            </div>`;
    }

    private _renderGroupBody(g: GroupRow, attached: boolean): TemplateResult {
        const priceLabel = g.price_mode === 'absolute' ? this.t('modifiers.price_abs') : this.t('modifiers.price_delta');
        return html`
            <div class="group-body">
                <div class="settings">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('modifiers.field_name')}
                        .value=${g.name}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const v = _str(e).trim();
                            if (v !== '') void this._patchGroup(g, { name: v });
                        }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('modifiers.field_selection')}
                        .value=${g.selection_mode}
                        .config=${{ values: [
                            { value: 'single', label: this.t('modifiers.single') },
                            { value: 'multi', label: this.t('modifiers.multi') },
                        ] }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const v = _str(e);
                            if (v === 'single' || v === 'multi') void this._patchGroup(g, { selection_mode: v });
                        }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('modifiers.field_min')}
                        .value=${String(g.min_selected)}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const v = parseInt(_str(e), 10);
                            if (Number.isFinite(v) && v >= 0) void this._patchGroup(g, { min_selected: v });
                        }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('modifiers.field_max')}
                        .value=${g.max_selected === null ? '' : String(g.max_selected)}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const raw = _str(e).trim();
                            const v = parseInt(raw, 10);
                            void this._patchGroup(g, { max_selected: raw === '' || !Number.isFinite(v) ? null : v });
                        }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('modifiers.field_price_mode')}
                        .value=${g.price_mode}
                        .config=${{ values: [
                            { value: 'delta', label: this.t('modifiers.price_delta') },
                            { value: 'absolute', label: this.t('modifiers.price_abs') },
                        ] }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const v = _str(e);
                            if (v === 'delta' || v === 'absolute') void this._patchGroup(g, { price_mode: v });
                        }}
                    ></platform-field>
                </div>
                <div class="sec-title">${this.t('modifiers.options_title')} · ${priceLabel}</div>
                ${g.options.map((o) => html`
                    <div class="opt-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            .value=${o.name}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                const v = _str(e).trim();
                                if (v !== '') void this._patchOption(o, { name: v });
                            }}
                        ></platform-field>
                        <platform-field
                            type="number"
                            mode="edit"
                            .value=${(o.price_minor / 100).toString()}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                const v = Math.round(parseFloat(_str(e).replace(',', '.')) * 100);
                                if (Number.isFinite(v) && v >= 0) void this._patchOption(o, { price_minor: v });
                            }}
                        ></platform-field>
                        <platform-switch
                            ?checked=${o.is_default}
                            title=${this.t('modifiers.is_default')}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => void this._patchOption(o, { is_default: Boolean(e.detail.value) })}
                        ></platform-switch>
                        <platform-switch
                            ?checked=${o.is_available}
                            title=${this.t('modifiers.is_available')}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => void this._patchOption(o, { is_available: Boolean(e.detail.value) })}
                        ></platform-switch>
                        <platform-button size="sm" variant="ghost" @click=${() => void this._removeOption(o)}>
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                    </div>`)}
                <div class="opt-add">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('modifiers.option_name')}
                        .value=${this._newOptionName}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newOptionName = _str(e); }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('modifiers.option_price')}
                        .value=${this._newOptionPrice}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newOptionPrice = _str(e); }}
                    ></platform-field>
                    <platform-button size="sm" ?disabled=${this._optionCreateOp.busy} @click=${() => void this._addOption(g)}>
                        ${this.t('modifiers.option_add')}
                    </platform-button>
                </div>
                <div class="group-actions">
                    <platform-button size="sm" variant="ghost" ?disabled=${this._suggestBusyFor !== ''} @click=${() => void this._suggest(g)}>
                        <platform-icon name="sparkle" size="14"></platform-icon>
                        ${this._suggestBusyFor === g.shop_modifier_group_id ? this.t('modifiers.ai_busy') : this.t('modifiers.ai_suggest')}
                    </platform-button>
                    <platform-button size="sm" variant="ghost" @click=${() => void this._removeGroup(g)}>
                        <platform-icon name="trash" size="14"></platform-icon> ${this.t('modifiers.group_remove')}
                    </platform-button>
                </div>
                ${!attached ? html`<div class="lib-note">${this.t('modifiers.library_note')}</div>` : ''}
            </div>`;
    }

    override renderHeader() {
        return this.t('modifiers.header');
    }

    override renderBody() {
        const attached = this._groups.filter((g) => this._attached(g));
        const library = this._groups.filter((g) => !this._attached(g));
        return html`
            <div class="body">
                <div class="hint">${this.t('modifiers.hint')} ${this.productName}</div>
                <div class="create-row">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('modifiers.new_group')}
                        .value=${this._newGroupName}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newGroupName = _str(e); }}
                    ></platform-field>
                    <platform-button size="sm" ?disabled=${this._groupCreateOp.busy} @click=${() => void this._createGroup()}>
                        ${this.t('modifiers.group_create')}
                    </platform-button>
                </div>
                ${this._groupsOp.busy && this._groups.length === 0
                    ? html`<div class="hint">${this.t('modifiers.loading')}</div>`
                    : html`
                        ${attached.length > 0 ? html`<div class="sec-title">${this.t('modifiers.attached_title')}</div>` : ''}
                        ${attached.map((g) => this._renderGroup(g))}
                        ${library.length > 0 ? html`<div class="sec-title">${this.t('modifiers.library_title')}</div>` : ''}
                        ${library.map((g) => this._renderGroup(g))}
                    `}
            </div>`;
    }
}

customElements.define('shop-modifiers-modal', ShopModifiersModal);
registerModalKind(ShopModifiersModal.modalKind, 'shop-modifiers-modal');
