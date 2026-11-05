/**
 * ShopZoneMap — превью зоны доставки на векторной карте (MapLibre).
 *
 * Только просмотр: полигон, центровка по магазину. Редактирование —
 * полноэкранная модалка `shop.zone_editor` (terra-draw) по кнопке «Изменить»:
 * openModal с onApply → GeoJSON Polygon в событии `zone-changed`
 * (`detail.zone`, пустой объект — зоны нет), родитель сохраняет его в
 * `shop.delivery_zone` обычным `shop/shop_update`.
 *
 * Свойства:
 *   zone      — GeoJSON Polygon или {} (ничего не нарисовано)
 *   address   — адрес магазина текстом: кнопка «Найти на карте» центрирует
 *               карту через публичный geocode endpoint.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { loadMapLibre, maplibreCssLink } from '@platform/lib/map/maplibre.js';
import type { MapLibreModule } from '@platform/lib/map/maplibre.js';
import { createBasemap } from '@platform/lib/map/basemap.js';
import type { PlatformMap } from '@platform/lib/map/basemap.js';

type MapLibreMarker = import('maplibre-gl').Marker;

type LngLatRing = [number, number][];

interface ZoneChangedDetail {
    zone: Record<string, unknown>;
}

export class ShopZoneMap extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        zone: { type: Object, attribute: false },
        address: { type: String, attribute: false },
        shopId: { type: String, attribute: 'shop-id' },
        _locating: { state: true },
    };

    declare zone: Record<string, unknown> | null;
    declare address: string;
    declare shopId: string;
    declare _locating: boolean;

    private _maplibre: MapLibreModule | null = null;
    private _map: PlatformMap | null = null;
    private _marker: MapLibreMarker | null = null;
    private _ro: ResizeObserver | null = null;
    private _mapSized = false;

    constructor() {
        super();
        this.zone = null;
        this.address = '';
        this.shopId = '';
        this._locating = false;
    }

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; gap: var(--space-3); }
            .mapwrap {
                position: relative;
                height: 280px;
                border-radius: var(--radius-m, 12px);
                overflow: hidden;
                border: 1px solid color-mix(in srgb, var(--text-primary) 12%, transparent);
                background: var(--bg-secondary, #f2f0ec);
            }
            .map { position: absolute; inset: 0; }
            .open-editor {
                position: absolute;
                right: var(--space-3);
                bottom: var(--space-3);
                z-index: 500;
                border: none;
                border-radius: var(--radius-full, 999px);
                padding: var(--space-2) var(--space-4);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                background: color-mix(in srgb, var(--bg-primary, #fff) 94%, transparent);
                backdrop-filter: blur(12px);
                box-shadow: 0 6px 22px color-mix(in srgb, var(--text-primary) 18%, transparent);
                color: var(--accent);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
            }
            .open-editor:hover { background: var(--bg-primary, #fff); }
            .empty-badge {
                position: absolute;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                z-index: 500;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 92%, transparent);
                backdrop-filter: blur(12px);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                pointer-events: none;
            }
            .toolbar { display: flex; flex-wrap: wrap; gap: var(--space-2); }
        `,
    ];

    override firstUpdated(): void {
        void this._initMap();
    }

    override disconnectedCallback(): void {
        this._ro?.disconnect();
        this._ro = null;
        this._mapSized = false;
        this._marker?.remove();
        this._marker = null;
        this._map?.remove();
        this._map = null;
        super.disconnectedCallback();
    }

    protected override updated(changed: Map<string, unknown>): void {
        // zone может прийти после init карты (fetch настроек) — перерисовываем.
        if (changed.has('zone') && this._map) this._renderZone();
    }

    private async _initMap(): Promise<void> {
        this._maplibre = await loadMapLibre();
        const el = this.renderRoot.querySelector<HTMLElement>('.map');
        if (!el || this._map) return;
        const map = (this._map = await createBasemap(el, {
            center: [37.6184, 55.7512],
            zoom: 11,
            interactive: false,
        }));
        this._ro = new ResizeObserver(() => {
            if (!this._map || !el.offsetWidth || !el.offsetHeight) return;
            this._map.resize();
            if (!this._mapSized) {
                this._mapSized = true;
                this._fitZone(false);
            }
        });
        this._ro.observe(el);
        map.once('load', () => {
            map.addSource('zone', { type: 'geojson', data: this._zoneData() });
            map.addLayer({
                id: 'zone-fill',
                type: 'fill',
                source: 'zone',
                paint: { 'fill-color': '#f2542d', 'fill-opacity': 0.12 },
            });
            map.addLayer({
                id: 'zone-line',
                type: 'line',
                source: 'zone',
                paint: { 'line-color': '#f2542d', 'line-width': 2.5 },
            });
            this._renderZone();
        });
    }

    private _ring(): LngLatRing | null {
        const z = this.zone;
        if (!z || z['type'] !== 'Polygon') return null;
        const coords = z['coordinates'];
        if (!Array.isArray(coords) || !Array.isArray(coords[0]) || coords[0].length < 4) {
            return null;
        }
        const ring: LngLatRing = [];
        for (const pt of coords[0] as Array<unknown>) {
            if (Array.isArray(pt) && typeof pt[0] === 'number' && typeof pt[1] === 'number') {
                ring.push([pt[0], pt[1]]);
            } else {
                return null;
            }
        }
        return ring.length >= 4 ? ring : null;
    }

    private _zoneData() {
        const ring = this._ring();
        return {
            type: 'FeatureCollection' as const,
            features: ring
                ? [
                      {
                          type: 'Feature' as const,
                          geometry: { type: 'Polygon' as const, coordinates: [ring] },
                          properties: {},
                      },
                  ]
                : [],
        };
    }

    private _fitZone(animate = true): void {
        const map = this._map;
        const ring = this._ring();
        if (!map || !ring) return;
        const lngs = ring.map((c) => c[0]);
        const lats = ring.map((c) => c[1]);
        map.fitBounds(
            [
                [Math.min(...lngs), Math.min(...lats)],
                [Math.max(...lngs), Math.max(...lats)],
            ],
            { padding: 24, animate },
        );
    }

    private _renderZone(): void {
        const map = this._map;
        if (!map || !map.isStyleLoaded()) return;
        const source = map.getSource('zone') as
            | { setData(d: unknown): void }
            | undefined;
        if (!source) return;
        source.setData(this._zoneData());
        if (this._ring()) this._fitZone();
    }

    private _emitZone(zone: Record<string, unknown>): void {
        this.dispatchEvent(
            new CustomEvent<ZoneChangedDetail>('zone-changed', {
                detail: { zone },
                bubbles: true,
                composed: true,
            }),
        );
    }

    private _openEditor(): void {
        this.openModal('shop.zone_editor', {
            zone: this.zone ?? {},
            address: this.address,
            shopId: this.shopId,
            onApply: (zone: Record<string, unknown>) => {
                this.zone = zone;
                this._renderZone();
                this._emitZone(zone);
            },
        });
    }

    private async _locate(): Promise<void> {
        const q = this.address.trim();
        if (!q || !this._map || !this._maplibre || !this.shopId) return;
        this._locating = true;
        try {
            const data = (await this.useOp('shop/shop_geocode').run({
                shop_id: this.shopId,
                address: q,
            })) as { lat: number; lng: number } | null;
            if (data) {
                this._map.jumpTo({ center: [data.lng, data.lat], zoom: 14 });
                this._marker?.remove();
                this._marker = new this._maplibre.Marker()
                    .setLngLat([data.lng, data.lat])
                    .addTo(this._map);
            }
        } finally {
            this._locating = false;
        }
    }

    protected override render(): TemplateResult {
        const hasZone = this._ring() !== null;
        return html`
            ${maplibreCssLink()}
            <div class="mapwrap">
                <div class="map"></div>
                ${!hasZone ? html`<div class="empty-badge">${this.t('settings.zone_empty_badge')}</div>` : nothing}
                <button type="button" class="open-editor" @click=${() => this._openEditor()}>
                    <platform-icon name="edit" size="14"></platform-icon>
                    ${hasZone ? this.t('settings.zone_edit') : this.t('settings.zone_set')}
                </button>
            </div>
            <div class="toolbar">
                ${this.address.trim()
                    ? html`
                        <platform-button size="sm" variant="secondary"
                            ?busy=${this._locating}
                            @click=${() => this._locate()}>
                            <platform-icon name="pin" size="14"></platform-icon>
                            ${this.t('settings.zone_locate')}
                        </platform-button>`
                    : nothing}
            </div>
        `;
    }
}

if (!customElements.get('shop-zone-map')) {
    customElements.define('shop-zone-map', ShopZoneMap);
}
