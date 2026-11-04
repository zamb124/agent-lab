/**
 * ShopZoneMap — редактор зоны доставки: полигон на карте (Leaflet + OSM).
 *
 * Директор рисует кольцо кликами: «Рисовать зону» → клики ставят вершины →
 * «Замкнуть». Результат — GeoJSON Polygon в событии `zone-changed`
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

type LeafletModule = typeof import('leaflet');
type LeafletMap = import('leaflet').Map;
type LeafletPolygon = import('leaflet').Polygon;
type LeafletPolyline = import('leaflet').Polyline;
type LeafletMarker = import('leaflet').Marker;
type LatLngTuple = [number, number];

interface ZoneChangedDetail {
    zone: Record<string, unknown>;
}

let _leafletPromise: Promise<LeafletModule> | null = null;

function loadLeaflet(): Promise<LeafletModule> {
    if (!_leafletPromise) {
        if (!document.getElementById('leaflet-css')) {
            const link = document.createElement('link');
            link.id = 'leaflet-css';
            link.rel = 'stylesheet';
            link.href = '/shop/ui/static/vendor/leaflet/leaflet.css';
            document.head.appendChild(link);
        }
        _leafletPromise = import('leaflet');
    }
    return _leafletPromise;
}

export class ShopZoneMap extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        zone: { type: Object, attribute: false },
        address: { type: String, attribute: false },
        shopId: { type: String, attribute: 'shop-id' },
        _drawing: { state: true },
        _locating: { state: true },
        _hint: { state: true },
    };

    declare zone: Record<string, unknown> | null;
    declare address: string;
    declare shopId: string;
    declare _drawing: boolean;
    declare _locating: boolean;
    declare _hint: string;

    private _L: LeafletModule | null = null;
    private _map: LeafletMap | null = null;
    private _polygon: LeafletPolygon | null = null;
    private _draftLine: LeafletPolyline | null = null;
    private _draftPoints: LatLngTuple[] = [];
    private _marker: LeafletMarker | null = null;

    constructor() {
        super();
        this.zone = null;
        this.address = '';
        this.shopId = '';
        this._drawing = false;
        this._locating = false;
        this._hint = '';
    }

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; gap: var(--space-3); }
            .map {
                height: 340px;
                border-radius: var(--radius-m, 12px);
                overflow: hidden;
                border: 1px solid color-mix(in srgb, var(--text-primary) 12%, transparent);
                background: var(--bg-secondary, #f2f0ec);
            }
            .map.drawing { cursor: crosshair; }
            .toolbar { display: flex; flex-wrap: wrap; gap: var(--space-2); }
            .hint { font-size: var(--text-sm); color: var(--text-tertiary); line-height: 1.45; }
        `,
    ];

    override firstUpdated(): void {
        void this._initMap();
    }

    override disconnectedCallback(): void {
        this._map?.remove();
        this._map = null;
        super.disconnectedCallback();
    }

    private async _initMap(): Promise<void> {
        const L = (this._L = await loadLeaflet());
        const el = this.renderRoot.querySelector<HTMLElement>('.map');
        if (!el || this._map) return;
        const map = (this._map = L.map(el, {
            center: [55.7512, 37.6184],
            zoom: 11,
            scrollWheelZoom: true,
        }));
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap',
            maxZoom: 19,
        }).addTo(map);
        map.on('click', (ev: { latlng: { lat: number; lng: number } }) => {
            if (this._drawing) this._addVertex(ev.latlng.lat, ev.latlng.lng);
        });
        this._renderZone();
    }

    private _ringLatLngs(): LatLngTuple[] | null {
        const z = this.zone;
        if (!z || z['type'] !== 'Polygon') return null;
        const coords = z['coordinates'];
        if (!Array.isArray(coords) || !Array.isArray(coords[0]) || coords[0].length < 4) {
            return null;
        }
        const ring: LatLngTuple[] = [];
        for (const pt of coords[0] as Array<unknown>) {
            if (Array.isArray(pt) && typeof pt[0] === 'number' && typeof pt[1] === 'number') {
                ring.push([pt[1], pt[0]]); // GeoJSON [lng,lat] → Leaflet [lat,lng]
            } else {
                return null;
            }
        }
        return ring.length >= 4 ? ring : null;
    }

    private _renderZone(): void {
        if (!this._map || !this._L) return;
        const ring = this._ringLatLngs();
        if (ring) {
            if (this._polygon) this._polygon.remove();
            this._polygon = this._L.polygon(ring, {
                color: '#f2542d',
                weight: 2.5,
                fillOpacity: 0.12,
            }).addTo(this._map);
            this._map.fitBounds(this._polygon.getBounds(), { padding: [24, 24] });
        }
    }

    private _emitZone(): void {
        this.dispatchEvent(
            new CustomEvent<ZoneChangedDetail>('zone-changed', {
                detail: { zone: this.zone ?? {} },
                bubbles: true,
                composed: true,
            }),
        );
    }

    private _addVertex(lat: number, lng: number): void {
        if (!this._map || !this._L) return;
        this._draftPoints.push([lat, lng]);
        if (this._draftLine) this._draftLine.remove();
        this._draftLine = this._L.polyline(this._draftPoints, {
            color: '#f2542d',
            weight: 2.5,
            dashArray: '6 6',
        }).addTo(this._map);
        this._hint = this._draftPoints.length < 3
            ? `Ещё ${3 - this._draftPoints.length} точки минимум`
            : '«Замкнуть» — готово, или добавьте ещё точек';
    }

    private _startDraw(): void {
        this._drawing = true;
        this._draftPoints = [];
        this._hint = 'Кликайте по карте — ставьте вершины зоны';
        this._clearZone(false);
    }

    private _finishDraw(): void {
        if (this._draftPoints.length < 3 || !this._L) return;
        const first = this._draftPoints[0];
        if (!first) return;
        const closed = [...this._draftPoints, first];
        this.zone = {
            type: 'Polygon',
            coordinates: [closed.map(([lat, lng]) => [lng, lat])],
        };
        this._drawing = false;
        this._draftPoints = [];
        if (this._draftLine) {
            this._draftLine.remove();
            this._draftLine = null;
        }
        this._hint = '';
        this._renderZone();
        this._emitZone();
    }

    private _cancelDraw(): void {
        this._drawing = false;
        this._draftPoints = [];
        if (this._draftLine) {
            this._draftLine.remove();
            this._draftLine = null;
        }
        this._hint = '';
    }

    private _clearZone(emit = true): void {
        this.zone = {};
        if (this._polygon) {
            this._polygon.remove();
            this._polygon = null;
        }
        if (emit) this._emitZone();
    }

    private async _locate(): Promise<void> {
        const q = this.address.trim();
        if (!q || !this._map || !this._L || !this.shopId) return;
        this._locating = true;
        try {
            const data = (await this.useOp('shop/shop_geocode').run({
                shop_id: this.shopId,
                address: q,
            })) as { lat: number; lng: number } | null;
            if (data) {
                this._map.setView([data.lat, data.lng], 14);
                if (this._marker) this._marker.remove();
                this._marker = this._L.marker([data.lat, data.lng]).addTo(this._map);
            }
        } finally {
            this._locating = false;
        }
    }

    protected override render(): TemplateResult {
        const hasZone = this._ringLatLngs() !== null;
        return html`
            <div class="map ${this._drawing ? 'drawing' : ''}"></div>
            <div class="toolbar">
                ${this._drawing
                    ? html`
                        <platform-button size="sm" variant="primary"
                            ?disabled=${this._draftPoints.length < 3}
                            @click=${() => this._finishDraw()}>
                            Замкнуть зону
                        </platform-button>
                        <platform-button size="sm" variant="secondary"
                            @click=${() => this._cancelDraw()}>
                            Отмена
                        </platform-button>`
                    : html`
                        <platform-button size="sm" variant="secondary"
                            @click=${() => this._startDraw()}>
                            <platform-icon name="edit" size="14"></platform-icon>
                            ${hasZone ? 'Перерисовать зону' : 'Нарисовать зону'}
                        </platform-button>
                        ${hasZone
                            ? html`
                                <platform-button size="sm" variant="secondary"
                                    @click=${() => this._clearZone()}>
                                    Очистить
                                </platform-button>`
                            : nothing}
                        ${this.address.trim()
                            ? html`
                                <platform-button size="sm" variant="secondary"
                                    ?busy=${this._locating}
                                    @click=${() => this._locate()}>
                                    <platform-icon name="pin" size="14"></platform-icon>
                                    Найти магазин на карте
                                </platform-button>`
                            : nothing}`}
            </div>
            ${this._hint ? html`<div class="hint">${this._hint}</div>` : nothing}
        `;
    }
}

if (!customElements.get('shop-zone-map')) {
    customElements.define('shop-zone-map', ShopZoneMap);
}
