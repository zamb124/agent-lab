/**
 * GeoRouteLabPage — маршрутная лаборатория.
 *
 * Два клика по карте ставят from/to (маркеры A/B), режим — `<platform-field>`
 * select; `geo/route/calculate` рисует геометрию overlay'ем `<geo-map>` и
 * показывает метрики. Слои реестра работают и здесь — та же панель.
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type { geoRouteOp } from '@platform/lib/events/resources/geo-route.resource.js';
import { GeoMap } from '@platform/lib/components/geo-map.js';
import type { GeoJsonOverlay } from '@platform/lib/components/geo-map.js';
import '@platform/lib/components/geo-map.js';
import '@platform/lib/components/geo-layer-panel.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

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
        _overlay: { state: true },
    };

    declare _mode: Mode;
    declare _from: [number, number] | null;
    declare _to: [number, number] | null;
    declare _result: { distance_m: number; duration_s: number } | null;
    declare _overlay: GeoJsonOverlay | null;

    constructor() {
        super();
        this._routeCtl = this.useOp('geo/route');
        this._mode = 'car';
        this._from = null;
        this._to = null;
        this._result = null;
        this._overlay = null;
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
            geo-map { flex: 1; min-height: 0; }
        `,
    ];

    private _map(): GeoMap | null {
        const el = this.renderRoot.querySelector('geo-map');
        return el instanceof GeoMap ? el : null;
    }

    private async _calculate(): Promise<void> {
        if (!this._from || !this._to) return;
        const res = await this._routeCtl.run({
            from_point: { lat: this._from[0], lng: this._from[1] },
            to_point: { lat: this._to[0], lng: this._to[1] },
            mode: this._mode,
        });
        if (res === null) {
            this._result = null;
            this._overlay = null;
            this.toast('route_lab.failed', { type: 'error' });
            return;
        }
        this._result = { distance_m: res.distance_m, duration_s: res.duration_s };
        this._overlay = res.geometry
            ? ({ type: 'Feature', geometry: res.geometry } as GeoJsonOverlay)
            : null;
    }

    private _onMapClick(e: CustomEvent<{ lat: number; lng: number }>): void {
        const map = this._map();
        if (!map) return;
        const { lat, lng } = e.detail;
        if (!this._from || (this._from && this._to)) {
            this._from = [lat, lng];
            this._to = null;
            this._result = null;
            this._overlay = null;
            map.clearMarkers();
            map.addMarker(lat, lng, '#22c55e');
            return;
        }
        this._to = [lat, lng];
        map.addMarker(lat, lng, '#ef4444');
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
            <geo-map
                .overlay=${this._overlay}
                @geo-map-click=${(e: CustomEvent<{ lat: number; lng: number }>) => this._onMapClick(e)}
            >
                <geo-layer-panel slot="panel"></geo-layer-panel>
            </geo-map>
        `;
    }
}

customElements.define('geo-route-lab-page', GeoRouteLabPage);
