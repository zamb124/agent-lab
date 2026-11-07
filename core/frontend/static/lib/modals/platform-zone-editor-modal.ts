/**
 * PlatformZoneEditorModal — платформенный редактор полигональной зоны.
 *
 * Единственный редактор зон платформы (зона доставки shop, зоны geo,
 * будущие wiki/tracker/flows): openModal('platform.zone_editor', {...}).
 * Внутри — <platform-map> с draw='polygon' (TerraDraw), каноническими
 * слоями geo и боковой панелью адресов в зоне.
 *
 * Вход (props модалки):
 *   zone        GeoJSON Polygon | MultiPolygon | null — текущая зона
 *   address     строка для стартового позиционирования (geo suggest)
 *   center/zoom камера, если зоны и адреса нет
 *   maxPoints   лимит вершин полигона (default 256)
 *   addressesPanel  false — скрыть панель адресов в зоне
 *   onApply     (zone | null) => void — результат в родителя; сохранение
 *               не делает модалка, это решение вызывающей стороны.
 *               null — «зоны нет».
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-map.js';
import type { PlatformMapEl, PlatformMapConfig, LngLat } from '@platform/lib/components/platform-map.js';
import { ringAreaM2, ringPerimeterM, fmtArea, fmtKm } from '@platform/lib/map/geo-math.js';
import '../events/resources/geo-addresses.resource.js';
import type { geoAddressSuggestOp } from '../events/resources/geo-addresses.resource.js';
import type { Polygon, MultiPolygon } from 'geojson';

const ZONE_MAX_POINTS = 256;

type ZoneGeometry = Polygon | MultiPolygon;

function _zonePoints(zone: ZoneGeometry): number {
    const rings =
        zone.type === 'Polygon' ? zone.coordinates : zone.coordinates.flatMap((p) => p);
    return rings.reduce((n, ring) => n + ring.length, 0);
}

function _zoneCenter(zone: ZoneGeometry): LngLat | null {
    const ring =
        (zone.type === 'Polygon' ? zone.coordinates[0] : zone.coordinates[0]?.[0]) as
            | LngLat[]
            | undefined;
    if (!ring || ring.length === 0) return null;
    let lng = 0;
    let lat = 0;
    for (const [x, y] of ring) {
        lng += x;
        lat += y;
    }
    return [lng / ring.length, lat / ring.length];
}

export class PlatformZoneEditorModal extends PlatformModal {
    static modalKind = 'platform.zone_editor';
    static i18nNamespace = 'geo';

    declare zone: ZoneGeometry | null;
    declare address: string;
    declare center: LngLat | null;
    declare zoom: number | null;
    declare maxPoints: number;
    declare addressesPanel: boolean;
    declare onApply: ((zone: ZoneGeometry | null) => void) | null;

    declare _zone: ZoneGeometry | null;
    declare _valid: boolean;
    declare _drawing: boolean;
    declare _locating: boolean;
    declare _mapConfig: PlatformMapConfig;

    private _suggestOp: OpControllerOf<typeof geoAddressSuggestOp> | null = null;
    private _mapEl: PlatformMapEl | null = null;

    static override properties: PropertyDeclarations = {
        zone: { type: Object, attribute: false },
        address: { type: String, attribute: false },
        center: { type: Array, attribute: false },
        zoom: { type: Number, attribute: false },
        maxPoints: { type: Number, attribute: false },
        addressesPanel: { type: Boolean, attribute: false },
        onApply: { attribute: false },
        _zone: { state: true },
        _valid: { state: true },
        _drawing: { state: true },
        _locating: { state: true },
        _mapConfig: { state: true },
    };

    constructor() {
        super();
        this.zone = null;
        this.address = '';
        this.center = null;
        this.zoom = null;
        this.maxPoints = ZONE_MAX_POINTS;
        this.addressesPanel = true;
        this.onApply = null;
        this._zone = null;
        this._valid = true;
        this._drawing = false;
        this._locating = false;
        this._mapConfig = {};
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._suggestOp = this.useOp('geo/addresses_suggest');
        this._zone = this.zone;
        this._mapConfig = this._buildConfig();
    }

    private _buildConfig(): PlatformMapConfig {
        const center = this.center ?? (this._zone ? _zoneCenter(this._zone) : null) ?? undefined;
        return {
            interactive: true,
            ...(center !== undefined ? { center } : {}),
            zoom: this.zoom ?? (this._zone ? 13 : 11),
            controls: { zoom: true, layers: true, locate: true },
            layers: { fetch: true },
            featureCards: { hover: true, click: true },
            draw: { zone: this._zone },
            addressesPanel: this.addressesPanel ? { zone: this._zone } : false,
        };
    }

    private get _stats(): { areaM2: number; perimeterM: number } | null {
        const zone = this._zone;
        if (!zone) return null;
        const rings =
            zone.type === 'Polygon' ? [zone.coordinates[0] ?? []] : zone.coordinates.map((p) => p[0] ?? []);
        let areaM2 = 0;
        let perimeterM = 0;
        for (const ring of rings) {
            areaM2 += ringAreaM2(ring as LngLat[]);
            perimeterM += ringPerimeterM(ring as LngLat[]);
        }
        return { areaM2, perimeterM };
    }

    private _onDrawChange = (e: Event): void => {
        const d = (e as CustomEvent<{ zone: ZoneGeometry | null; valid: boolean }>).detail;
        this._zone = d.zone;
        this._valid = d.valid;
        this._drawing = this._mapEl?.getDraw()?.draw.getMode() === 'polygon';
        if (this.addressesPanel) {
            this._mapConfig = {
                ...this._mapConfig,
                addressesPanel: { zone: this._zone },
            };
        }
    };

    private _toggleDraw(): void {
        const draw = this._mapEl?.getDraw()?.draw;
        if (!draw) return;
        this._drawing = draw.getMode() !== 'polygon';
        draw.setMode(this._drawing ? 'polygon' : 'select');
    }

    private _clearZone(): void {
        const draw = this._mapEl?.getDraw()?.draw;
        if (!draw) return;
        draw.clear();
        this._zone = null;
        this._valid = true;
        if (this.addressesPanel) {
            this._mapConfig = { ...this._mapConfig, addressesPanel: { zone: null } };
        }
    }

    private _fitZone(): void {
        const zone = this._zone;
        const map = this._mapEl?.getMap();
        if (!zone || !map) return;
        const rings =
            (zone.type === 'Polygon' ? zone.coordinates : zone.coordinates.flatMap((p) => p)) as LngLat[][];
        let w = Infinity;
        let e = -Infinity;
        let s = Infinity;
        let n = -Infinity;
        for (const ring of rings) {
            for (const [lng, lat] of ring) {
                w = Math.min(w, lng);
                e = Math.max(e, lng);
                s = Math.min(s, lat);
                n = Math.max(n, lat);
            }
        }
        if (w <= e && s <= n) {
            map.fitBounds(
                [
                    [w, s],
                    [e, n],
                ],
                { padding: 60, duration: 500 },
            );
        }
    }

    private async _locate(): Promise<void> {
        const q = this.address.trim();
        const map = this._mapEl?.getMap();
        const op = this._suggestOp;
        if (!q || !map || !op || this._locating) return;
        this._locating = true;
        try {
            const res = await op.run({ q, limit: 1 });
            const hit = res?.items?.[0];
            if (hit) {
                map.easeTo({ center: [hit.lng, hit.lat], zoom: 15, duration: 700 });
            }
        } finally {
            this._locating = false;
        }
    }

    private _canApply(): boolean {
        if (this._drawing || !this._valid) return false;
        return this._zone === null || _zonePoints(this._zone) <= this.maxPoints;
    }

    private _apply(): void {
        if (!this._canApply()) return;
        this.onApply?.(this._zone);
        this.close();
    }

    override renderHeader() {
        return this.t('zone_editor.title');
    }

    override renderBody(): TemplateResult {
        const stats = this._stats;
        const points = this._zone ? _zonePoints(this._zone) : 0;
        return html`
            <div class="zwrap">
                <div class="zmap">
                    <platform-map
                        .config=${this._mapConfig}
                        @pm-ready=${(e: CustomEvent) => {
                            this._mapEl = e.target as PlatformMapEl;
                        }}
                        @pm-draw-change=${this._onDrawChange}
                    ></platform-map>
                </div>
                <div class="ztools">
                    <button
                        type="button"
                        class="ztool ${this._drawing ? 'on' : ''}"
                        title=${this.t('zone_editor.draw')}
                        @click=${this._toggleDraw}
                    >
                        <platform-icon name="edit" size="16"></platform-icon>
                        <span>${this._drawing ? this.t('zone_editor.draw_stop') : this.t('zone_editor.draw')}</span>
                    </button>
                    ${this._zone
                        ? html`
                              <button type="button" class="ztool" title=${this.t('zone_editor.fit')} @click=${this._fitZone}>
                                  <platform-icon name="maximize" size="16"></platform-icon>
                                  <span>${this.t('zone_editor.fit')}</span>
                              </button>
                              <button
                                  type="button"
                                  class="ztool danger"
                                  title=${this.t('zone_editor.clear')}
                                  @click=${this._clearZone}
                              >
                                  <platform-icon name="delete" size="16"></platform-icon>
                                  <span>${this.t('zone_editor.clear')}</span>
                              </button>`
                        : nothing}
                    ${this.address.trim()
                        ? html`
                              <button
                                  type="button"
                                  class="ztool"
                                  title=${this.t('zone_editor.locate')}
                                  ?disabled=${this._locating}
                                  @click=${this._locate}
                              >
                                  <platform-icon name="pin" size="16"></platform-icon>
                                  <span>${this.t('zone_editor.locate')}</span>
                              </button>`
                        : nothing}
                </div>
                ${stats
                    ? html`
                          <div class="zstats">
                              <span>${this.t('zone_editor.area')}: <b>${fmtArea(stats.areaM2)} ${this.t('zone_editor.km2')}</b></span>
                              <span>${this.t('zone_editor.perimeter')}: <b>${fmtKm(stats.perimeterM)} ${this.t('zone_editor.km')}</b></span>
                              <span>${this.t('zone_editor.points')}: <b>${points}</b></span>
                              ${!this._valid
                                  ? html`<span class="zwarn">${this.t('zone_editor.self_intersection')}</span>`
                                  : nothing}
                              ${points > this.maxPoints
                                  ? html`<span class="zwarn">${this.t('zone_editor.too_many_points')}</span>`
                                  : nothing}
                          </div>`
                    : nothing}
            </div>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <platform-button variant="secondary" @click=${() => this.close()}>
                ${this.t('zone_editor.cancel')}
            </platform-button>
            <platform-button variant="primary" ?disabled=${!this._canApply()} @click=${this._apply}>
                ${this.t('zone_editor.apply')}
            </platform-button>
        `;
    }

    static override styles = [
        PlatformModal.styles,
        css`
        .zwrap {
            position: relative;
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 0;
        }
        .zmap {
            flex: 1;
            min-height: 320px;
            border-radius: 12px;
            overflow: hidden;
        }
        .zmap platform-map {
            display: block;
            width: 100%;
            height: 100%;
        }
        .ztools {
            display: flex;
            gap: 8px;
            padding: 10px 0 0;
            flex-wrap: wrap;
        }
        .ztool {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 12px;
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 9px;
            background: var(--color-surface, #fff);
            font-size: 12.5px;
            cursor: pointer;
            color: var(--color-text, #0f172a);
        }
        .ztool.on {
            background: var(--color-accent-soft, #fff1ea);
            border-color: var(--color-accent, #f2542d);
        }
        .ztool.danger {
            color: var(--color-danger, #dc2626);
        }
        .ztool:disabled {
            opacity: 0.5;
            cursor: default;
        }
        .zstats {
            display: flex;
            gap: 16px;
            padding: 8px 2px 0;
            font-size: 12px;
            color: var(--color-text-muted, #64748b);
            flex-wrap: wrap;
        }
        .zstats b {
            color: var(--color-text, #0f172a);
        }
        .zwarn {
            color: var(--color-danger, #dc2626);
        }
        `,
    ];
}

customElements.define('platform-zone-editor-modal', PlatformZoneEditorModal);
registerModalKind(PlatformZoneEditorModal.modalKind, 'platform-zone-editor-modal');

declare global {
    interface HTMLElementTagNameMap {
        'platform-zone-editor-modal': PlatformZoneEditorModal;
    }
}
