/**
 * Настройки магазина: master-detail — слева пять разделов, справа одна
 * секция целиком. Активный раздел — search-параметр `?section=` того же
 * маршрута `shop_settings`; правки копятся в sticky-панель «Сохранить».
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import '../components/shop-hours-editor.js';
import type { ShopDayHours } from '../components/shop-hours-editor.js';
import '../components/shop-brand-editor.js';
import '../components/shop-tables-editor.js';
import '../components/shop-zone-map.js';

const SECTIONS = ['storefront', 'profile', 'hours', 'delivery', 'notifications'] as const;
type SettingsSection = (typeof SECTIONS)[number];

const SECTION_ICONS: Record<SettingsSection, string> = {
    storefront: 'store',
    profile: 'edit',
    hours: 'schedule',
    delivery: 'truck',
    notifications: 'bell-ring',
};

const STATUS_TONES: Record<string, string> = {
    draft: 'var(--text-tertiary)',
    published: 'var(--success)',
    suspended: 'var(--warning)',
};

interface ChecklistItem {
    key: string;
    done: boolean;
    optional: boolean;
    section: SettingsSection | null;
}

interface FormSnapshot {
    name: string;
    description: string;
    phone: string;
    city: string;
    address: string;
    deliveryEnabled: boolean;
    pickupEnabled: boolean;
    onsiteEnabled: boolean;
    deliveryFee: string;
    minOrder: string;
    prepMinutes: string;
    courierMode: string;
    deliveryZone: Record<string, unknown>;
    hours: ShopDayHours[];
}

export class ShopSettingsPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _updateOp: OpController;
    private _publishOp: OpController;
    private _suspendOp: OpController;
    private _domainAddOp: OpController;
    private _telegramConnectOp: OpController;
    private _telegramDisconnectOp: OpController;
    private _aiDescribeShopOp: OpController;
    private _searchSel: SelectController<unknown>;

    declare _name: string;
    declare _description: string;
    declare _phone: string;
    declare _city: string;
    declare _address: string;
    declare _deliveryEnabled: boolean;
    declare _pickupEnabled: boolean;
    declare _onsiteEnabled: boolean;
    declare _deliveryFee: string;
    declare _minOrder: string;
    declare _prepMinutes: string;
    declare _courierMode: string;
    declare _deliveryZone: Record<string, unknown>;
    declare _newDomain: string;
    declare _botToken: string;
    declare _hours: ShopDayHours[];
    declare _loadAttempted: boolean;
    private _hydrated = false;
    private _saved: FormSnapshot | null = null;

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
        _onsiteEnabled: { state: true },
        _deliveryFee: { state: true },
        _minOrder: { state: true },
        _prepMinutes: { state: true },
        _courierMode: { state: true },
        _deliveryZone: { state: true },
        _newDomain: { state: true },
        _botToken: { state: true },
        _hours: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
            .head { flex-shrink: 0; padding: var(--space-5) var(--space-6) 0; }
            .settings {
                flex: 1;
                min-height: 0;
                display: grid;
                grid-template-columns: 240px minmax(0, 1fr);
            }
            .nav {
                padding: var(--space-3) var(--space-3) var(--space-3) var(--space-6);
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                border: 0;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                text-align: left;
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                transition: background var(--motion-duration-micro),
                            color var(--motion-duration-micro);
            }
            .nav-item:hover { background: color-mix(in srgb, var(--text-primary) 5%, transparent); }
            .nav-item.active {
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
            }
            .nav-item platform-icon { flex-shrink: 0; }
            .nav-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .nav-badge {
                min-width: 18px;
                height: 18px;
                border-radius: 9px;
                background: color-mix(in srgb, var(--warning) 22%, transparent);
                color: var(--warning);
                font-size: var(--text-2xs, 10px);
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0 var(--space-1);
            }
            .content {
                overflow-y: auto;
                padding: var(--space-2) var(--space-6) var(--space-6) var(--space-4);
            }
            .section { max-width: 680px; display: flex; flex-direction: column; gap: var(--space-4); }
            .section-head { margin-bottom: var(--space-1); }
            .section-title {
                margin: 0;
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .section-sub { margin: var(--space-1) 0 0; font-size: var(--text-sm); color: var(--text-tertiary); }
            .card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hero {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-5);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hero.published {
                border-color: color-mix(in srgb, var(--success) 40%, transparent);
                background: color-mix(in srgb, var(--success) 6%, transparent);
            }
            .hero.draft {
                border-color: color-mix(in srgb, var(--accent) 35%, transparent);
                background: color-mix(in srgb, var(--accent) 6%, transparent);
            }
            .hero.suspended {
                border-color: color-mix(in srgb, var(--warning) 40%, transparent);
                background: color-mix(in srgb, var(--warning) 6%, transparent);
            }
            .hero-top { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
            .hero-status {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .hero-status .dot { width: 10px; height: 10px; border-radius: 50%; }
            .hero-text { font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.5; }
            .hero-actions { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
            .link-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--accent);
                min-width: 0;
            }
            .link-chip .url { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .icon-btn {
                border: 0;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-sm);
                padding: 0;
            }
            .icon-btn:hover { color: var(--accent); }
            .progress-row { display: flex; align-items: baseline; gap: var(--space-2); }
            .progress-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .progress-count { font-size: var(--text-sm); color: var(--text-tertiary); }
            .progress-bar {
                height: 6px;
                border-radius: 3px;
                background: color-mix(in srgb, var(--text-primary) 8%, transparent);
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                border-radius: 3px;
                background: var(--success);
                transition: width var(--motion-duration-standard);
            }
            .checklist { display: flex; flex-direction: column; }
            .check-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) 0;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .check-item + .check-item { border-top: 1px solid color-mix(in srgb, var(--text-primary) 6%, transparent); }
            .check-item platform-icon.mark { color: var(--text-tertiary); flex-shrink: 0; }
            .check-item.done platform-icon.mark { color: var(--success); }
            .check-item.done .check-label { color: var(--text-tertiary); }
            .check-label { flex: 1; min-width: 0; }
            .check-optional { font-size: var(--text-xs); color: var(--text-tertiary); }
            .check-go {
                border: 0;
                background: transparent;
                color: var(--accent);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
            }
            .check-go:hover { text-decoration: underline; }
            .qr-card { display: flex; gap: var(--space-4); align-items: center; flex-wrap: wrap; }
            .qr { border-radius: var(--radius-sm); background: #fff; padding: var(--space-1); }
            .qr-info { display: flex; flex-direction: column; gap: var(--space-2); flex: 1; min-width: 200px; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
            .advanced {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
            }
            .advanced summary {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                cursor: pointer;
                list-style: none;
            }
            .advanced summary::-webkit-details-marker { display: none; }
            .advanced summary .chevron { transition: transform var(--motion-duration-micro); }
            .advanced[open] summary .chevron { transform: rotate(90deg); }
            .advanced-body {
                padding: 0 var(--space-4) var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .advanced-block { display: flex; flex-direction: column; gap: var(--space-2); }
            .advanced-title { font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--text-primary); }
            .embed {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--bg-inset);
                border-radius: var(--radius-sm);
                padding: var(--space-2);
                word-break: break-all;
                user-select: all;
            }
            .row { display: flex; gap: var(--space-3); align-items: center; }
            .row > platform-field { flex: 1; min-width: 0; }
            .domain-row { display: flex; justify-content: space-between; align-items: center; font-size: var(--text-sm); color: var(--text-primary); }
            .option {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
                transition: border-color var(--motion-duration-micro);
            }
            .option.on { border-color: color-mix(in srgb, var(--accent) 50%, transparent); }
            .option-icon {
                width: 44px;
                height: 44px;
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                color: var(--text-secondary);
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .option.on .option-icon {
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                color: var(--accent);
            }
            .option-body { flex: 1; min-width: 0; }
            .option-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--text-primary); }
            .option-desc { font-size: var(--text-sm); color: var(--text-tertiary); margin-top: 2px; }
            .option-fields {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
            }
            .steps { display: flex; flex-direction: column; gap: var(--space-3); }
            .step { display: flex; gap: var(--space-3); align-items: flex-start; }
            .step-num {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                color: var(--accent);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .step-text { font-size: var(--text-sm); color: var(--text-secondary); line-height: 1.5; padding-top: 2px; }
            .connected { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
            .savebar {
                position: sticky;
                bottom: var(--space-3);
                display: flex;
                align-items: center;
                gap: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-elevated);
                padding: var(--space-3) var(--space-4);
                box-shadow: 0 4px 16px var(--glass-shadow-subtle);
            }
            .savebar-text { flex: 1; font-size: var(--text-sm); color: var(--text-secondary); }
            @media (max-width: 767px) {
                .head { padding: var(--space-4) var(--space-4) 0; }
                .settings { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
                .nav {
                    flex-direction: row;
                    overflow-x: auto;
                    padding: var(--space-2) var(--space-4);
                    gap: var(--space-2);
                }
                .nav-item { width: auto; flex-shrink: 0; }
                .nav-badge { display: none; }
                .content { padding: var(--space-2) var(--space-4) var(--space-4); }
                .option-fields { grid-template-columns: 1fr; }
            }
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
        this._onsiteEnabled = false;
        this._deliveryFee = '';
        this._minOrder = '';
        this._prepMinutes = '';
        this._courierMode = 'scooter';
        this._deliveryZone = {};
        this._newDomain = '';
        this._botToken = '';
        this._hours = [];
        this._shops = this.useResource('shop/shops', { autoload: true });
        this._updateOp = this.useOp('shop/shop_update');
        this._publishOp = this.useOp('shop/shop_publish');
        this._suspendOp = this.useOp('shop/shop_suspend');
        this._domainAddOp = this.useOp('shop/domain_add');
        this._telegramConnectOp = this.useOp('shop/telegram_connect');
        this._telegramDisconnectOp = this.useOp('shop/telegram_disconnect');
        this._aiDescribeShopOp = this.useOp('shop/ai_describe_shop');
        this._searchSel = this.select((s) => s.router.search);
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
        this._onsiteEnabled = Boolean(shop.onsite_enabled);
        this._deliveryFee = String((Number(shop.delivery_fee_minor ?? 0) / 100) || '');
        this._minOrder = String((Number(shop.min_order_minor ?? 0) / 100) || '');
        this._prepMinutes = String(Number(shop.prep_minutes ?? 0) || '');
        this._courierMode = String(shop.courier_mode ?? 'scooter');
        const zone = shop.delivery_zone;
        this._deliveryZone = zone !== null && typeof zone === 'object'
            ? (zone as Record<string, unknown>)
            : {};
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
        this._saved = this._capture();
        return true;
    }

    private _capture(): FormSnapshot {
        return {
            name: this._name,
            description: this._description,
            phone: this._phone,
            city: this._city,
            address: this._address,
            deliveryEnabled: this._deliveryEnabled,
            pickupEnabled: this._pickupEnabled,
            onsiteEnabled: this._onsiteEnabled,
            deliveryFee: this._deliveryFee,
            minOrder: this._minOrder,
            prepMinutes: this._prepMinutes,
            courierMode: this._courierMode,
            deliveryZone: this._deliveryZone,
            hours: this._hours.map((d) => ({ ...d })),
        };
    }

    private get _dirty(): boolean {
        return this._saved !== null && JSON.stringify(this._capture()) !== JSON.stringify(this._saved);
    }

    private _cancel() {
        if (this._saved === null) return;
        const s = this._saved;
        this._name = s.name;
        this._description = s.description;
        this._phone = s.phone;
        this._city = s.city;
        this._address = s.address;
        this._deliveryEnabled = s.deliveryEnabled;
        this._pickupEnabled = s.pickupEnabled;
        this._onsiteEnabled = s.onsiteEnabled;
        this._deliveryFee = s.deliveryFee;
        this._minOrder = s.minOrder;
        this._prepMinutes = s.prepMinutes;
        this._courierMode = s.courierMode;
        this._deliveryZone = s.deliveryZone;
        this._hours = s.hours.map((d) => ({ ...d }));
    }

    private get _section(): SettingsSection {
        const raw = this._searchSel.value;
        const section = typeof raw === 'string' ? new URLSearchParams(raw).get('section') : null;
        return section !== null && (SECTIONS as readonly string[]).includes(section)
            ? section as SettingsSection
            : 'storefront';
    }

    private _goSection(section: SettingsSection) {
        this.navigate('shop_settings', { shopId: this.shopId }, { search: `?section=${section}` });
    }

    private _toMinor(value: string): number {
        const parsed = parseFloat(value.replace(',', '.'));
        return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 100) : 0;
    }

    private _toInt(value: string): number {
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) && parsed >= 0 ? Math.min(parsed, 600) : 0;
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

    private _checklist(shop: Record<string, unknown>): ChecklistItem[] {
        const wh = shop.working_hours !== null && typeof shop.working_hours === 'object'
            ? shop.working_hours as Record<string, unknown>
            : {};
        return [
            { key: 'name',        done: String(shop.name ?? '') !== '',              optional: false, section: 'profile' },
            { key: 'logo',        done: typeof shop.logo_file_id === 'string',       optional: false, section: 'profile' },
            { key: 'cover',       done: typeof shop.cover_file_id === 'string',      optional: false, section: 'profile' },
            { key: 'description', done: String(shop.description ?? '') !== '',       optional: false, section: 'profile' },
            { key: 'menu',        done: Number(shop.products_count ?? 0) > 0,        optional: false, section: null },
            { key: 'hours',       done: Object.keys(wh).length > 0,                  optional: false, section: 'hours' },
            { key: 'order',       done: Boolean(shop.pickup_enabled) || Boolean(shop.delivery_enabled) || Boolean(shop.onsite_enabled), optional: false, section: 'delivery' },
            { key: 'notify',      done: Boolean(shop.telegram_connected),            optional: true,  section: 'notifications' },
        ];
    }

    private _pendingBySection(items: ChecklistItem[]): Map<SettingsSection, number> {
        const counts = new Map<SettingsSection, number>();
        for (const item of items) {
            if (item.done || item.section === null) continue;
            counts.set(item.section, (counts.get(item.section) ?? 0) + 1);
        }
        return counts;
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
            onsite_enabled: this._onsiteEnabled,
            delivery_fee_minor: this._toMinor(this._deliveryFee),
            min_order_minor: this._toMinor(this._minOrder),
            prep_minutes: this._toInt(this._prepMinutes),
            courier_mode: this._courierMode,
            delivery_zone: this._deliveryZone,
            working_hours: this._collectHours(),
        });
        if (result !== null) {
            this._saved = this._capture();
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

    private _copyLink(url: string) {
        this.copyToClipboard(url, {
            success_i18n_key: 'shop:settings.link_copied',
            error_i18n_key: 'shop:settings.copy_failed',
        });
    }

    private _goChecklist(item: ChecklistItem) {
        if (item.section === null) {
            this.navigate('shop_menu', { shopId: this.shopId });
            return;
        }
        this._goSection(item.section);
    }

    private _renderSectionHead(titleKey: string, subKey: string) {
        return html`
            <div class="section-head">
                <h2 class="section-title">${this.t(titleKey)}</h2>
                <p class="section-sub">${this.t(subKey)}</p>
            </div>
        `;
    }

    private _renderStorefront(shop: Record<string, unknown>) {
        const status = String(shop.status);
        const slug = String(shop.slug);
        const storefrontUrl = String(shop.storefront_url ?? '');
        const publicPath = `/shop/api/v1/public/s/${encodeURIComponent(slug)}`;
        const items = this._checklist(shop);
        const done = items.filter((i) => i.done).length;
        const pct = Math.round((done / items.length) * 100);
        const domains = Array.isArray(shop.domains) ? (shop.domains as Array<Record<string, unknown>>) : [];
        return html`
            ${this._renderSectionHead('settings.nav_storefront', 'settings.storefront_sub')}

            <div class="hero ${status}">
                <div class="hero-top">
                    <span class="hero-status">
                        <span class="dot" style="background:${STATUS_TONES[status] ?? 'var(--text-tertiary)'}"></span>
                        ${this.t(`status.${status}`)}
                    </span>
                </div>
                <div class="hero-text">
                    ${status === 'published' ? this.t('settings.hero_published') : ''}
                    ${status === 'draft' ? this.t('settings.hero_draft') : ''}
                    ${status === 'suspended' ? this.t('settings.hero_suspended') : ''}
                </div>
                <div class="hero-actions">
                    ${status === 'published'
                        ? html`
                            <span class="link-chip">
                                <span class="url">${storefrontUrl}</span>
                                <button class="icon-btn" title=${this.t('settings.copy_link')} @click=${() => this._copyLink(storefrontUrl)}>
                                    <platform-icon name="copy" size="14"></platform-icon>
                                </button>
                            </span>
                            <platform-button size="sm" variant="secondary" @click=${() => { window.open(publicPath, '_blank', 'noopener'); }}>
                                <platform-icon name="external-link" size="14"></platform-icon> ${this.t('settings.open_storefront')}
                            </platform-button>
                            <platform-button size="sm" variant="secondary" ?busy=${this._suspendOp.busy} @click=${() => this._suspend()}>
                                ${this.t('settings.suspend_button')}
                            </platform-button>`
                        : html`
                            <platform-button variant="primary" ?busy=${this._publishOp.busy} @click=${() => this._publish()}>
                                ${this.t('settings.publish_button')}
                            </platform-button>`}
                </div>
            </div>

            ${status !== 'published'
                ? html`
                    <div class="card">
                        <div class="progress-row">
                            <span class="progress-title">${this.t('settings.checklist_title')}</span>
                            <span class="progress-count">${this.t('settings.checklist_progress', { done, total: items.length })}</span>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
                        <div class="checklist">
                            ${items.map((item) => html`
                                <div class="check-item ${item.done ? 'done' : ''}">
                                    <platform-icon class="mark" name=${item.done ? 'check' : 'circle'} size="15"></platform-icon>
                                    <span class="check-label">
                                        ${this.t(`settings.check_${item.key}`)}
                                        ${item.optional ? html`<span class="check-optional"> · ${this.t('settings.optional')}</span>` : nothing}
                                    </span>
                                    ${!item.done
                                        ? html`
                                            <button class="check-go" @click=${() => this._goChecklist(item)}>
                                                ${this.t('settings.check_go')} <platform-icon name="arrow-right" size="13"></platform-icon>
                                            </button>`
                                        : nothing}
                                </div>
                            `)}
                        </div>
                        ${done === items.length
                            ? html`<div class="hint">${this.t('settings.checklist_ready')}</div>`
                            : nothing}
                    </div>`
                : nothing}

            ${status === 'published'
                ? html`
                    <div class="card">
                        <div class="qr-card">
                            <img class="qr" src="/shop/api/v1/public/storefront/${encodeURIComponent(slug)}/qr.svg" alt="QR" width="128" height="128">
                            <div class="qr-info">
                                <div class="hint">${this.t('settings.qr_hint')}</div>
                                <div class="row">
                                    <a class="qr-link" href="/shop/api/v1/public/storefront/${encodeURIComponent(slug)}/qr.svg" download="storefront-qr.svg">
                                        <platform-button size="sm" variant="secondary">
                                            <platform-icon name="download" size="14"></platform-icon> ${this.t('settings.qr_download')}
                                        </platform-button>
                                    </a>
                                    <platform-button size="sm" variant="secondary" @click=${() => this.navigate('shop_builder', { shopId: this.shopId })}>
                                        <platform-icon name="edit" size="14"></platform-icon> ${this.t('settings.theme_link')}
                                    </platform-button>
                                </div>
                            </div>
                        </div>
                    </div>`
                : nothing}

            <details class="advanced">
                <summary>
                    <platform-icon class="chevron" name="chevron-right" size="14"></platform-icon>
                    ${this.t('settings.advanced_title')}
                </summary>
                <div class="advanced-body">
                    <div class="advanced-block">
                        <div class="advanced-title">${this.t('settings.embed_title')}</div>
                        <code class="embed">&lt;iframe src="${storefrontUrl}?embed=1" style="width:100%;max-width:480px;height:640px;border:0;border-radius:16px"&gt;&lt;/iframe&gt;</code>
                        <div>
                            <platform-button size="sm" variant="secondary"
                                @click=${() => this._copyLink(`<iframe src="${storefrontUrl}?embed=1" style="width:100%;max-width:480px;height:640px;border:0;border-radius:16px"></iframe>`)}>
                                <platform-icon name="copy" size="14"></platform-icon> ${this.t('settings.copy_code')}
                            </platform-button>
                        </div>
                    </div>
                    <div class="advanced-block">
                        <div class="advanced-title">${this.t('settings.domains_title')}</div>
                        <div class="hint">${this.t('settings.domains_hint')}</div>
                        ${domains.map((d) => html`
                            <div class="domain-row"><span>${d.domain}</span><span class="hint">${d.status}</span></div>
                        `)}
                        <div class="row">
                            <platform-field type="string" mode="edit" label=${this.t('settings.field_domain')} .value=${this._newDomain}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newDomain = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                            ></platform-field>
                            <platform-button size="sm" variant="secondary" ?busy=${this._domainAddOp.busy} ?disabled=${this._newDomain.trim() === ''} @click=${() => this._addDomain()}>
                                ${this.t('settings.domain_add')}
                            </platform-button>
                        </div>
                    </div>
                </div>
            </details>
        `;
    }

    private _renderProfile(shop: Record<string, unknown>) {
        const logoFileId = typeof shop.logo_file_id === 'string' ? shop.logo_file_id : '';
        const coverFileId = typeof shop.cover_file_id === 'string' ? shop.cover_file_id : '';
        return html`
            ${this._renderSectionHead('settings.nav_profile', 'settings.profile_sub')}
            <div class="card">
                <shop-brand-editor
                    shop-id=${this.shopId}
                    logo-file-id=${logoFileId}
                    cover-file-id=${coverFileId}
                    shop-name=${this._name}
                    description=${this._description}
                    @updated=${() => { this._shops.load(); }}
                ></shop-brand-editor>
            </div>
            <div class="card">
                <platform-field type="string" mode="edit" label=${this.t('settings.field_name')} .value=${this._name}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._name = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field type="text" mode="edit" label=${this.t('settings.field_description')} .value=${this._description}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._description = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <div class="row" style="justify-content: flex-end">
                    <platform-button size="sm" variant="accent" ?busy=${this._aiDescribeShopOp.busy} ?disabled=${this._name.trim() === ''}
                        title=${this.t('settings.ai_describe_hint')}
                        @click=${() => this._aiDescribeShop()}
                    ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('settings.ai_describe')}</platform-button>
                </div>
            </div>
            <div class="card">
                <platform-field type="string" mode="edit" label=${this.t('settings.field_phone')} .value=${this._phone}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._phone = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field type="string" mode="edit" label=${this.t('settings.field_city')} .value=${this._city}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._city = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field type="string" mode="edit" label=${this.t('settings.field_address')} .value=${this._address}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._address = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
            </div>
        `;
    }

    private _renderHours() {
        return html`
            ${this._renderSectionHead('settings.nav_hours', 'settings.hours_sub')}
            <div class="card">
                <shop-hours-editor
                    .hours=${this._hours}
                    @change=${(e: CustomEvent<{ hours: ShopDayHours[] }>) => { this._hours = e.detail.hours; }}
                ></shop-hours-editor>
                <div class="hint">${this.t('settings.hours_hint')}</div>
            </div>
        `;
    }

    private _renderDelivery(shop: Record<string, unknown>) {
        const slug = String(shop.slug ?? '');
        return html`
            ${this._renderSectionHead('settings.nav_delivery', 'settings.delivery_sub')}
            <div class="option ${this._pickupEnabled ? 'on' : ''}">
                <span class="option-icon"><platform-icon name="store" size="22"></platform-icon></span>
                <span class="option-body">
                    <div class="option-title">${this.t('settings.pickup')}</div>
                    <div class="option-desc">${this.t('settings.pickup_desc')}</div>
                </span>
                <platform-switch ?checked=${this._pickupEnabled}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._pickupEnabled = Boolean(e.detail.value); }}
                ></platform-switch>
            </div>
            <div class="option ${this._deliveryEnabled ? 'on' : ''}">
                <span class="option-icon"><platform-icon name="truck" size="22"></platform-icon></span>
                <span class="option-body">
                    <div class="option-title">${this.t('settings.delivery')}</div>
                    <div class="option-desc">${this.t('settings.delivery_desc')}</div>
                </span>
                <platform-switch ?checked=${this._deliveryEnabled}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._deliveryEnabled = Boolean(e.detail.value); }}
                ></platform-switch>
            </div>
            <div class="option ${this._onsiteEnabled ? 'on' : ''}">
                <span class="option-icon"><platform-icon name="restaurant" size="22"></platform-icon></span>
                <span class="option-body">
                    <div class="option-title">${this.t('settings.onsite')}</div>
                    <div class="option-desc">${this.t('settings.onsite_desc')}</div>
                </span>
                <platform-switch ?checked=${this._onsiteEnabled}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._onsiteEnabled = Boolean(e.detail.value); }}
                ></platform-switch>
            </div>
            ${this._onsiteEnabled
                ? html`
                    <div class="card">
                        <shop-tables-editor shop-id=${this.shopId} shop-slug=${slug}></shop-tables-editor>
                    </div>`
                : nothing}
            ${this._deliveryEnabled
                ? html`
                    <div class="card">
                        <div class="option-fields">
                            <platform-field type="number" mode="edit" label=${this.t('settings.field_delivery_fee')} .value=${this._deliveryFee}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._deliveryFee = typeof e.detail.value === 'number' ? String(e.detail.value) : typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                            ></platform-field>
                            <platform-field type="number" mode="edit" label=${this.t('settings.field_min_order')} .value=${this._minOrder}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._minOrder = typeof e.detail.value === 'number' ? String(e.detail.value) : typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                            ></platform-field>
                            <platform-field type="number" mode="edit" label=${this.t('settings.field_prep_minutes')} .value=${this._prepMinutes}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._prepMinutes = typeof e.detail.value === 'number' ? String(e.detail.value) : typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                            ></platform-field>
                            <platform-field type="enum" mode="edit" label=${this.t('settings.field_courier_mode')} .value=${this._courierMode}
                                .config=${{ values: ['scooter', 'bike', 'foot', 'car'].map((m) => ({ value: m, label: this.t(`settings.courier_mode_${m}`) })) }}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._courierMode = typeof e.detail.value === 'string' ? e.detail.value : 'scooter'; }}
                            ></platform-field>
                        </div>
                    </div>
                    <div class="card">
                        <div class="option-title" style="margin-bottom: var(--space-1)">${this.t('settings.zone_title')}</div>
                        <div class="option-desc" style="margin-bottom: var(--space-3)">${this.t('settings.zone_desc')}</div>
                        <shop-zone-map
                            .zone=${this._deliveryZone}
                            .address=${[this._city, this._address].filter(Boolean).join(', ')}
                            .shopId=${this.shopId}
                            @zone-changed=${(e: CustomEvent<{ zone: Record<string, unknown> }>) => { this._deliveryZone = e.detail.zone; }}
                        ></shop-zone-map>
                    </div>`
                : nothing}
        `;
    }

    private _renderNotifications(shop: Record<string, unknown>) {
        return html`
            ${this._renderSectionHead('settings.nav_notifications', 'settings.notifications_sub')}
            ${shop.telegram_connected
                ? html`
                    <div class="card">
                        <div class="connected">
                            <platform-icon name="check" size="18" style="color: var(--success)"></platform-icon>
                            <span class="option-title">${shop.telegram_chat_id
                                ? this.t('settings.telegram_bound')
                                : this.t('settings.telegram_connected')}</span>
                            <platform-button size="sm" variant="secondary" ?busy=${this._telegramDisconnectOp.busy} @click=${() => this._disconnectTelegram()}>
                                ${this.t('settings.telegram_disconnect')}
                            </platform-button>
                        </div>
                        <div class="hint">${this.t('settings.telegram_bound_hint')}</div>
                    </div>`
                : html`
                    <div class="card">
                        <div class="steps">
                            <div class="step">
                                <span class="step-num">1</span>
                                <span class="step-text">${this.t('settings.tg_step_1')}</span>
                            </div>
                            <div class="step">
                                <span class="step-num">2</span>
                                <span class="step-text">${this.t('settings.tg_step_2')}</span>
                            </div>
                            <div class="step">
                                <span class="step-num">3</span>
                                <span class="step-text">${this.t('settings.tg_step_3')}</span>
                            </div>
                        </div>
                        <platform-field type="string" mode="edit" label=${this.t('settings.field_bot_token')} .value=${this._botToken}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._botToken = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                        ></platform-field>
                        <div class="row" style="justify-content: flex-end">
                            <platform-button variant="primary" ?busy=${this._telegramConnectOp.busy} ?disabled=${this._botToken.trim().length < 20} @click=${() => this._connectTelegram()}>
                                ${this.t('settings.telegram_connect')}
                            </platform-button>
                        </div>
                    </div>`}
        `;
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
        const section = this._section;
        const pending = this._pendingBySection(this._checklist(shop));
        return html`
            <div class="head">
                <shop-page-head
                    .shop=${shopHeadRow(shop)}
                    shop-id=${this.shopId}
                    section=${this.t('routes.shop_settings')}
                ></shop-page-head>
            </div>
            <div class="settings">
                <nav class="nav">
                    ${SECTIONS.map((key) => {
                        const badge = pending.get(key) ?? 0;
                        return html`
                            <button class="nav-item ${section === key ? 'active' : ''}" @click=${() => this._goSection(key)}>
                                <platform-icon name=${SECTION_ICONS[key]} size="18"></platform-icon>
                                <span class="nav-label">${this.t(`settings.nav_${key}`)}</span>
                                ${badge > 0 ? html`<span class="nav-badge">${badge}</span>` : nothing}
                            </button>
                        `;
                    })}
                </nav>
                <div class="content">
                    <div class="section">
                        ${section === 'storefront' ? this._renderStorefront(shop) : nothing}
                        ${section === 'profile' ? this._renderProfile(shop) : nothing}
                        ${section === 'hours' ? this._renderHours() : nothing}
                        ${section === 'delivery' ? this._renderDelivery(shop) : nothing}
                        ${section === 'notifications' ? this._renderNotifications(shop) : nothing}
                        ${this._dirty
                            ? html`
                                <div class="savebar">
                                    <span class="savebar-text">${this.t('settings.unsaved')}</span>
                                    <platform-button size="sm" variant="secondary" @click=${() => this._cancel()}>${this.t('settings.cancel')}</platform-button>
                                    <platform-button size="sm" variant="primary" ?busy=${this._updateOp.busy} @click=${() => this._save()}>${this.t('settings.save')}</platform-button>
                                </div>`
                            : nothing}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('shop-settings-page', ShopSettingsPage);
