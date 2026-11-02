/**
 * Магазины компании: карточки витрин, создание первого магазина в два поля,
 * быстрые действия (меню, вид, заказы, открыть витрину).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

const STATUS_TONES: Record<string, string> = {
    draft: 'var(--text-tertiary)',
    published: 'var(--success)',
    suspended: 'var(--warning)',
};

export class ShopHomePage extends PlatformPage {
    static i18nNamespace = 'shop';

    private _shops: ResourceController;
    private _createOp: OpController;
    private _publishOp: OpController;
    private _autofillOp: OpController;
    private _newName = '';
    private _newSlug = '';
    private _slugTouched = false;

    static override properties = {
        _newName: { state: true },
        _newSlug: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
            h1 { margin: 0 0 var(--space-1); font-size: var(--text-2xl); color: var(--text-primary); }
            .sub { color: var(--text-tertiary); font-size: var(--text-sm); margin-bottom: var(--space-5); }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: var(--space-4);
            }
            .card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                background: var(--bg-surface);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .card-head { display: flex; align-items: center; gap: var(--space-2); }
            .card-name { font-weight: var(--font-semibold); color: var(--text-primary); flex: 1; }
            .status { font-size: var(--text-xs); font-weight: var(--font-medium); }
            .slug { color: var(--text-tertiary); font-size: var(--text-xs); font-variant-numeric: tabular-nums; }
            .actions { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-top: auto; }
            .create {
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .create-title { font-weight: var(--font-medium); color: var(--text-primary); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .checklist { display: flex; flex-direction: column; gap: var(--space-1); }
            .check-item { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); color: var(--text-tertiary); }
            .check-item.done { color: var(--text-secondary); }
            .check-item.done platform-icon { color: var(--success); }
            .check-item platform-icon { flex-shrink: 0; }
            .publish-cta {
                border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
                background: color-mix(in srgb, var(--accent) 8%, transparent);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .publish-cta .hint { flex: 1; }
        `,
    ];

    constructor() {
        super();
        this._shops = this.useResource('shop/shops');
        this._createOp = this.useOp('shop/shop_create');
        this._publishOp = this.useOp('shop/shop_publish');
        this._autofillOp = this.useOp('shop/ai_autofill');
    }

    async onRouteActive(): Promise<void> {
        await this._shops.load();
    }

    private _transliterate(text: string): string {
        const map: Record<string, string> = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        };
        return text
            .toLowerCase()
            .split('')
            .map((ch) => map[ch] ?? ch)
            .join('');
    }

    private _slugify(name: string): string {
        return this._transliterate(name)
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 40);
    }

    private _slugInput(raw: string): string {
        return this._transliterate(raw)
            .replace(/[^a-z0-9-]/g, '')
            .replace(/-{2,}/g, '-')
            .replace(/^-+/, '')
            .slice(0, 40);
    }

    private async _create() {
        const slug = (this._newSlug || this._slugify(this._newName)).trim();
        if (this._newName.trim() === '' || slug.length < 3) return;
        const result = await this._createOp.run({ name: this._newName.trim(), slug });
        if (result !== null) {
            this._newName = '';
            this._newSlug = '';
            this._slugTouched = false;
            await this._shops.load();
            const created = result as { shop_id?: string };
            if (created && typeof created.shop_id === 'string') {
                this.navigate('shop_menu', { shopId: created.shop_id });
            }
        }
    }

    private async _publish(shopId: string) {
        const result = await this._publishOp.run({ shop_id: shopId });
        if (result !== null) await this._shops.load();
    }

    private async _autofill(shopId: string) {
        const result = await this._autofillOp.run({ shop_id: shopId });
        if (result !== null) await this._shops.load();
    }

    private _statusLabel(status: string) {
        return this.t(`status.${status}`);
    }

    override render() {
        const items = this._shops.items;
        return html`
            <div class="wrap">
                <h1>${this.t('home.title')}</h1>
                <div class="sub">${this.t('home.subtitle')}</div>
                ${this._shops.loading && items.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : html`
                        <div class="grid">
                            ${items.map((row) => {
                                const shop = row as Record<string, unknown>;
                                const shopId = String(shop.shop_id);
                                const status = String(shop.status);
                                const productsCount = typeof shop.products_count === 'number' ? shop.products_count : 0;
                                const storefrontUrl = typeof shop.storefront_url === 'string' ? shop.storefront_url : '';
                                return html`
                                    <div class="card">
                                        <div class="card-head">
                                            <span class="card-name">${shop.name}</span>
                                            <span class="status" style="color:${STATUS_TONES[status] ?? 'var(--text-tertiary)'}">
                                                ${this._statusLabel(status)}
                                            </span>
                                        </div>
                                        <span class="slug">${shop.slug}.linnex.io</span>
                                        <div class="checklist">
                                            <span class="check-item ${productsCount > 0 ? 'done' : ''}">
                                                <platform-icon name=${productsCount > 0 ? 'check' : 'circle'} size="13"></platform-icon>
                                                ${productsCount > 0 ? `${productsCount} ${this.t('home.menu_count')}` : this.t('home.menu_empty')}
                                            </span>
                                        </div>
                                        ${status === 'draft' && productsCount > 0
                                            ? html`
                                                <div class="publish-cta">
                                                    <span class="hint">${this.t('home.ready_hint')}</span>
                                                    <platform-button size="sm" variant="primary" ?busy=${this._publishOp.busy} @click=${() => this._publish(shopId)}>
                                                        ${this.t('home.publish')}
                                                    </platform-button>
                                                </div>`
                                            : status === 'draft'
                                            ? html`<div class="hint">${this.t('home.fill_hint')}</div>`
                                            : nothing}
                                        ${status === 'published' && storefrontUrl !== ''
                                            ? html`<a class="hint" href=${storefrontUrl} target="_blank" rel="noopener">${this.t('home.published_open')} →</a>`
                                            : nothing}
                                        <div class="actions">
                                            ${(!shop.description || !shop.cover_file_id)
                                                ? html`<platform-button size="sm" ?busy=${this._autofillOp.busy} @click=${() => this._autofill(shopId)}>
                                                      ${this.t('home.ai_autofill')}
                                                  </platform-button>`
                                                : nothing}
                                            <platform-button size="sm" variant="primary" @click=${() => this.navigate('shop_menu', { shopId })}>
                                                ${this.t('home.open_menu')}
                                            </platform-button>
                                            <platform-button size="sm" @click=${() => this.navigate('shop_builder', { shopId })}>
                                                ${this.t('home.open_builder')}
                                            </platform-button>
                                            <platform-button size="sm" @click=${() => this.navigate('shop_orders', { shopId })}>
                                                ${this.t('home.open_orders')}
                                            </platform-button>
                                            <platform-button size="sm" @click=${() => this.navigate('shop_settings', { shopId })}>
                                                ${this.t('home.open_settings')}
                                            </platform-button>
                                        </div>
                                    </div>
                                `;
                            })}
                            <div class="create">
                                <div class="create-title">${this.t('home.create_title')}</div>
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    label=${this.t('home.field_name')}
                                    .value=${this._newName}
                                    @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                        this._newName = typeof event.detail.value === 'string' ? event.detail.value : '';
                                        if (!this._slugTouched) this._newSlug = this._slugify(this._newName);
                                    }}
                                ></platform-field>
                                <platform-field
                                    type="string"
                                    mode="edit"
                                    label=${this.t('home.field_slug')}
                                    hint=${this.t('home.field_slug_hint')}
                                    .value=${this._newSlug}
                                    @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                        this._slugTouched = true;
                                        const raw = typeof event.detail.value === 'string' ? event.detail.value : '';
                                        this._newSlug = this._slugInput(raw);
                                    }}
                                ></platform-field>
                                <div class="hint">${this._newSlug || this._slugify(this._newName) || 'my-shop'}.linnex.io</div>
                                <platform-button
                                    variant="primary"
                                    ?busy=${this._createOp.busy}
                                    ?disabled=${this._newName.trim() === ''}
                                    @click=${() => this._create()}
                                >${this.t('home.create_button')}</platform-button>
                            </div>
                        </div>
                    `}
            </div>
        `;
    }
}

customElements.define('shop-home-page', ShopHomePage);
