/**
 * GeoRouteLabPage — маршрутная лаборатория.
 *
 * Два клика по карте ставят from/to (маркеры A/B), режим — кнопки;
 * `geo/route/calculate` рисует геометрию overlay'ем `<platform-map>` и
 * показывает метрики. Слои реестра и контролы — встроенные.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type { geoRouteOp } from '@platform/lib/events/resources/geo-route.resource.js';
import '@platform/lib/components/platform-map.js';
import type { PlatformMapConfig, LngLat } from '@platform/lib/components/platform-map.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import type { Feature, LineString } from 'geojson';

const MODES = ['car', 'foot', 'bike', 'scooter'] as const;
type Mode = (typeof MODES)[number];

export class GeoRouteLabPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _routeCtl: OpControllerOf<typeof geoRouteOp>;

    static override properties = {
        _mode: { state: true },
        _from: { state: true },
        _to: { state: true },
        _result: { state: true },
        _routeGeometry: { state: true },
    };

    declare _mode: Mode;
    declare _from: LngLat | null;
    declare _to: LngLat | null;
    declare _result: { distance_m: number; duration_s: number } | null;
    declare _routeGeometry: LineString | null;

    constructor() {
        super();
        this._routeCtl = this.useOp('geo/route');
        this._mode = 'car';
        this._from = null;
        this._to = null;
        this._result = null;
        this._routeGeometry = null;
    }

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                flex-wrap: wrap;
                padding: var(--space-2) 0 var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .modes { display: flex; gap: var(--space-1); }
            .mode-btn {
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                border-radius: var(--radius-full, 999px);
                padding: var(--space-1) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .mode-btn.active {
                border-color: var(--accent);
                color: var(--accent);
                background: var(--accent-subtle);
            }
            .metrics {
                display: flex;
                gap: var(--space-4);
                padding: var(--space-2) 0 var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            .metrics strong { color: var(--text-primary); font-weight: var(--font-semibold); }
            platform-map { flex: 1; min-height: 0; }
        `,
    ];

    private get _mapConfig(): PlatformMapConfig {
        const markers: NonNullable<PlatformMapConfig['markers']> = [];
        if (this._from) markers.push({ key: 'from', lngLat: this._from, color: '#22c55e', title: 'A' });
        if (this._to) markers.push({ key: 'to', lngLat: this._to, color: '#ef4444', title: 'B' });
        const overlays: NonNullable<PlatformMapConfig['overlays']> = [];
        if (this._routeGeometry) {
            const feature: Feature<LineString> = {
                type: 'Feature',
                geometry: this._routeGeometry,
                properties: {},
            };
            overlays.push({ name: 'route', data: feature, color: '#155dfc', width: 5 });
        }
        return {
            interactive: true,
            controls: { zoom: true, layers: true, locate: true },
            layers: { fetch: true },
            featureCards: { hover: true, click: true },
            markers,
            overlays,
        };
    }

    private async _calculate(): Promise<void> {
        if (!this._from || !this._to) return;
        const res = await this._routeCtl.run({
            from_point: { lat: this._from[1], lng: this._from[0] },
            to_point: { lat: this._to[1], lng: this._to[0] },
            mode: this._mode,
        });
        if (res === null) {
            this._result = null;
            this._routeGeometry = null;
            this.toast('route_lab.failed', { type: 'error' });
            return;
        }
        this._result = { distance_m: res.distance_m, duration_s: res.duration_s };
        this._routeGeometry = (res.geometry as LineString | null) ?? null;
    }

    private _onMapClick(e: CustomEvent<{ lngLat: LngLat }>): void {
        const lngLat = e.detail.lngLat;
        if (!this._from || (this._from && this._to)) {
            this._from = lngLat;
            this._to = null;
            this._result = null;
            this._routeGeometry = null;
            return;
        }
        this._to = lngLat;
        void this._calculate();
    }

    private _setMode(mode: Mode): void {
        this._mode = mode;
        if (this._from && this._to) void this._calculate();
    }

    override render() {
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('route_lab.header_title')}
                subtitle=${this.t('route_lab.header_subtitle')}
            ></page-header>
            <div class="toolbar">
                <span>${this.t('route_lab.modes')}</span>
                <span class="modes">
                    ${MODES.map((mode) => html`
                        <button
                            class="mode-btn ${this._mode === mode ? 'active' : ''}"
                            @click=${() => this._setMode(mode)}
                        >${this.t(`route_lab.mode_${mode}`)}</button>
                    `)}
                </span>
                <span class="hint">${this.t('route_lab.click_hint')}</span>
            </div>
            ${this._result
                ? html`
                    <div class="metrics">
                        <span>${this.t('route_lab.distance')} <strong>${(this._result.distance_m / 1000).toFixed(2)} ${this.t('route_lab.km')}</strong></span>
                        <span>${this.t('route_lab.duration')} <strong>${Math.round(this._result.duration_s / 60)} ${this.t('route_lab.min')}</strong></span>
                    </div>
                `
                : nothing}
            <platform-map
                .config=${this._mapConfig}
                @pm-click=${(e: CustomEvent<{ lngLat: LngLat }>) => this._onMapClick(e)}
            ></platform-map>
        `;
    }
}

customElements.define('geo-route-lab-page', GeoRouteLabPage);
