/**
 * Настройки магазина: профиль, доставка, публикация, домены, Telegram.
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';

export class ShopSettingsPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _updateOp: OpController;
    private _publishOp: OpController;
    private _suspendOp: OpController;
    private _domainAddOp: OpController;
    private _domainProvisionOp: OpController;

    declare _name: string;
    declare _description: string;
    declare _phone: string;
    declare _city: string;
    declare _address: string;
    declare _deliveryEnabled: boolean;
    declare _pickupEnabled: boolean;
    declare _deliveryFee: string;
    declare _minOrder: string;
    declare _newDomain: string;
    declare _botToken: string;
    private _telegramConnectOp: OpController;
    private _telegramDisconnectOp: OpController;
    private _uploadOp: OpController;
    private _aiDescribeShopOp: OpController;
    private _aiGenerateCoverOp: OpController;
    private _aiGenerateLogoOp: OpController;
    declare _logoFileId: string;
    declare _coverFileId: string;
    declare _hours: Array<{ open: string; close: string; closed: boolean }>;
    declare _loadAttempted: boolean;
    private _hydrated = false;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _loadAttempted: { state: true },
        _name: { state: true },
        _description: { state: true },
        _phone: { state: true },
        _city: { state: true },
        _address: { state: true },
        _deliveryEnabled: { state: true },
        _pickupEnabled: { state: true },
        _deliveryFee: { state: true },
        _minOrder: { state: true },
        _newDomain: { state: true },
        _botToken: { state: true },
        _logoFileId: { state: true },
        _coverFileId: { state: true },
        _hours: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { padding: var(--space-5) var(--space-6); }
            .sections { display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: var(--space-4); align-items: start; }
            .card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .card-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .row { display: flex; gap: var(--space-3); align-items: center; justify-content: space-between; }
            .row > platform-field { flex: 1; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); }
            .status-line { display: flex; align-items: center; gap: var(--space-3); }
            .qr-row { display: flex; gap: var(--space-3); align-items: center; }
            .brand { display: grid; grid-template-columns: 88px 1fr; gap: var(--space-3); }
            .brand-tile {
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: transparent;
                cursor: pointer;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                padding: var(--space-2);
                min-height: 88px;
                position: relative;
            }
            .brand-tile.cover { min-height: 88px; }
            .brand-tile img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
            .brand-tile .veil {
                position: absolute;
                inset: auto 0 0;
                background: color-mix(in srgb, var(--bg-surface) 82%, transparent);
                font-size: var(--text-2xs, 10px);
                padding: 2px;
                text-align: center;
            }
            .brand-tile:hover { border-color: var(--accent); color: var(--accent); }
            .ai-row { display: flex; justify-content: flex-end; }
            .hours { display: flex; flex-direction: column; gap: var(--space-2); }
            .day-row { display: grid; grid-template-columns: 32px 1fr 12px 1fr auto; gap: var(--space-2); align-items: center; }
            .day-row.off platform-field { opacity: 0.4; pointer-events: none; }
            .day-name { font-size: var(--text-sm); color: var(--text-secondary); font-weight: var(--font-medium); }
            .dash { text-align: center; color: var(--text-tertiary); }
            .closed-label { font-size: var(--text-xs); color: var(--text-tertiary); display: flex; align-items: center; gap: var(--space-2); }
            .qr { border-radius: var(--radius-sm); background: #fff; padding: var(--space-1); }
            .qr-link { color: var(--accent); font-size: var(--text-sm); }
            .embed { display: block; font-size: var(--text-xs); color: var(--text-tertiary); background: var(--bg-inset); border-radius: var(--radius-sm); padding: var(--space-2); word-break: break-all; user-select: all; }
        `,
    ];

    constructor() {
        super();
        this._loadAttempted = false;
        this._name = '';
        this._description = '';
        this._phone = '';
        this._city = '';
        this._address = '';
        this._deliveryEnabled = false;
        this._pickupEnabled = false;
        this._deliveryFee = '';
        this._minOrder = '';
        this._newDomain = '';
        this._botToken = '';
        this._logoFileId = '';
        this._coverFileId = '';
        this._hours = [];
        this._shops = this.useResource('shop/shops', { autoload: true });
        this._updateOp = this.useOp('shop/shop_update');
        this._publishOp = this.useOp('shop/shop_publish');
        this._suspendOp = this.useOp('shop/shop_suspend');
        this._domainAddOp = this.useOp('shop/domain_add');
        this._telegramConnectOp = this.useOp('shop/telegram_connect');
        this._telegramDisconnectOp = this.useOp('shop/telegram_disconnect');
        this._domainProvisionOp = this.useOp('shop/domain_provision');
        this._uploadOp = this.useOp('platform/file_create');
        this._aiDescribeShopOp = this.useOp('shop/ai_describe_shop');
        this._aiGenerateCoverOp = this.useOp('shop/ai_generate_cover');
        this._aiGenerateLogoOp = this.useOp('shop/ai_generate_logo');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._loadAttempted = true;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId')) this._hydrated = false;
        if (!this._hydrated) this._hydrated = this._hydrate();
    }

    private _shop(): Record<string, unknown> | null {
        const row = this._shops.items.find((s) => (s as Record<string, unknown>).shop_id === this.shopId);
        return row === undefined ? null : (row as Record<string, unknown>);
    }

    private _hydrate(): boolean {
        const shop = this._shop();
        if (shop === null) return false;
        this._name = String(shop.name ?? '');
        this._description = String(shop.description ?? '');
        this._phone = String(shop.phone ?? '');
        this._city = String(shop.city ?? '');
        this._address = String(shop.address ?? '');
        this._deliveryEnabled = Boolean(shop.delivery_enabled);
        this._pickupEnabled = Boolean(shop.pickup_enabled);
        this._deliveryFee = String((Number(shop.delivery_fee_minor ?? 0) / 100) || '');
        this._minOrder = String((Number(shop.min_order_minor ?? 0) / 100) || '');
        this._logoFileId = typeof shop.logo_file_id === 'string' ? shop.logo_file_id : '';
        this._coverFileId = typeof shop.cover_file_id === 'string' ? shop.cover_file_id : '';
        const wh = shop.working_hours !== null && typeof shop.working_hours === 'object'
            ? shop.working_hours as Record<string, unknown>
            : {};
        this._hours = Array.from({ length: 7 }, (_, day) => {
            const raw = wh[String(day)];
            const range = typeof raw === 'string' ? raw.split('-') : [];
            return {
                open: range[0]?.trim() ?? '',
                close: range[1]?.trim() ?? '',
                closed: typeof raw !== 'string' || raw.trim() === '',
            };
        });
        return true;
    }

    private _toMinor(value: string): number {
        const parsed = parseFloat(value.replace(',', '.'));
        return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 100) : 0;
    }

    private _collectHours(): Record<string, string> {
        const hours: Record<string, string> = {};
        const re = /^\d{1,2}:\d{2}$/;
        this._hours.forEach((day, index) => {
            if (day.closed) return;
            if (re.test(day.open) && re.test(day.close)) {
                hours[String(index)] = `${day.open}-${day.close}`;
            }
        });
        return hours;
    }

    private _setHour(index: number, key: 'open' | 'close' | 'closed', value: unknown) {
        this._hours = this._hours.map((day, i) => {
            if (i !== index) return day;
            if (key === 'closed') return { ...day, closed: Boolean(value) };
            return { ...day, [key]: typeof value === 'string' ? value : '' };
        });
    }

    private async _save() {
        const result = await this._updateOp.run({
            shop_id: this.shopId,
            name: this._name.trim() === '' ? null : this._name.trim(),
            description: this._description,
            phone: this._phone,
            city: this._city,
            address: this._address,
            delivery_enabled: this._deliveryEnabled,
            pickup_enabled: this._pickupEnabled,
            delivery_fee_minor: this._toMinor(this._deliveryFee),
            min_order_minor: this._toMinor(this._minOrder),
            working_hours: this._collectHours(),
        });
        if (result !== null) await this._shops.load();
    }

    private async _pickBrandImage(kind: 'logo' | 'cover') {
        const input = this.renderRoot?.querySelector<HTMLInputElement>(`#brand-${kind}-input`);
        input?.click();
    }

    private async _uploadBrandImage(kind: 'logo' | 'cover', event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files && input.files[0];
        input.value = '';
        if (!file) return;
        const uploaded = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId }),
        });
        if (uploaded === null || typeof uploaded !== 'object') return;
        const fileId = (uploaded as { file_id?: unknown }).file_id;
        if (typeof fileId !== 'string') return;
        const result = await this._updateOp.run({ shop_id: this.shopId, [`${kind}_file_id`]: fileId });
        if (result !== null) {
            if (kind === 'logo') this._logoFileId = fileId; else this._coverFileId = fileId;
            await this._shops.load();
        }
    }

    private async _aiDescribeShop() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiDescribeShopOp.run({
            shop_id: this.shopId,
            name,
            description: this._description,
        });
        if (result !== null && typeof result === 'object') {
            const text = (result as { text?: unknown }).text;
            if (typeof text === 'string' && text !== '') this._description = text;
        }
    }

    private async _aiGenerateCover() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiGenerateCoverOp.run({
            shop_id: this.shopId,
            name,
            description: this._description,
        });
        if (result === null || typeof result !== 'object') return;
        const fileId = (result as { file_id?: unknown }).file_id;
        if (typeof fileId !== 'string') return;
        const saved = await this._updateOp.run({ shop_id: this.shopId, cover_file_id: fileId });
        if (saved !== null) {
            this._coverFileId = fileId;
            await this._shops.load();
        }
    }

    private async _aiGenerateLogo() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiGenerateLogoOp.run({
            shop_id: this.shopId,
            name,
            description: this._description,
        });
        if (result === null || typeof result !== 'object') return;
        const fileId = (result as { file_id?: unknown }).file_id;
        if (typeof fileId !== 'string') return;
        const saved = await this._updateOp.run({ shop_id: this.shopId, logo_file_id: fileId });
        if (saved !== null) {
            this._logoFileId = fileId;
            await this._shops.load();
        }
    }

    private async _publish() {
        const result = await this._publishOp.run({ shop_id: this.shopId });
        if (result !== null) await this._shops.load();
    }

    private async _suspend() {
        const result = await this._suspendOp.run({ shop_id: this.shopId });
        if (result !== null) await this._shops.load();
    }

    private async _connectTelegram() {
        const token = this._botToken.trim();
        if (token.length < 20) return;
        const result = await this._telegramConnectOp.run({ shop_id: this.shopId, bot_token: token });
        if (result !== null) {
            this._botToken = '';
            await this._shops.load();
        }
    }

    private async _disconnectTelegram() {
        const result = await this._telegramDisconnectOp.run({ shop_id: this.shopId });
        if (result !== null) await this._shops.load();
    }

    private async _addDomain() {
        const domain = this._newDomain.trim().toLowerCase();
        if (domain === '') return;
        const result = await this._domainAddOp.run({ shop_id: this.shopId, domain });
        if (result !== null) {
            this._newDomain = '';
            await this._shops.load();
        }
    }

    override render() {
        const shop = this._shop();
        if (shop === null) {
            return this._shops.loading || !this._loadAttempted
                ? html`<platform-empty-state loading></platform-empty-state>`
                : html`
                    <platform-empty-state icon="store" title=${this.t('settings.shop_not_found')}>
                        <platform-button size="sm" variant="secondary" @click=${() => { this._shops.load(); }}>${this.t('settings.retry')}</platform-button>
                    </platform-empty-state>`;
        }
        const status = String(shop.status);
        const storefrontUrl = String(shop.storefront_url ?? '');
        const domains = Array.isArray(shop.domains) ? (shop.domains as Array<Record<string, unknown>>) : [];
        return html`
            <div class="wrap">
                <shop-page-head
                    .shop=${shopHeadRow(shop)}
                    shop-id=${this.shopId}
                    section=${this.t('routes.shop_settings')}
                ></shop-page-head>

                <div class="sections">
                <div class="card">
                    <div class="card-title">${this.t('settings.publish_title')}</div>
                    <div class="status-line">
                        <span>${this.t(`status.${status}`)}</span>
                        ${status !== 'published'
                            ? html`<platform-button variant="primary" size="sm" ?loading=${this._publishOp.busy} @click=${() => this._publish()}>${this.t('settings.publish_button')}</platform-button>`
                            : html`
                                <platform-button size="sm" variant="secondary" ?loading=${this._suspendOp.busy} @click=${() => this._suspend()}>${this.t('settings.suspend_button')}</platform-button>
                                <a class="hint" href="/shop/api/v1/public/s/${encodeURIComponent(String(shop.slug))}" target="_blank" rel="noopener">${storefrontUrl}</a>
                            `}
                    </div>
                    <div class="hint">${this.t('settings.publish_hint')}</div>
                    ${status === 'published'
                        ? html`
                            <div class="qr-row">
                                <img class="qr" src="/shop/api/v1/public/storefront/${String(shop.slug)}/qr.svg" alt="QR" width="112" height="112">
                                <div>
                                    <div class="hint">${this.t('settings.qr_hint')}</div>
                                    <a class="qr-link" href="/shop/api/v1/public/storefront/${String(shop.slug)}/qr.svg" download="storefront-qr.svg">${this.t('settings.qr_download')}</a>
                                </div>
                            </div>
                            <div class="hint">${this.t('settings.embed_hint')}</div>
                            <code class="embed">&lt;iframe src="${storefrontUrl}?embed=1" style="width:100%;max-width:480px;height:640px;border:0;border-radius:16px"&gt;&lt;/iframe&gt;</code>`
                        : html``}
                </div>

                <div class="card">
                    <div class="card-title">${this.t('settings.profile_title')}</div>
                    <input id="brand-logo-input" type="file" accept="image/*" style="display:none" @change=${(e: Event) => this._uploadBrandImage('logo', e)}>
                    <input id="brand-cover-input" type="file" accept="image/*" style="display:none" @change=${(e: Event) => this._uploadBrandImage('cover', e)}>
                    <div class="brand">
                        <button class="brand-tile" ?disabled=${this._uploadOp.busy} @click=${() => this._pickBrandImage('logo')}>
                            ${this._logoFileId === ''
                                ? html`<platform-icon name="image" size="18"></platform-icon><span>${this.t('settings.logo')}</span>`
                                : html`<img src="/shop/api/v1/files/download/${this._logoFileId}" alt=""><span class="veil">${this.t('settings.replace_photo')}</span>`}
                        </button>
                        <button class="brand-tile cover" ?disabled=${this._uploadOp.busy} @click=${() => this._pickBrandImage('cover')}>
                            ${this._coverFileId === ''
                                ? html`<platform-icon name="image" size="18"></platform-icon><span>${this.t('settings.cover')}</span>`
                                : html`<img src="/shop/api/v1/files/download/${this._coverFileId}" alt=""><span class="veil">${this.t('settings.replace_photo')}</span>`}
                        </button>
                    </div>
                    <div class="hint">${this.t('settings.brand_hint')}</div>
                    <div class="ai-row">
                        <platform-button size="sm" variant="accent" ?loading=${this._aiGenerateCoverOp.busy} ?disabled=${this._name.trim() === ''}
                            title=${this.t('settings.ai_cover_hint')}
                            @click=${() => this._aiGenerateCover()}
                        ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('settings.ai_generate_cover')}</platform-button>
                        <platform-button size="sm" variant="accent" ?loading=${this._aiGenerateLogoOp.busy} ?disabled=${this._name.trim() === ''}
                            title=${this.t('settings.ai_logo_hint')}
                            @click=${() => this._aiGenerateLogo()}
                        ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('settings.ai_generate_logo')}</platform-button>
                    </div>
                    <platform-field type="string" mode="edit" label=${this.t('settings.field_name')} .value=${this._name}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._name = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-field>
                    <platform-field type="text" mode="edit" label=${this.t('settings.field_description')} .value=${this._description}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._description = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-field>
                    <div class="ai-row">
                        <platform-button size="sm" variant="accent" ?loading=${this._aiDescribeShopOp.busy} ?disabled=${this._name.trim() === ''}
                            title=${this.t('settings.ai_describe_hint')}
                            @click=${() => this._aiDescribeShop()}
                        ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('settings.ai_describe')}</platform-button>
                    </div>
                    <div class="row">
                        <platform-field type="string" mode="edit" label=${this.t('settings.field_phone')} .value=${this._phone}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._phone = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                        <platform-field type="string" mode="edit" label=${this.t('settings.field_city')} .value=${this._city}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._city = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                    </div>
                    <platform-field type="string" mode="edit" label=${this.t('settings.field_address')} .value=${this._address}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._address = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-field>
                </div>

                <div class="card">
                    <div class="card-title">${this.t('settings.delivery_title')}</div>
                    <div class="row">
                        <platform-switch ?checked=${this._pickupEnabled} label=${this.t('settings.pickup')}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._pickupEnabled = Boolean(e.detail.value); }}
                        ></platform-switch>
                        <platform-switch ?checked=${this._deliveryEnabled} label=${this.t('settings.delivery')}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._deliveryEnabled = Boolean(e.detail.value); }}
                        ></platform-switch>
                    </div>
                    <div class="row">
                        <platform-field type="number" mode="edit" label=${this.t('settings.field_delivery_fee')} .value=${this._deliveryFee}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._deliveryFee = typeof e.detail.value === 'number' ? String(e.detail.value) : typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                        <platform-field type="number" mode="edit" label=${this.t('settings.field_min_order')} .value=${this._minOrder}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._minOrder = typeof e.detail.value === 'number' ? String(e.detail.value) : typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">${this.t('settings.hours_title')}</div>
                    <div class="hours">
                        ${this._hours.map((day, index) => html`
                            <div class="day-row ${day.closed ? 'off' : ''}">
                                <span class="day-name">${this.t(`settings.day_${index}`)}</span>
                                <platform-field type="string" mode="edit" label=${this.t('settings.hours_from')} .value=${day.open}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._setHour(index, 'open', e.detail.value)}
                                ></platform-field>
                                <span class="dash">—</span>
                                <platform-field type="string" mode="edit" label=${this.t('settings.hours_to')} .value=${day.close}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._setHour(index, 'close', e.detail.value)}
                                ></platform-field>
                                <span class="closed-label">
                                    <platform-switch ?checked=${day.closed}
                                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._setHour(index, 'closed', e.detail.value)}
                                    ></platform-switch>
                                    ${this.t('settings.closed')}
                                </span>
                            </div>
                        `)}
                    </div>
                    <div class="hint">${this.t('settings.hours_hint')}</div>
                </div>

                <div class="card">
                    <div class="card-title">${this.t('settings.domains_title')}</div>
                    <div class="hint">${String(shop.slug)}.linnex.io</div>
                    ${domains.map((d) => html`<div class="row"><span>${d.domain}</span><span class="hint">${d.status}</span></div>`)}
                    <div class="row">
                        <platform-field type="string" mode="edit" label=${this.t('settings.field_domain')} .value=${this._newDomain}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newDomain = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                        <platform-button size="sm" variant="secondary" ?loading=${this._domainAddOp.busy} ?disabled=${this._newDomain.trim() === ''} @click=${() => this._addDomain()}>
                            ${this.t('settings.domain_add')}
                        </platform-button>
                    </div>
                    <div class="hint">${this.t('settings.domains_hint')}</div>
                </div>

                <div class="card">
                    <div class="card-title">${this.t('settings.telegram_title')}</div>
                    ${shop.telegram_connected
                        ? html`
                            <div class="status-line">
                                <span>${shop.telegram_chat_id
                                    ? this.t('settings.telegram_bound')
                                    : this.t('settings.telegram_connected')}</span>
                                <platform-button size="sm" variant="secondary" ?loading=${this._telegramDisconnectOp.busy} @click=${() => this._disconnectTelegram()}>
                                    ${this.t('settings.telegram_disconnect')}
                                </platform-button>
                            </div>
                            <div class="hint">${this.t('settings.telegram_bound_hint')}</div>
                        `
                        : html`
                            <div class="row">
                                <platform-field type="string" mode="edit" label=${this.t('settings.field_bot_token')} .value=${this._botToken}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._botToken = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                                ></platform-field>
                                <platform-button size="sm" variant="primary" ?loading=${this._telegramConnectOp.busy} ?disabled=${this._botToken.trim().length < 20} @click=${() => this._connectTelegram()}>
                                    ${this.t('settings.telegram_connect')}
                                </platform-button>
                            </div>
                            <div class="hint">${this.t('settings.telegram_hint')}</div>
                        `}
                </div>

                </div>

                <platform-button variant="primary" ?loading=${this._updateOp.busy} @click=${() => this._save()}>
                    ${this.t('settings.save')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('shop-settings-page', ShopSettingsPage);
