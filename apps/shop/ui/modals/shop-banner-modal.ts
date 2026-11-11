/**
 * ShopBannerModal — редактор сторис-баннера верха витринной ленты.
 *
 * Картинка загружается в файлы (spec product — ассеты витрины),
 * deeplink собирается конструктором: раздел / товар / полка / внешняя
 * ссылка; необязательное окно показа по времени суток.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

const LINK_TYPES = ['none', 'product', 'category', 'shelf', 'url'] as const;
type LinkType = (typeof LINK_TYPES)[number];

export interface BannerDraft {
    shop_banner_id?: string;
    title: string;
    subtitle: string;
    image_file_id: string | null;
    link: string;
    window: Record<string, unknown>;
    is_active: boolean;
}

interface NamedRow {
    id: string;
    name: string;
}

function _str(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

const _TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export class ShopBannerModal extends PlatformModal {
    static modalKind = 'shop.banner';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare banner: BannerDraft | null;

    private _createOp: OpController;
    private _updateOp: OpController;
    private _uploadOp: OpController;
    private _productsOp: OpController;
    private _categoriesOp: OpController;
    private _shelvesOp: OpController;

    declare _title: string;
    declare _subtitle: string;
    declare _imageFileId: string;
    declare _imagePreview: string;
    declare _linkType: LinkType;
    declare _linkRef: string;
    declare _linkUrl: string;
    declare _windowOn: boolean;
    declare _timeFrom: string;
    declare _timeTo: string;
    declare _isActive: boolean;
    declare _products: NamedRow[];
    declare _categories: NamedRow[];
    declare _shelves: NamedRow[];

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        banner: { attribute: false },
        _title: { state: true },
        _subtitle: { state: true },
        _imageFileId: { state: true },
        _imagePreview: { state: true },
        _linkType: { state: true },
        _linkRef: { state: true },
        _linkUrl: { state: true },
        _windowOn: { state: true },
        _timeFrom: { state: true },
        _timeTo: { state: true },
        _isActive: { state: true },
        _products: { state: true },
        _categories: { state: true },
        _shelves: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .top { display: grid; grid-template-columns: 160px 1fr; gap: var(--space-4); align-items: start; }
            .photo-box {
                width: 160px; height: 100px; border-radius: var(--radius-lg);
                border: 1px dashed var(--glass-border-subtle);
                background: color-mix(in srgb, var(--text-primary) 4%, transparent);
                cursor: pointer; overflow: hidden; position: relative;
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                gap: var(--space-1); color: var(--text-tertiary); font-size: var(--text-xs);
            }
            .photo-box:hover { border-color: var(--accent); color: var(--accent); }
            .photo-box img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
            .fields { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
            .sec-title { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .toggle-row { display: flex; align-items: center; gap: var(--space-2); }
            .toggle-row span { font-size: var(--text-sm); color: var(--text-primary); }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            @media (max-width: 560px) {
                .top { grid-template-columns: 1fr; }
                .photo-box { width: 100%; height: 120px; }
            }
        `,
    ];

    constructor() {
        super();
        this._title = '';
        this._subtitle = '';
        this._imageFileId = '';
        this._imagePreview = '';
        this._linkType = 'none';
        this._linkRef = '';
        this._linkUrl = '';
        this._windowOn = false;
        this._timeFrom = '12:00';
        this._timeTo = '18:00';
        this._isActive = true;
        this._products = [];
        this._categories = [];
        this._shelves = [];
        this._createOp = this.useOp('shop/banner_create');
        this._updateOp = this.useOp('shop/banner_update');
        this._uploadOp = this.useOp('platform/file_create');
        this._productsOp = this.useOp('shop/products_list');
        this._categoriesOp = this.useOp('shop/categories_list');
        this._shelvesOp = this.useOp('shop/shelves_list');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopBannerModal: prop "shopId" required');
        }
        const b = this.banner;
        if (b !== null && b !== undefined) {
            this._title = b.title;
            this._subtitle = b.subtitle;
            this._imageFileId = b.image_file_id ?? '';
            this._imagePreview = b.image_file_id !== null
                ? `/shop/api/v1/files/download/${b.image_file_id}?v=sm!sq`
                : '';
            const [prefix, ...rest] = b.link.split(':');
            if (prefix === 'product' || prefix === 'category' || prefix === 'shelf') {
                this._linkType = prefix;
                this._linkRef = rest.join(':');
            } else if (prefix === 'url') {
                this._linkType = 'url';
                this._linkUrl = rest.join(':');
            }
            const w = b.window;
            const tf = typeof w.time_from === 'string' ? w.time_from : '';
            const tt = typeof w.time_to === 'string' ? w.time_to : '';
            this._windowOn = tf !== '' || tt !== '';
            if (tf !== '') this._timeFrom = tf;
            if (tt !== '') this._timeTo = tt;
            this._isActive = b.is_active;
        }
        void this._load();
    }

    private async _load(): Promise<void> {
        const [products, categories, shelves] = await Promise.all([
            this._productsOp.run({ shop_id: this.shopId, limit: 500 }),
            this._categoriesOp.run({ shop_id: this.shopId }),
            this._shelvesOp.run({ shop_id: this.shopId }),
        ]);
        const pItems = (products as { items?: { product_id?: string; name?: string }[] } | null)?.items;
        this._products = Array.isArray(pItems)
            ? pItems
                .filter((p): p is { product_id: string; name: string } => typeof p.product_id === 'string' && typeof p.name === 'string')
                .map((p) => ({ id: p.product_id, name: p.name }))
            : [];
        const cItems = (categories as { items?: { shop_category_id?: string; name?: string }[] } | null)?.items;
        this._categories = Array.isArray(cItems)
            ? cItems
                .filter((c): c is { shop_category_id: string; name: string } => typeof c.shop_category_id === 'string' && typeof c.name === 'string')
                .map((c) => ({ id: c.shop_category_id, name: c.name }))
            : [];
        const sItems = (shelves as { items?: { shop_shelf_id?: string; title?: string; kind?: string }[] } | null)?.items;
        this._shelves = Array.isArray(sItems)
            ? sItems
                .filter((s): s is { shop_shelf_id: string; title: string; kind: string } => typeof s.shop_shelf_id === 'string')
                .map((s) => ({ id: s.shop_shelf_id, name: s.title !== '' ? s.title : this.t(`feed.kind.${s.kind}`) }))
            : [];
    }

    private get _editing(): boolean {
        return this.banner !== null && this.banner !== undefined && typeof this.banner.shop_banner_id === 'string';
    }

    private _linkRows(): NamedRow[] {
        if (this._linkType === 'product') return this._products;
        if (this._linkType === 'category') return this._categories;
        return this._shelves;
    }

    private _buildLink(): string {
        if (this._linkType === 'none') return '';
        if (this._linkType === 'url') {
            const url = this._linkUrl.trim();
            return url === '' ? '' : `url:${url}`;
        }
        return this._linkRef === '' ? '' : `${this._linkType}:${this._linkRef}`;
    }

    private _buildWindow(): Record<string, unknown> {
        if (!this._windowOn) return {};
        if (!_TIME_RE.test(this._timeFrom) || !_TIME_RE.test(this._timeTo)) return {};
        return { time_from: this._timeFrom, time_to: this._timeTo };
    }

    private get _valid(): boolean {
        if (this._linkType === 'url' && this._linkUrl.trim() !== '' && !/^https?:\/\//.test(this._linkUrl.trim())) return false;
        if (this._linkType !== 'none' && this._linkType !== 'url' && this._linkRef === '') return false;
        return true;
    }

    private async _uploadImage(e: Event) {
        const input = e.target as HTMLInputElement;
        const file = input.files && input.files[0];
        if (!file) return;
        const result = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId }),
        });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                this._imageFileId = fileId;
                this._imagePreview = `/shop/api/v1/files/download/${fileId}?v=sm!sq`;
            }
        }
        input.value = '';
    }

    private async _save() {
        if (!this._valid || this._createOp.busy || this._updateOp.busy) return;
        const body: Record<string, unknown> = {
            title: this._title.trim(),
            subtitle: this._subtitle.trim(),
            image_file_id: this._imageFileId === '' ? null : this._imageFileId,
            link: this._buildLink(),
            window: this._buildWindow(),
        };
        const result = this._editing && this.banner !== null && this.banner.shop_banner_id !== undefined
            ? await this._updateOp.run({
                shop_id: this.shopId,
                shop_banner_id: this.banner.shop_banner_id,
                ...body,
                is_active: this._isActive,
            })
            : await this._createOp.run({ shop_id: this.shopId, ...body });
        if (result !== null) this.close();
    }

    override renderHeader(): string {
        return this._editing ? this.t('feed.banner_edit') : this.t('feed.banner_new');
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="body">
                <div class="top">
                    <button class="photo-box" ?disabled=${this._uploadOp.busy}
                        @click=${() => this.renderRoot.querySelector<HTMLInputElement>('#banner-input')?.click()}>
                        ${this._imagePreview === ''
                            ? html`<platform-icon name="image" size="24"></platform-icon><span>${this.t('feed.banner_photo')}</span>`
                            : html`<img src=${this._imagePreview} alt="">`}
                    </button>
                    <input id="banner-input" type="file" accept="image/*" style="display:none" @change=${(e: Event) => this._uploadImage(e)}>
                    <div class="fields">
                        <platform-field type="string" mode="edit" label=${this.t('feed.field_title')} .value=${this._title}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._title = _str(e); }}></platform-field>
                        <platform-field type="string" mode="edit" label=${this.t('feed.field_subtitle')} .value=${this._subtitle}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._subtitle = _str(e); }}></platform-field>
                    </div>
                </div>
                <div class="sec-title">${this.t('feed.link_title')}</div>
                <div class="grid">
                    <platform-field type="enum" mode="edit" label=${this.t('feed.field_link_type')} .value=${this._linkType}
                        .config=${{ values: LINK_TYPES.map((t) => ({ value: t, label: this.t(`feed.link.${t}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            this._linkType = _str(e) as LinkType;
                            this._linkRef = '';
                        }}></platform-field>
                    ${this._linkType === 'url' ? html`
                        <platform-field type="string" mode="edit" label=${this.t('feed.field_link_url')} .value=${this._linkUrl}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._linkUrl = _str(e); }}></platform-field>
                    ` : nothing}
                    ${this._linkType !== 'none' && this._linkType !== 'url' ? html`
                        <platform-field type="enum" mode="edit" label=${this.t('feed.field_link_target')} .value=${this._linkRef}
                            .config=${{ values: this._linkRows().map((r) => ({ value: r.id, label: r.name })) }}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._linkRef = _str(e); }}></platform-field>
                    ` : nothing}
                </div>
                <div class="toggle-row">
                    <platform-switch ?checked=${this._windowOn}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._windowOn = Boolean(e.detail.value); }}></platform-switch>
                    <span>${this.t('feed.window_toggle')}</span>
                </div>
                ${this._windowOn ? html`
                    <div class="grid">
                        <platform-field type="string" mode="edit" label=${this.t('feed.field_time_from')} .value=${this._timeFrom}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._timeFrom = _str(e); }}></platform-field>
                        <platform-field type="string" mode="edit" label=${this.t('feed.field_time_to')} .value=${this._timeTo}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._timeTo = _str(e); }}></platform-field>
                    </div>
                ` : nothing}
                ${this._editing ? html`
                    <div class="toggle-row">
                        <platform-switch ?checked=${this._isActive}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._isActive = Boolean(e.detail.value); }}></platform-switch>
                        <span>${this.t('feed.field_active')}</span>
                    </div>
                ` : nothing}
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>${this.t('menu.cancel')}</platform-button>
                    <platform-button variant="primary" ?loading=${this._createOp.busy || this._updateOp.busy}
                        ?disabled=${!this._valid} @click=${() => this._save()}>${this.t('menu.save')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-banner-modal', ShopBannerModal);
registerModalKind(ShopBannerModal.modalKind, 'shop-banner-modal');
