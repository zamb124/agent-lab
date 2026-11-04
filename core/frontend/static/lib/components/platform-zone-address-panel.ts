/**
 * <platform-zone-address-panel> — панель «какие адреса попали в зону».
 *
 * Провайдер-агностична: запрос идёт через op фабрики хоста
 * (`addressesOpName` — например 'shop/zone_addresses'), зона — GeoJSON
 * полигона прямо из редактора. Контракт ответа — geo wire:
 * `{items: GeoAddressItem[], total}`.
 *
 * События наружу (для синка маркеров на карте):
 *   addresses-changed {items}      — перерисовать маркеры
 *   address-hover    {id|null}     — подсветить маркер строки
 *
 * Requery: debounce 300мс на изменение зоны/поиска, защита от гонок
 * номером запроса. Пагинация — серверная.
 */

import { css, html, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';

import { PlatformElement } from '../platform-element/index.js';
import type { FactoryNameOfKind } from '../events/factory-registry.js';
import type { OpController } from '../base/use-resource.js';
import './platform-icon.js';
import './platform-spinner.js';

export interface GeoAddressItem {
    id: number;
    display_name: string;
    city: string;
    street: string;
    housenumber: string;
    lat: number;
    lng: number;
}

interface ZoneAddressResult {
    items: GeoAddressItem[];
    total: number;
}

const _QUERY_DEBOUNCE_MS = 300;

export class PlatformZoneAddressPanel extends PlatformElement {
    static i18nNamespace = 'geo';

    static override properties: PropertyDeclarations = {
        addressesOpName: { type: String, attribute: 'addresses-op-name' },
        zone: { attribute: false },
        pageSize: { type: Number, attribute: 'page-size' },
        _items: { state: true },
        _total: { state: true },
        _page: { state: true },
        _q: { state: true },
        _loading: { state: true },
        _failed: { state: true },
        _hoveredId: { state: true },
    };

    declare addressesOpName: FactoryNameOfKind<'async-op'> | null;
    declare zone: Record<string, unknown> | null;
    declare pageSize: number;
    declare _items: GeoAddressItem[];
    declare _total: number;
    declare _page: number;
    declare _q: string;
    declare _loading: boolean;
    declare _failed: boolean;
    declare _hoveredId: number | null;

    private _op: OpController | null = null;
    private _reqSeq = 0;
    private _debounceTimer: number | null = null;

    constructor() {
        super();
        this.addressesOpName = null;
        this.zone = null;
        this.pageSize = 50;
        this._items = [];
        this._total = 0;
        this._page = 0;
        this._q = '';
        this._loading = false;
        this._failed = false;
        this._hoveredId = null;
    }

    static override styles: CSSResultGroup = css`
        :host {
            display: flex;
            flex-direction: column;
            min-width: 0;
            height: 100%;
            background: var(--glass-bg, rgba(255, 255, 255, 0.94));
            border-left: 1px solid var(--border-color, #e2e8f0);
            font-family: var(--font-family, inherit);
        }
        .search {
            padding: var(--space-3, 12px) var(--space-3, 12px) var(--space-2, 8px);
            border-bottom: 1px solid var(--border-color, #e2e8f0);
        }
        .search-box {
            display: flex;
            align-items: center;
            gap: var(--space-2, 8px);
            background: var(--input-bg, #f8fafc);
            border: 1px solid var(--border-color, #e2e8f0);
            border-radius: var(--radius-md, 10px);
            padding: 8px 12px;
            transition: border-color 0.15s, box-shadow 0.15s;
        }
        .search-box:focus-within {
            border-color: var(--accent, #6366f1);
            box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent, #6366f1) 15%, transparent);
        }
        .search-box platform-icon { color: var(--text-secondary, #64748b); flex: none; }
        .search-box input {
            flex: 1;
            border: none;
            background: transparent;
            outline: none;
            font-size: var(--font-size-md, 14px);
            color: var(--text-primary, #0f172a);
            min-width: 0;
        }
        .search-box input::placeholder { color: var(--text-tertiary, #94a3b8); }
        .count {
            display: flex;
            align-items: center;
            gap: var(--space-2, 8px);
            padding: var(--space-2, 8px) var(--space-3, 12px);
            font-size: var(--font-size-sm, 13px);
            color: var(--text-secondary, #64748b);
            border-bottom: 1px solid var(--border-color, #e2e8f0);
            min-height: 20px;
        }
        .count b { color: var(--text-primary, #0f172a); font-weight: 600; }
        .list {
            flex: 1;
            overflow-y: auto;
            overscroll-behavior: contain;
        }
        .row {
            display: flex;
            align-items: center;
            gap: var(--space-2, 8px);
            padding: 7px var(--space-3, 12px);
            cursor: pointer;
            border-left: 2px solid transparent;
        }
        .row:hover, .row.hovered {
            background: color-mix(in srgb, var(--accent, #6366f1) 8%, transparent);
            border-left-color: var(--accent, #6366f1);
        }
        .row platform-icon { color: var(--accent, #6366f1); flex: none; }
        .row .addr {
            flex: 1;
            min-width: 0;
            font-size: var(--font-size-sm, 13px);
            color: var(--text-primary, #0f172a);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: var(--space-2, 8px);
            padding: var(--space-6, 24px) var(--space-3, 12px);
            color: var(--text-tertiary, #94a3b8);
            font-size: var(--font-size-sm, 13px);
            text-align: center;
        }
        .empty platform-icon { font-size: 28px; opacity: 0.6; }
        .pager {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-2, 8px) var(--space-3, 12px);
            border-top: 1px solid var(--border-color, #e2e8f0);
            font-size: var(--font-size-sm, 13px);
            color: var(--text-secondary, #64748b);
        }
        .pager button {
            border: none;
            background: transparent;
            color: var(--accent, #6366f1);
            font: inherit;
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 6px;
        }
        .pager button:hover:not(:disabled) { background: color-mix(in srgb, var(--accent, #6366f1) 10%, transparent); }
        .pager button:disabled { color: var(--text-tertiary, #94a3b8); cursor: default; }
        .spin { display: flex; justify-content: center; padding: var(--space-4, 16px); }
    `;

    override connectedCallback(): void {
        super.connectedCallback();
        this._query();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this._reqSeq += 1;
        if (this._debounceTimer !== null) {
            window.clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
    }

    override willUpdate(changed: Map<string, unknown>): void {
        if (changed.has('zone')) {
            this._page = 0;
            this._scheduleQuery();
        }
    }

    private _ensureOp(): OpController {
        if (this.addressesOpName === null) {
            throw new Error('platform-zone-address-panel: addressesOpName required');
        }
        this._op ??= this.useOp(this.addressesOpName);
        return this._op;
    }

    private _scheduleQuery(): void {
        if (this._debounceTimer !== null) {
            window.clearTimeout(this._debounceTimer);
        }
        this._debounceTimer = window.setTimeout(() => {
            this._debounceTimer = null;
            this._query();
        }, _QUERY_DEBOUNCE_MS);
    }

    private async _query(): Promise<void> {
        if (this.zone === null) {
            this._items = [];
            this._total = 0;
            this._loading = false;
            this._emitItems([]);
            return;
        }
        const seq = ++this._reqSeq;
        this._loading = true;
        this._failed = false;
        try {
            const result = (await this._ensureOp().run({
                zone: this.zone,
                q: this._q || null,
                limit: this.pageSize,
                offset: this._page * this.pageSize,
            })) as ZoneAddressResult;
            if (seq !== this._reqSeq) return;
            this._items = result.items;
            this._total = result.total;
            this._emitItems(this._items);
        } catch {
            if (seq !== this._reqSeq) return;
            this._failed = true;
            this._items = [];
            this._total = 0;
            this._emitItems([]);
        } finally {
            if (seq === this._reqSeq) this._loading = false;
        }
    }

    private _emitItems(items: GeoAddressItem[]): void {
        this.dispatchEvent(
            new CustomEvent('addresses-changed', {
                detail: { items },
                bubbles: true,
                composed: true,
            }),
        );
    }

    private _setHover(id: number | null, item?: GeoAddressItem): void {
        if (this._hoveredId === id) return;
        this._hoveredId = id;
        this.dispatchEvent(
            new CustomEvent('address-hover', {
                detail: { id, lat: item?.lat ?? null, lng: item?.lng ?? null },
                bubbles: true,
                composed: true,
            }),
        );
    }

    private _onSearchInput(e: InputEvent): void {
        this._q = (e.target as HTMLInputElement).value.trim();
        this._page = 0;
        this._scheduleQuery();
    }

    private _setPage(page: number): void {
        const maxPage = Math.max(0, Math.ceil(this._total / this.pageSize) - 1);
        this._page = Math.min(Math.max(0, page), maxPage);
        this._query();
    }

    private get _pageCount(): number {
        return Math.max(1, Math.ceil(this._total / this.pageSize));
    }

    private _renderRow(item: GeoAddressItem): TemplateResult {
        const hovered = item.id === this._hoveredId;
        return html`
            <div
                class="row ${hovered ? 'hovered' : ''}"
                data-address-id=${item.id}
                @mouseenter=${() => this._setHover(item.id, item)}
                @mouseleave=${() => this._setHover(null)}
            >
                <platform-icon name="pin" size="14"></platform-icon>
                <span class="addr" title=${item.display_name}>${item.display_name}</span>
            </div>
        `;
    }

    override render(): TemplateResult {
        const hasZone = this.zone !== null;
        const showPager = this._total > this.pageSize;
        return html`
            <div class="search">
                <div class="search-box">
                    <platform-icon name="search" size="16"></platform-icon>
                    <input
                        type="search"
                        placeholder=${this.t('zone_panel.search_placeholder')}
                        .value=${this._q}
                        ?disabled=${!hasZone}
                        @input=${this._onSearchInput}
                        aria-label=${this.t('zone_panel.search_placeholder')}
                    />
                </div>
            </div>
            <div class="count">
                ${this._loading
                    ? html`<platform-spinner size="14"></platform-spinner><span>${this.t('zone_panel.loading')}</span>`
                    : hasZone
                      ? html`<b>${this._total}</b><span>${this.t('zone_panel.count_suffix')}</span>`
                      : html`<span>${this.t('zone_panel.draw_first')}</span>`}
                ${this._failed ? html`<span class="err">${this.t('zone_panel.error')}</span>` : nothing}
            </div>
            <div class="list" role="list">
                ${!hasZone
                    ? html`<div class="empty">
                          <platform-icon name="globe" size="28"></platform-icon>
                          <span>${this.t('zone_panel.empty_no_zone')}</span>
                      </div>`
                    : this._total === 0 && !this._loading
                      ? html`<div class="empty">
                            <platform-icon name="search" size="28"></platform-icon>
                            <span>${this.t('zone_panel.empty_no_hits')}</span>
                        </div>`
                      : this._items.map((item) => this._renderRow(item))}
            </div>
            ${showPager
                ? html`<div class="pager">
                      <button ?disabled=${this._page === 0} @click=${() => this._setPage(this._page - 1)}>
                          ← ${this.t('zone_panel.prev')}
                      </button>
                      <span>${this._page + 1} / ${this._pageCount}</span>
                      <button
                          ?disabled=${this._page >= this._pageCount - 1}
                          @click=${() => this._setPage(this._page + 1)}
                      >
                          ${this.t('zone_panel.next')} →
                      </button>
                  </div>`
                : nothing}
        `;
    }
}

customElements.define('platform-zone-address-panel', PlatformZoneAddressPanel);

declare global {
    interface HTMLElementTagNameMap {
        'platform-zone-address-panel': PlatformZoneAddressPanel;
    }
}
