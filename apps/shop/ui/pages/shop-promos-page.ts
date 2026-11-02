/**
 * Акции магазина: конструктор шаблонов без JSON.
 *
 * Директор выбирает шаблон («2+1», «комбо», «скидка %», «бесплатная
 * доставка от N₽») — страница собирает polymorphic condition/action,
 * который исполняет PromoEngine на сервере. Список живёт в `lastResult`
 * опа `shop/promos_list`: `shop/catalog/changed` перезапускает его.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

const TEMPLATES = [
    'percent_order',
    'percent_items',
    'amount_order',
    'n_plus_m_free',
    'fixed_bundle_price',
    'free_delivery',
] as const;
type Template = (typeof TEMPLATES)[number];

const CONDS = ['always', 'min_total', 'min_qty', 'items_present'] as const;
type CondType = (typeof CONDS)[number];

interface PromoRow {
    shop_promo_id: string;
    name: string;
    is_active: boolean;
    sort: number;
    priority: number;
    stacking: string;
    window: Record<string, unknown>;
    condition: Record<string, unknown>;
    action: Record<string, unknown>;
}

interface ProductRow {
    shop_product_id: string;
    name: string;
    price_minor: number;
}

interface BundleItem {
    product_id: string;
    qty: number;
}

interface Draft {
    id: string | null;
    name: string;
    template: Template;
    pct: string;
    amount: string;
    n: string;
    m: string;
    price: string;
    scopeIds: Set<string>;
    bundle: BundleItem[];
    condType: CondType;
    condMinor: string;
    condN: string;
    condIds: Set<string>;
    scheduleOn: boolean;
    weekdays: Set<number>;
    timeFrom: string;
    timeTo: string;
    priority: string;
    stacking: 'all' | 'exclusive';
    isActive: boolean;
}

function _str(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

function _rubles(minor: number): string {
    return (minor / 100).toString();
}

function _toMinor(raw: string): number {
    const v = Math.round(parseFloat(raw.replace(',', '.')) * 100);
    return Number.isFinite(v) && v >= 0 ? v : 0;
}

function _ids(v: unknown): string[] {
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

export class ShopPromosPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _promosOp: OpController;
    private _productsOp: OpController;
    private _createOp: OpController;
    private _updateOp: OpController;
    private _removeOp: OpController;
    private _locale: SelectController<string>;

    declare _draft: Draft | null;

    static override properties: PropertyDeclarations = {
        shopId: { type: String, attribute: 'shop-id' },
        _draft: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .wrap { height: 100%; overflow-y: auto; padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-4); max-width: 860px; }
            .head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
            h1 { margin: 0; font-size: var(--text-2xl); color: var(--text-primary); }
            .card {
                background: var(--bg-surface);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                display: flex; flex-direction: column; gap: var(--space-3);
            }
            .row { display: flex; gap: var(--space-2); align-items: end; flex-wrap: wrap; }
            .row platform-field { flex: 1; min-width: 130px; }
            .sec-title { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .chips { display: flex; gap: var(--space-1); flex-wrap: wrap; }
            .chip {
                border: 1px solid var(--glass-border-subtle); border-radius: 999px;
                padding: 4px 12px; font-size: var(--text-xs); cursor: pointer;
                background: transparent; color: var(--text-secondary); font: inherit;
            }
            .chip.on { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
            .bundle-row { display: flex; gap: var(--space-2); align-items: end; }
            .bundle-row platform-field:first-child { flex: 3; }
            .bundle-row platform-field:last-of-type { flex: 1; min-width: 80px; }
            .promo { display: flex; align-items: center; gap: var(--space-3); }
            .promo .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
            .promo .name { font-weight: var(--font-semibold); color: var(--text-primary); }
            .promo .desc { font-size: var(--text-xs); color: var(--text-tertiary); }
            .badges { display: flex; gap: var(--space-1); }
            .badge {
                font-size: var(--text-xs); padding: 2px 8px; border-radius: 999px;
                background: color-mix(in srgb, var(--text-primary) 8%, transparent);
                color: var(--text-secondary); white-space: nowrap;
            }
            .badge.off { background: color-mix(in srgb, var(--text-primary) 5%, transparent); color: var(--text-tertiary); }
            .badge.excl { background: color-mix(in srgb, var(--warning) 18%, transparent); color: var(--warning); }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._draft = null;
        this._promosOp = this.useOp('shop/promos_list');
        this._productsOp = this.useOp('shop/products_list');
        this._createOp = this.useOp('shop/promo_create');
        this._updateOp = this.useOp('shop/promo_update');
        this._removeOp = this.useOp('shop/promo_remove');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    async onRouteActive(): Promise<void> {
        if (this.shopId === '') return;
        await Promise.all([
            this._promosOp.run({ shop_id: this.shopId }),
            this._productsOp.run({ shop_id: this.shopId, limit: 500 }),
        ]);
    }

    private _promos(): PromoRow[] {
        const result = this._promosOp.lastResult as { promos?: PromoRow[] } | null;
        return Array.isArray(result?.promos) ? result.promos : [];
    }

    private _products(): ProductRow[] {
        const result = this._productsOp.lastResult as { items?: ProductRow[] } | null;
        return Array.isArray(result?.items) ? result.items : [];
    }

    private _money(minor: number): string {
        return formatPlatformNumber(minor / 100, this._locale.value, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    private _newDraft(): Draft {
        return {
            id: null, name: '', template: 'percent_order',
            pct: '10', amount: '', n: '2', m: '1', price: '',
            scopeIds: new Set(), bundle: [{ product_id: '', qty: 1 }],
            condType: 'always', condMinor: '', condN: '', condIds: new Set(),
            scheduleOn: false, weekdays: new Set([0, 1, 2, 3, 4, 5, 6]),
            timeFrom: '12:00', timeTo: '16:00',
            priority: '0', stacking: 'all', isActive: true,
        };
    }

    private _draftFrom(p: PromoRow): Draft {
        const d = this._newDraft();
        const a = p.action;
        const c = p.condition;
        const w = p.window;
        d.id = p.shop_promo_id;
        d.name = p.name;
        d.template = (TEMPLATES as readonly string[]).includes(String(a.type)) ? (a.type as Template) : 'percent_order';
        d.pct = String(a.pct ?? 10);
        d.amount = _rubles(Number(a.minor ?? 0));
        d.n = String(a.n ?? 2);
        d.m = String(a.m ?? 1);
        d.price = _rubles(Number(a.price_minor ?? 0));
        d.scopeIds = new Set(_ids(a.product_ids));
        const items = Array.isArray(a.items) ? a.items : [];
        d.bundle = items.length
            ? items.map((it) => ({
                product_id: typeof (it as Record<string, unknown>).product_id === 'string' ? (it as { product_id: string }).product_id : '',
                qty: Number((it as Record<string, unknown>).qty ?? 1) || 1,
            }))
            : [{ product_id: '', qty: 1 }];
        const ct = String(c.type ?? 'always');
        d.condType = (CONDS as readonly string[]).includes(ct) ? (ct as CondType) : 'always';
        d.condMinor = _rubles(Number(c.minor ?? 0));
        d.condN = String(c.n ?? '');
        d.condIds = new Set(_ids(c.product_ids));
        const wd = Array.isArray(w.weekdays) ? w.weekdays : null;
        const tf = typeof w.time_from === 'string' ? w.time_from : '';
        const tt = typeof w.time_to === 'string' ? w.time_to : '';
        d.scheduleOn = wd !== null || tf !== '' || tt !== ''
            || typeof w.starts_at === 'string' || typeof w.ends_at === 'string';
        if (wd !== null) d.weekdays = new Set(wd.map((x) => Number(x)));
        if (tf !== '') d.timeFrom = tf;
        if (tt !== '') d.timeTo = tt;
        d.priority = String(p.priority);
        d.stacking = p.stacking === 'exclusive' ? 'exclusive' : 'all';
        d.isActive = p.is_active;
        return d;
    }

    private _buildAction(d: Draft): Record<string, unknown> | null {
        switch (d.template) {
            case 'percent_order': {
                const pct = parseInt(d.pct, 10);
                return pct > 0 && pct < 100 ? { type: 'percent_order', pct } : null;
            }
            case 'percent_items': {
                const pct = parseInt(d.pct, 10);
                if (!(pct > 0 && pct < 100)) return null;
                const ids = [...d.scopeIds];
                return ids.length ? { type: 'percent_items', pct, product_ids: ids } : { type: 'percent_items', pct };
            }
            case 'amount_order': {
                const minor = _toMinor(d.amount);
                return minor > 0 ? { type: 'amount_order', minor } : null;
            }
            case 'n_plus_m_free': {
                const n = parseInt(d.n, 10);
                const m = parseInt(d.m, 10);
                if (!(n > 0 && m > 0)) return null;
                const ids = [...d.scopeIds];
                return ids.length
                    ? { type: 'n_plus_m_free', n, m, product_ids: ids }
                    : { type: 'n_plus_m_free', n, m };
            }
            case 'fixed_bundle_price': {
                const price = _toMinor(d.price);
                const items = d.bundle
                    .filter((it) => it.product_id !== '' && it.qty > 0)
                    .map((it) => ({ product_id: it.product_id, qty: it.qty }));
                return price > 0 && items.length >= 2
                    ? { type: 'fixed_bundle_price', price_minor: price, items }
                    : null;
            }
            case 'free_delivery':
                return { type: 'free_delivery' };
        }
    }

    private _buildCondition(d: Draft): Record<string, unknown> | null {
        switch (d.condType) {
            case 'always':
                return { type: 'always' };
            case 'min_total': {
                const minor = _toMinor(d.condMinor);
                return minor > 0 ? { type: 'min_total', minor } : null;
            }
            case 'min_qty': {
                const n = parseInt(d.condN, 10);
                return n > 0 ? { type: 'min_qty', n } : null;
            }
            case 'items_present': {
                const ids = [...d.condIds];
                return ids.length ? { type: 'items_present', product_ids: ids } : null;
            }
        }
    }

    private _buildWindow(d: Draft): Record<string, unknown> {
        if (!d.scheduleOn) return {};
        const window: Record<string, unknown> = {};
        if (d.weekdays.size < 7) window.weekdays = [...d.weekdays].sort();
        if (d.timeFrom !== '' && d.timeTo !== '') {
            window.time_from = d.timeFrom;
            window.time_to = d.timeTo;
        }
        return window;
    }

    private async _save() {
        const d = this._draft;
        if (d === null) return;
        const action = this._buildAction(d);
        const condition = this._buildCondition(d);
        if (d.name.trim() === '' || action === null || condition === null) return;
        const body = {
            name: d.name.trim(),
            is_active: d.isActive,
            priority: parseInt(d.priority, 10) || 0,
            stacking: d.stacking,
            window: this._buildWindow(d),
            condition,
            action,
        };
        const result = d.id === null
            ? await this._createOp.run({ shop_id: this.shopId, ...body })
            : await this._updateOp.run({ shop_id: this.shopId, shop_promo_id: d.id, ...body });
        if (result !== null) this._draft = null;
    }

    private async _toggle(p: PromoRow, checked: boolean) {
        await this._updateOp.run({
            shop_id: this.shopId, shop_promo_id: p.shop_promo_id, is_active: checked,
        });
    }

    private _describe(p: PromoRow): string {
        const a = p.action;
        const t = String(a.type);
        if (t === 'percent_order') return this.t('promos.desc.percent_order', { pct: String(a.pct ?? 0) });
        if (t === 'percent_items') return this.t('promos.desc.percent_items', { pct: String(a.pct ?? 0) });
        if (t === 'amount_order') return this.t('promos.desc.amount_order', { sum: this._money(Number(a.minor ?? 0)) });
        if (t === 'n_plus_m_free') return this.t('promos.desc.n_plus_m', { n: String(a.n ?? 0), m: String(a.m ?? 0) });
        if (t === 'fixed_bundle_price') return this.t('promos.desc.bundle', { sum: this._money(Number(a.price_minor ?? 0)) });
        if (t === 'free_delivery') return this.t('promos.desc.free_delivery');
        return t;
    }

    private _condDescribe(p: PromoRow): string {
        const c = p.condition;
        const t = String(c.type ?? 'always');
        if (t === 'min_total') return this.t('promos.cond_desc.min_total', { sum: this._money(Number(c.minor ?? 0)) });
        if (t === 'min_qty') return this.t('promos.cond_desc.min_qty', { n: String(c.n ?? 0) });
        if (t === 'items_present') return this.t('promos.cond_desc.items_present');
        return '';
    }

    private _chips(all: ProductRow[], selected: Set<string>, onToggle: (id: string) => void) {
        return html`<div class="chips">
            ${all.map((p) => html`
                <button class="chip ${selected.has(p.shop_product_id) ? 'on' : ''}"
                    @click=${() => onToggle(p.shop_product_id)}>${p.name}</button>
            `)}
        </div>`;
    }

    private _toggleIn(set: Set<string>, id: string) {
        if (set.has(id)) set.delete(id); else set.add(id);
        this.requestUpdate();
    }

    private _patchDraft(patch: Partial<Draft>) {
        if (this._draft === null) return;
        this._draft = { ...this._draft, ...patch };
    }

    private _editor() {
        const d = this._draft;
        if (d === null) return nothing;
        const products = this._products();
        const needsScope = d.template === 'percent_items' || d.template === 'n_plus_m_free';
        return html`
            <div class="card">
                <div class="sec-title">${d.id === null ? this.t('promos.new') : this.t('promos.edit_title')}</div>
                <div class="row">
                    <platform-field type="string" mode="edit" label=${this.t('promos.field_name')} .value=${d.name}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ name: _str(e) })}></platform-field>
                    <platform-field type="enum" mode="edit" label=${this.t('promos.template')} .value=${d.template}
                        .config=${{ values: TEMPLATES.map((tp) => ({ value: tp, label: this.t(`promos.tpl.${tp}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ template: _str(e) as Template })}></platform-field>
                </div>
                <div class="row">
                    ${d.template === 'percent_order' || d.template === 'percent_items' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.field_pct')} .value=${d.pct}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ pct: _str(e) })}></platform-field>` : nothing}
                    ${d.template === 'amount_order' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.field_amount')} .value=${d.amount}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ amount: _str(e) })}></platform-field>` : nothing}
                    ${d.template === 'n_plus_m_free' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.field_n')} .value=${d.n}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ n: _str(e) })}></platform-field>
                        <platform-field type="number" mode="edit" label=${this.t('promos.field_m')} .value=${d.m}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ m: _str(e) })}></platform-field>` : nothing}
                    ${d.template === 'fixed_bundle_price' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.field_price')} .value=${d.price}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ price: _str(e) })}></platform-field>` : nothing}
                </div>
                ${d.template === 'fixed_bundle_price' ? html`
                    <div class="sec-title">${this.t('promos.bundle_items')}</div>
                    ${d.bundle.map((it, idx) => html`
                        <div class="bundle-row">
                            <platform-field type="enum" mode="edit" .value=${it.product_id}
                                .config=${{ values: products.map((p) => ({ value: p.shop_product_id, label: p.name })) }}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                    const bundle = d.bundle.map((x, i) => i === idx ? { ...x, product_id: _str(e) } : x);
                                    this._patchDraft({ bundle });
                                }}></platform-field>
                            <platform-field type="number" mode="edit" .value=${String(it.qty)}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                    const qty = parseInt(_str(e), 10) || 1;
                                    const bundle = d.bundle.map((x, i) => i === idx ? { ...x, qty } : x);
                                    this._patchDraft({ bundle });
                                }}></platform-field>
                            <platform-button size="sm" variant="secondary"
                                @click=${() => this._patchDraft({ bundle: d.bundle.filter((_, i) => i !== idx) })}>
                                <platform-icon name="close" size="14"></platform-icon></platform-button>
                        </div>`)}
                    <platform-button size="sm" variant="secondary"
                        @click=${() => this._patchDraft({ bundle: [...d.bundle, { product_id: '', qty: 1 }] })}>
                        ${this.t('promos.bundle_add')}</platform-button>` : nothing}
                ${needsScope ? html`
                    <div class="sec-title">${this.t('promos.scope')}</div>
                    <div class="hint">${this.t('promos.scope_hint')}</div>
                    ${this._chips(products, d.scopeIds, (id) => this._toggleIn(d.scopeIds, id))}` : nothing}
                <div class="row">
                    <platform-field type="enum" mode="edit" label=${this.t('promos.condition')} .value=${d.condType}
                        .config=${{ values: CONDS.map((c) => ({ value: c, label: this.t(`promos.cond.${c}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ condType: _str(e) as CondType })}></platform-field>
                    ${d.condType === 'min_total' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.cond_sum')} .value=${d.condMinor}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ condMinor: _str(e) })}></platform-field>` : nothing}
                    ${d.condType === 'min_qty' ? html`
                        <platform-field type="number" mode="edit" label=${this.t('promos.cond_n')} .value=${d.condN}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ condN: _str(e) })}></platform-field>` : nothing}
                </div>
                ${d.condType === 'items_present' ? this._chips(products, d.condIds, (id) => this._toggleIn(d.condIds, id)) : nothing}
                <div class="row">
                    <platform-switch ?checked=${d.scheduleOn} label=${this.t('promos.schedule')}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ scheduleOn: Boolean(e.detail.value) })}></platform-switch>
                    ${d.scheduleOn ? html`
                        <platform-field type="string" mode="edit" label=${this.t('promos.time_from')} .value=${d.timeFrom}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ timeFrom: _str(e) })}></platform-field>
                        <platform-field type="string" mode="edit" label=${this.t('promos.time_to')} .value=${d.timeTo}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ timeTo: _str(e) })}></platform-field>` : nothing}
                </div>
                ${d.scheduleOn ? html`
                    <div class="chips">
                        ${[0, 1, 2, 3, 4, 5, 6].map((day) => html`
                            <button class="chip ${d.weekdays.has(day) ? 'on' : ''}"
                                @click=${() => {
                                    if (d.weekdays.has(day)) d.weekdays.delete(day); else d.weekdays.add(day);
                                    this.requestUpdate();
                                }}>${this.t(`settings.day_${day}`)}</button>`)}
                    </div>` : nothing}
                <div class="row">
                    <platform-field type="number" mode="edit" label=${this.t('promos.priority')} .value=${d.priority}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ priority: _str(e) })}></platform-field>
                    <platform-field type="enum" mode="edit" label=${this.t('promos.stacking')} .value=${d.stacking}
                        .config=${{ values: [
                            { value: 'all', label: this.t('promos.stacking_all') },
                            { value: 'exclusive', label: this.t('promos.stacking_exclusive') },
                        ] }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ stacking: _str(e) === 'exclusive' ? 'exclusive' : 'all' })}></platform-field>
                    <platform-switch ?checked=${d.isActive} label=${this.t('promos.active')}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._patchDraft({ isActive: Boolean(e.detail.value) })}></platform-switch>
                </div>
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => { this._draft = null; }}>${this.t('promos.cancel')}</platform-button>
                    <platform-button variant="primary" ?busy=${this._createOp.busy || this._updateOp.busy}
                        @click=${() => void this._save()}>${this.t('promos.save')}</platform-button>
                </div>
            </div>
        `;
    }

    private _card(p: PromoRow) {
        const cond = this._condDescribe(p);
        const w = p.window;
        const scheduled = Object.keys(w).length > 0;
        return html`
            <div class="card promo">
                <div class="info">
                    <span class="name">${p.name}</span>
                    <span class="desc">${this._describe(p)}${cond === '' ? '' : ` · ${cond}`}</span>
                </div>
                <div class="badges">
                    ${p.is_active ? nothing : html`<span class="badge off">${this.t('promos.off')}</span>`}
                    ${p.stacking === 'exclusive' ? html`<span class="badge excl">${this.t('promos.stacking_exclusive')}</span>` : nothing}
                    ${scheduled ? html`<span class="badge">${this.t('promos.scheduled')}</span>` : nothing}
                </div>
                <platform-switch ?checked=${p.is_active} ?busy=${this._updateOp.busy}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => void this._toggle(p, Boolean(e.detail.value))}></platform-switch>
                <platform-button size="sm" variant="secondary"
                    @click=${() => { this._draft = this._draftFrom(p); }}>${this.t('promos.edit')}</platform-button>
                <platform-button size="sm" variant="secondary" ?busy=${this._removeOp.busy}
                    @click=${() => void this._removeOp.run({ shop_id: this.shopId, shop_promo_id: p.shop_promo_id })}>
                    <platform-icon name="trash" size="14"></platform-icon></platform-button>
            </div>
        `;
    }

    override render() {
        const promos = this._promos();
        return html`
            <div class="wrap">
                <div class="head">
                    <h1>${this.t('promos.title')}</h1>
                    ${this._draft === null ? html`
                        <platform-button variant="primary" @click=${() => { this._draft = this._newDraft(); }}>
                            ${this.t('promos.new')}</platform-button>` : nothing}
                </div>
                <div class="hint">${this.t('promos.hint')}</div>
                ${this._editor()}
                ${promos.length === 0 && this._draft === null
                    ? html`<platform-empty-state .text=${this.t('promos.empty')}></platform-empty-state>`
                    : promos.map((p) => this._card(p))}
            </div>
        `;
    }
}

customElements.define('shop-promos-page', ShopPromosPage);
