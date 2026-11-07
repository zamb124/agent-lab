/**
 * Внешний вид витрины: тема, функциональные флаги и лента.
 *
 * Директор собирает витрину без кода: шаблон и оформление шапки,
 * акцентный цвет, флаги «включил → функционал есть» (КБЖУ, возврат
 * в наличие), полки ленты и сторис-баннеры с реордером. Живое превью
 * справа — телефон / планшет / десктоп через theme-preview query.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import '../modals/shop-shelf-modal.js';
import '../modals/shop-banner-modal.js';
import type { ShelfDraft } from '../modals/shop-shelf-modal.js';
import type { BannerDraft } from '../modals/shop-banner-modal.js';

const PRESETS = ['menu', 'grid', 'compact'] as const;

const MODES = ['dark', 'light'] as const;

const HERO_STYLES = ['card', 'cover', 'minimal'] as const;
type HeroStyle = (typeof HERO_STYLES)[number];

const BACKDROPS = ['solid', 'blur', 'gradient'] as const;
type Backdrop = (typeof BACKDROPS)[number];

const ACCENTS = ['#e2553f', '#f2a33c', '#34c47c', '#3f8cff', '#9b5de5', '#ef476f', '#111827', '#0f766e'];

const DEVICES = ['phone', 'tablet', 'desktop'] as const;
type Device = (typeof DEVICES)[number];

const DEVICE_ICONS: Record<Device, string> = { phone: 'smartphone', tablet: 'tablet', desktop: 'monitor' };

const FEATURES = ['nutrition', 'back_in_stock', 'favorites'] as const;
type FeatureKey = (typeof FEATURES)[number];

interface ShelfRow {
    shop_shelf_id: string;
    kind: string;
    layout: string;
    placement: string;
    title: string;
    subtitle: string;
    product_ids: string[];
    category_id: string | null;
    limit: number;
    sort: number;
    is_active: boolean;
}

interface BannerRow {
    shop_banner_id: string;
    title: string;
    subtitle: string;
    image_file_id: string | null;
    link: string;
    window: Record<string, unknown>;
    sort: number;
    is_active: boolean;
}

export class ShopBuilderPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _updateOp: OpController;
    private _shelvesOp: OpController;
    private _bannersOp: OpController;
    private _shelfRemoveOp: OpController;
    private _shelfReorderOp: OpController;
    private _bannerRemoveOp: OpController;
    private _bannerReorderOp: OpController;
    declare _preset: string;
    declare _accent: string;
    declare _mode: string;
    declare _heroStyle: HeroStyle;
    declare _backdrop: Backdrop;
    declare _nutrition: boolean;
    declare _backInStock: boolean;
    declare _favorites: boolean;
    declare _device: Device;
    private _savedPreset = 'menu';
    private _savedAccent = '#e2553f';
    private _savedMode = 'dark';
    private _savedHeroStyle: HeroStyle = 'card';
    private _savedBackdrop: Backdrop = 'solid';
    private _savedNutrition = false;
    private _savedBackInStock = true;
    private _savedFavorites = true;
    declare _loadAttempted: boolean;
    private _hydrated = false;
    private _feedShopId = '';

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _preset: { state: true },
        _accent: { state: true },
        _mode: { state: true },
        _heroStyle: { state: true },
        _backdrop: { state: true },
        _nutrition: { state: true },
        _backInStock: { state: true },
        _device: { state: true },
        _loadAttempted: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .layout {
                display: grid;
                grid-template-columns: 360px 1fr;
                height: 100%;
            }
            .panel {
                padding: var(--space-5) var(--space-6);
                overflow-y: auto;
                border-right: 1px solid var(--glass-border-subtle);
            }
            .section { margin-bottom: var(--space-5); }
            .label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); margin-bottom: var(--space-2); text-transform: uppercase; letter-spacing: 0.05em; }
            .presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-2); }
            .preset {
                border: 2px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                background: var(--bg-surface);
                cursor: pointer;
                text-align: center;
                color: var(--text-primary);
                transition: border-color 0.15s ease, transform 0.15s ease;
            }
            .preset:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--text-primary) 25%, transparent); }
            .preset.active { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
            .wire {
                height: 72px;
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                overflow: hidden;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 6px;
                margin-bottom: var(--space-2);
            }
            .wire .hero { height: 16px; border-radius: 4px; background: var(--accent); opacity: 0.85; }
            .wire .ln { height: 9px; border-radius: 3px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); display: flex; gap: 4px; align-items: center; }
            .wire .ln::before { content: ''; width: 9px; height: 9px; border-radius: 3px; background: var(--accent); flex-shrink: 0; }
            .wire .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; flex: 1; }
            .wire .tile { border-radius: 4px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); position: relative; }
            .wire .tile::after { content: ''; position: absolute; left: 3px; right: 3px; bottom: 3px; height: 4px; border-radius: 2px; background: var(--accent); opacity: 0.8; }
            .wire .dense { height: 7px; border-radius: 3px; background: color-mix(in srgb, var(--text-primary) 22%, transparent); }
            .wire .dense::after { content: ''; display: block; margin-left: auto; width: 12px; height: 7px; border-radius: 3px; background: var(--accent); opacity: 0.8; }
            .preset .name { font-size: var(--text-xs); font-weight: var(--font-medium); display: block; padding-bottom: var(--space-1); }
            .swatches { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .swatch {
                width: 40px;
                height: 40px;
                border-radius: var(--radius-md);
                border: 3px solid transparent;
                cursor: pointer;
                transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
            }
            .swatch:hover { transform: translateY(-1px); }
            .swatch.active { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
            .modes { display: flex; background: var(--bg-inset); border-radius: var(--radius-md); padding: 4px; gap: 4px; }
            .mode {
                flex: 1;
                border: 0;
                border-radius: var(--radius-sm);
                padding: var(--space-2) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }
            .mode.active { background: var(--bg-surface); color: var(--text-primary); box-shadow: 0 1px 4px rgba(0,0,0,0.18); }
            .feature {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
            }
            .feature + .feature { margin-top: var(--space-2); }
            .feature .ftext { flex: 1; min-width: 0; }
            .feature .fname { font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--text-primary); }
            .feature .fdesc { font-size: var(--text-xs); color: var(--text-tertiary); margin-top: 2px; line-height: 1.4; }
            .feed-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-2); }
            .feed-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
                margin-bottom: var(--space-1);
            }
            .feed-row .fthumb {
                width: 44px; height: 32px; border-radius: var(--radius-sm);
                object-fit: cover; flex-shrink: 0;
                background: color-mix(in srgb, var(--text-primary) 6%, transparent);
            }
            .feed-row .finfo { flex: 1; min-width: 0; }
            .feed-row .finfo .fname { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .feed-row .finfo .fsub { font-size: var(--text-xs); color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .feed-row .fbtns { display: flex; gap: 2px; flex-shrink: 0; }
            .feed-row .fbtns button {
                border: 0; background: transparent; color: var(--text-tertiary);
                width: 22px; height: 22px; border-radius: var(--radius-sm);
                cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
            }
            .feed-row .fbtns button:hover { color: var(--text-primary); background: color-mix(in srgb, var(--text-primary) 6%, transparent); }
            .feed-row .fbtns button.danger:hover { color: var(--error); }
            .feed-empty { font-size: var(--text-xs); color: var(--text-tertiary); padding: var(--space-2) 0; }
            .actions { display: flex; gap: var(--space-2); }
            .preview {
                position: relative;
                overflow: hidden;
                background: color-mix(in srgb, var(--text-primary) 3%, transparent);
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .preview iframe {
                width: 420px;
                height: 100%;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: #0f1218;
                margin: var(--space-8) 0 var(--space-4);
                box-shadow: 0 24px 60px rgba(0,0,0,.35);
                transition: width 0.2s ease;
            }
            .preview iframe.tablet { width: 834px; }
            .preview iframe.desktop {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                margin: 0;
                border: 0;
                border-radius: 0;
                box-shadow: none;
                transition: none;
            }
            /* transform: scale (не zoom): внутренний viewport iframe равен
               layout-ширине 1400px — десктопный брейкпоинт витрины срабатывает
               при любой ширине панели превью. */
            @supports (width: 1cqw) {
                .preview { container-type: size; }
                .preview iframe.desktop {
                    width: 1400px;
                    height: calc(100cqh / (100cqw / 1400px));
                    transform: scale(calc(100cqw / 1400px));
                    transform-origin: top left;
                }
            }
            .preview-bar {
                position: absolute;
                top: var(--space-3);
                z-index: 2;
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: 4px 12px 4px 4px;
                border-radius: 99px;
                border: 1px solid var(--glass-border-subtle);
                background: color-mix(in srgb, var(--bg-surface) 82%, transparent);
                backdrop-filter: blur(10px);
            }
            .preview-url {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .devices { display: flex; gap: var(--space-1); }
            .devices button {
                border: 1px solid var(--glass-border-subtle);
                background: var(--bg-surface);
                color: var(--text-tertiary);
                border-radius: var(--radius-sm);
                width: 30px;
                height: 26px;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .devices button.active { color: var(--accent); border-color: var(--accent); }
            @media (max-width: 900px) {
                .layout { grid-template-columns: 1fr; }
                .preview { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this._preset = 'menu';
        this._accent = '#e2553f';
        this._mode = 'dark';
        this._heroStyle = 'card';
        this._backdrop = 'solid';
        this._nutrition = false;
        this._backInStock = true;
        this._favorites = true;
        this._device = 'phone';
        this._loadAttempted = false;
        this._shops = this.useResource('shop/shops', { autoload: true });
        this._updateOp = this.useOp('shop/shop_update');
        this._shelvesOp = this.useOp('shop/shelves_list');
        this._bannersOp = this.useOp('shop/banners_list');
        this._shelfRemoveOp = this.useOp('shop/shelf_remove');
        this._shelfReorderOp = this.useOp('shop/shelves_reorder');
        this._bannerRemoveOp = this.useOp('shop/banner_remove');
        this._bannerReorderOp = this.useOp('shop/banners_reorder');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._loadAttempted = true;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId')) {
            this._hydrated = false;
            this._feedShopId = '';
        }
        if (!this._hydrated) this._hydrated = this._hydrate();
        if (this.shopId !== '' && this._feedShopId !== this.shopId) {
            this._feedShopId = this.shopId;
            void this._loadFeed();
        }
    }

    private async _loadFeed(): Promise<void> {
        await Promise.all([
            this._shelvesOp.run({ shop_id: this.shopId }),
            this._bannersOp.run({ shop_id: this.shopId }),
        ]);
    }

    private _shop(): Record<string, unknown> | null {
        const row = this._shops.items.find((s) => (s as Record<string, unknown>).shop_id === this.shopId);
        return row === undefined ? null : (row as Record<string, unknown>);
    }

    private _shelves(): ShelfRow[] {
        const result = this._shelvesOp.lastResult as { items?: ShelfRow[] } | null;
        return Array.isArray(result?.items) ? result.items : [];
    }

    private _banners(): BannerRow[] {
        const result = this._bannersOp.lastResult as { items?: BannerRow[] } | null;
        return Array.isArray(result?.items) ? result.items : [];
    }

    private _hydrate(): boolean {
        const shop = this._shop();
        if (shop === null) return false;
        const theme = (shop.theme ?? {}) as Record<string, unknown>;
        this._preset = typeof theme.preset === 'string' ? theme.preset : 'menu';
        this._accent = typeof theme.accent_color === 'string' ? theme.accent_color : '#e2553f';
        this._mode = theme.mode === 'light' ? 'light' : 'dark';
        const hero = typeof theme.hero_style === 'string' ? theme.hero_style : 'card';
        this._heroStyle = (HERO_STYLES as readonly string[]).includes(hero) ? (hero as HeroStyle) : 'card';
        const backdrop = typeof theme.backdrop === 'string' ? theme.backdrop : 'solid';
        this._backdrop = (BACKDROPS as readonly string[]).includes(backdrop) ? (backdrop as Backdrop) : 'solid';
        const features = (shop.features ?? {}) as Record<string, unknown>;
        this._nutrition = features.nutrition === true;
        this._backInStock = features.back_in_stock !== false;
        this._favorites = features.favorites !== false;
        this._savedPreset = this._preset;
        this._savedAccent = this._accent;
        this._savedMode = this._mode;
        this._savedHeroStyle = this._heroStyle;
        this._savedBackdrop = this._backdrop;
        this._savedNutrition = this._nutrition;
        this._savedBackInStock = this._backInStock;
        this._savedFavorites = this._favorites;
        return true;
    }

    private _featureValue(f: FeatureKey): boolean {
        return f === 'nutrition' ? this._nutrition : f === 'back_in_stock' ? this._backInStock : this._favorites;
    }

    private _setFeature(f: FeatureKey, v: boolean): void {
        if (f === 'nutrition') this._nutrition = v;
        else if (f === 'back_in_stock') this._backInStock = v;
        else this._favorites = v;
    }

    private get _dirty(): boolean {
        return this._preset !== this._savedPreset
            || this._accent !== this._savedAccent
            || this._mode !== this._savedMode
            || this._heroStyle !== this._savedHeroStyle
            || this._backdrop !== this._savedBackdrop
            || this._nutrition !== this._savedNutrition
            || this._backInStock !== this._savedBackInStock
            || this._favorites !== this._savedFavorites;
    }

    private _wireframe(preset: string) {
        if (preset === 'grid') {
            return html`<span class="wire"><span class="hero"></span><span class="tiles"><span class="tile"></span><span class="tile"></span><span class="tile"></span><span class="tile"></span></span></span>`;
        }
        if (preset === 'compact') {
            return html`<span class="wire"><span class="hero"></span><span class="dense"></span><span class="dense"></span><span class="dense"></span><span class="dense"></span></span>`;
        }
        return html`<span class="wire"><span class="hero"></span><span class="ln"></span><span class="ln"></span><span class="ln"></span></span>`;
    }

    private _previewSrc(base: string): string {
        const q = `tpreset=${this._preset}&taccent=${encodeURIComponent(this._accent)}&tmode=${this._mode}&thero=${this._heroStyle}&tbackdrop=${this._backdrop}`;
        return `${base}${base.includes('?') ? '&' : '?'}${q}`;
    }

    private async _save() {
        const result = await this._updateOp.run({
            shop_id: this.shopId,
            theme: {
                preset: this._preset,
                accent_color: this._accent,
                mode: this._mode,
                hero_style: this._heroStyle,
                backdrop: this._backdrop,
            },
            features: {
                nutrition: this._nutrition,
                back_in_stock: this._backInStock,
                favorites: this._favorites,
            },
        });
        if (result !== null) {
            this._savedPreset = this._preset;
            this._savedAccent = this._accent;
            this._savedMode = this._mode;
            this._savedHeroStyle = this._heroStyle;
            this._savedBackdrop = this._backdrop;
            this._savedNutrition = this._nutrition;
            this._savedBackInStock = this._backInStock;
            this._savedFavorites = this._favorites;
            await this._shops.load();
            this._refreshPreview();
        }
    }

    private _refreshPreview(): void {
        const frame = this.renderRoot?.querySelector<HTMLIFrameElement>('.preview iframe');
        if (frame !== null && frame !== undefined && frame.src !== '') {
            frame.src = this._previewSrc(frame.src.split('?')[0] ?? frame.src);
        }
    }

    private _openShelfModal(shelf?: ShelfRow) {
        const draft: ShelfDraft | null = shelf === undefined
            ? null
            : {
                shop_shelf_id: shelf.shop_shelf_id,
                kind: shelf.kind as ShelfDraft['kind'],
                layout: shelf.layout as ShelfDraft['layout'],
                placement: shelf.placement as ShelfDraft['placement'],
                title: shelf.title,
                subtitle: shelf.subtitle,
                product_ids: [...shelf.product_ids],
                category_id: shelf.category_id,
                limit: shelf.limit,
                is_active: shelf.is_active,
            };
        this.openModal('shop.shelf', {
            shopId: this.shopId,
            shelf: draft,
        });
    }

    private _openBannerModal(banner?: BannerRow) {
        const draft: BannerDraft | null = banner === undefined
            ? null
            : {
                shop_banner_id: banner.shop_banner_id,
                title: banner.title,
                subtitle: banner.subtitle,
                image_file_id: banner.image_file_id,
                link: banner.link,
                window: { ...banner.window },
                is_active: banner.is_active,
            };
        this.openModal('shop.banner', {
            shopId: this.shopId,
            banner: draft,
        });
    }

    private async _moveShelf(shelf: ShelfRow, dir: -1 | 1) {
        const rows = this._shelves();
        const idx = rows.findIndex((s) => s.shop_shelf_id === shelf.shop_shelf_id);
        const swap = idx + dir;
        if (idx < 0 || swap < 0 || swap >= rows.length) return;
        const ids = rows.map((s) => s.shop_shelf_id);
        [ids[idx], ids[swap]] = [ids[swap] as string, ids[idx] as string];
        await this._shelfReorderOp.run({ shop_id: this.shopId, shelf_ids: ids });
        await this._loadFeed();
    }

    private async _removeShelf(shelf: ShelfRow) {
        await this._shelfRemoveOp.run({ shop_id: this.shopId, shop_shelf_id: shelf.shop_shelf_id });
        await this._loadFeed();
    }

    private async _moveBanner(banner: BannerRow, dir: -1 | 1) {
        const rows = this._banners();
        const idx = rows.findIndex((b) => b.shop_banner_id === banner.shop_banner_id);
        const swap = idx + dir;
        if (idx < 0 || swap < 0 || swap >= rows.length) return;
        const ids = rows.map((b) => b.shop_banner_id);
        [ids[idx], ids[swap]] = [ids[swap] as string, ids[idx] as string];
        await this._bannerReorderOp.run({ shop_id: this.shopId, banner_ids: ids });
        await this._loadFeed();
    }

    private async _removeBanner(banner: BannerRow) {
        await this._bannerRemoveOp.run({ shop_id: this.shopId, shop_banner_id: banner.shop_banner_id });
        await this._loadFeed();
    }

    private _shelfTitle(s: ShelfRow): string {
        return s.title !== '' ? s.title : this.t(`feed.kind.${s.kind}`);
    }

    private _shelfMeta(s: ShelfRow): string {
        const parts = [this.t(`feed.kind.${s.kind}`), this.t(`feed.layout.${s.layout}`)];
        if (s.placement === 'cart') parts.push(this.t('feed.placement.cart'));
        if (!s.is_active) parts.push(this.t('feed.off'));
        return parts.join(' · ');
    }

    private _renderFeed() {
        const shelves = this._shelves();
        const banners = this._banners();
        return html`
            <div class="section">
                <div class="feed-head">
                    <div class="label" style="margin-bottom:0">${this.t('feed.shelves_label')}</div>
                    <platform-button size="sm" variant="secondary" @click=${() => this._openShelfModal()}>
                        <platform-icon name="plus" size="14"></platform-icon> ${this.t('feed.shelf_add')}
                    </platform-button>
                </div>
                ${shelves.length === 0
                    ? html`<div class="feed-empty">${this.t('feed.shelves_empty')}</div>`
                    : shelves.map((s) => html`
                        <div class="feed-row">
                            <div class="finfo">
                                <div class="fname">${this._shelfTitle(s)}</div>
                                <div class="fsub">${this._shelfMeta(s)}</div>
                            </div>
                            <div class="fbtns">
                                <button title=${this.t('feed.move_up')} @click=${() => this._moveShelf(s, -1)}><platform-icon name="chevron-up" size="14"></platform-icon></button>
                                <button title=${this.t('feed.move_down')} @click=${() => this._moveShelf(s, 1)}><platform-icon name="chevron-down" size="14"></platform-icon></button>
                                <button title=${this.t('feed.edit')} @click=${() => this._openShelfModal(s)}><platform-icon name="edit" size="14"></platform-icon></button>
                                <button class="danger" title=${this.t('feed.remove')} @click=${() => this._removeShelf(s)}><platform-icon name="trash" size="14"></platform-icon></button>
                            </div>
                        </div>
                    `)}
            </div>
            <div class="section">
                <div class="feed-head">
                    <div class="label" style="margin-bottom:0">${this.t('feed.banners_label')}</div>
                    <platform-button size="sm" variant="secondary" @click=${() => this._openBannerModal()}>
                        <platform-icon name="plus" size="14"></platform-icon> ${this.t('feed.banner_add')}
                    </platform-button>
                </div>
                ${banners.length === 0
                    ? html`<div class="feed-empty">${this.t('feed.banners_empty')}</div>`
                    : banners.map((b) => html`
                        <div class="feed-row">
                            ${b.image_file_id !== null
                                ? html`<img class="fthumb" src="/shop/api/v1/files/download/${b.image_file_id}?v=sm!sq" alt="">`
                                : html`<div class="fthumb"></div>`}
                            <div class="finfo">
                                <div class="fname">${b.title !== '' ? b.title : this.t('feed.banner_untitled')}</div>
                                <div class="fsub">${b.subtitle}${b.is_active ? '' : ` · ${this.t('feed.off')}`}</div>
                            </div>
                            <div class="fbtns">
                                <button title=${this.t('feed.move_up')} @click=${() => this._moveBanner(b, -1)}><platform-icon name="chevron-up" size="14"></platform-icon></button>
                                <button title=${this.t('feed.move_down')} @click=${() => this._moveBanner(b, 1)}><platform-icon name="chevron-down" size="14"></platform-icon></button>
                                <button title=${this.t('feed.edit')} @click=${() => this._openBannerModal(b)}><platform-icon name="edit" size="14"></platform-icon></button>
                                <button class="danger" title=${this.t('feed.remove')} @click=${() => this._removeBanner(b)}><platform-icon name="trash" size="14"></platform-icon></button>
                            </div>
                        </div>
                    `)}
            </div>`;
    }

    override render() {
        const shop = this._shop();
        if (shop === null) {
            return this._shops.loading || !this._loadAttempted
                ? html`<platform-empty-state loading></platform-empty-state>`
                : html`
                    <platform-empty-state icon="store" title=${this.t('builder.shop_not_found')}>
                        <platform-button size="sm" variant="secondary" @click=${() => { this._shops.load(); }}>${this.t('builder.retry')}</platform-button>
                    </platform-empty-state>`;
        }
        const storefrontUrl = typeof shop.storefront_url === 'string' ? shop.storefront_url : '';
        const slug = typeof shop.slug === 'string' ? shop.slug : '';
        const previewPath = shop.status === 'published' && slug !== ''
            ? `/shop/api/v1/public/s/${encodeURIComponent(slug)}`
            : '';
        return html`
            <div class="layout">
                <div class="panel">
                    <shop-page-head
                        .shop=${shopHeadRow(shop)}
                        shop-id=${this.shopId}
                        section=${this.t('routes.shop_builder')}
                    ></shop-page-head>
                    <div class="section">
                        <div class="label">${this.t('builder.preset_label')}</div>
                        <div class="presets">
                            ${PRESETS.map((key) => html`
                                <button
                                    class="preset ${this._preset === key ? 'active' : ''}"
                                    @click=${() => { this._preset = key; }}
                                >
                                    ${this._wireframe(key)}
                                    <span class="name">${this.t(`builder.preset_${key}`)}</span>
                                </button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.mode_label')}</div>
                        <div class="modes">
                            ${MODES.map((key) => html`
                                <button
                                    class="mode ${this._mode === key ? 'active' : ''}"
                                    @click=${() => { this._mode = key; }}
                                ><platform-icon name=${key === 'dark' ? 'moon' : 'sun'} size="14"></platform-icon> ${this.t(`builder.mode_${key}`)}</button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.hero_label')}</div>
                        <div class="modes">
                            ${HERO_STYLES.map((key) => html`
                                <button
                                    class="mode ${this._heroStyle === key ? 'active' : ''}"
                                    @click=${() => { this._heroStyle = key; }}
                                >${this.t(`builder.hero_${key}`)}</button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.backdrop_label')}</div>
                        <div class="modes">
                            ${BACKDROPS.map((key) => html`
                                <button
                                    class="mode ${this._backdrop === key ? 'active' : ''}"
                                    @click=${() => { this._backdrop = key; }}
                                >${this.t(`builder.backdrop_${key}`)}</button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.accent_label')}</div>
                        <div class="swatches">
                            ${ACCENTS.map((c) => html`
                                <button
                                    class="swatch ${this._accent === c ? 'active' : ''}"
                                    style="background:${c}"
                                    @click=${() => { this._accent = c; }}
                                ></button>
                            `)}
                        </div>
                    </div>
                    <div class="section">
                        <div class="label">${this.t('builder.features_label')}</div>
                        ${FEATURES.map((f) => html`
                            <div class="feature">
                                <div class="ftext">
                                    <div class="fname">${this.t(`builder.feature_${f}`)}</div>
                                    <div class="fdesc">${this.t(`builder.feature_${f}_desc`)}</div>
                                </div>
                                <platform-switch
                                    ?checked=${this._featureValue(f)}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                                        this._setFeature(f, Boolean(e.detail.value));
                                    }}
                                ></platform-switch>
                            </div>
                        `)}
                    </div>
                    ${this._renderFeed()}
                    <div class="actions">
                        <platform-button
                            variant="primary"
                            ?loading=${this._updateOp.busy}
                            ?disabled=${!this._dirty}
                            @click=${() => this._save()}
                        >${this.t('builder.save')}</platform-button>
                        <platform-button variant="secondary" ?disabled=${!this._dirty} @click=${() => {
                            this._preset = this._savedPreset;
                            this._accent = this._savedAccent;
                            this._mode = this._savedMode;
                            this._heroStyle = this._savedHeroStyle;
                            this._backdrop = this._savedBackdrop;
                            this._nutrition = this._savedNutrition;
                            this._backInStock = this._savedBackInStock;
                            this._favorites = this._savedFavorites;
                        }}>
                            ${this.t('builder.reset')}
                        </platform-button>
                    </div>
                </div>
                <div class="preview">
                    <div class="preview-bar">
                        <div class="devices">
                            ${DEVICES.map((d) => html`
                                <button class=${this._device === d ? 'active' : ''} title=${this.t(`builder.device_${d}`)}
                                    @click=${() => { this._device = d; }}
                                ><platform-icon name=${DEVICE_ICONS[d]} size="14"></platform-icon></button>
                            `)}
                        </div>
                        <span class="preview-url">${storefrontUrl}</span>
                    </div>
                    ${previewPath === ''
                        ? html`<platform-empty-state icon="store" title=${this.t('builder.preview_unavailable')}></platform-empty-state>`
                        : html`<iframe class=${this._device === 'phone' ? '' : this._device} src=${this._previewSrc(previewPath)} title="storefront"></iframe>`}
                </div>
            </div>
        `;
    }
}

customElements.define('shop-builder-page', ShopBuilderPage);
