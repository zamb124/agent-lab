/**
 * GeoOverviewPage — карта канонических слоёв Geo.
 *
 * `<platform-map>` рисует фичи из `geo/layers/features` по рамке и зуму,
 * контрол слоёв переключает видимость через slice `geo/map`.
 * Строка статуса — поколение импорта (`geo/import/status`).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type { geoImportStatusOp } from '@platform/lib/events/resources/geo-coverage.resource.js';
import '@platform/lib/components/platform-map.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';

export class GeoOverviewPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _statusCtl: OpControllerOf<typeof geoImportStatusOp>;

    constructor() {
        super();
        this._statusCtl = this.useOp('geo/import_status');
    }

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .map-wrap {
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
            }
            platform-map { flex: 1; min-height: 0; }
            .map-status {
                position: absolute;
                top: 12px;
                left: 12px;
                z-index: 6;
                display: flex;
                gap: var(--space-4);
                flex-wrap: wrap;
                padding: var(--space-2) var(--space-4);
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-md, 10px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                color: var(--text-tertiary);
                font-size: var(--text-xs, 12px);
                pointer-events: none;
            }
            .map-status strong { color: var(--text-primary); font-weight: var(--font-semibold); }
        `,
    ];

    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._statusCtl.lastResult && !this._statusCtl.busy) {
            void this._statusCtl.run({});
        }
    }

    override render() {
        const status = this._statusCtl.lastResult;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                dense
                title=${this.t('overview.header_title')}
            ></page-header>
            <div class="map-wrap">
            <platform-map
                .config=${{
                    interactive: true,
                    controls: {
                        zoom: true,
                        layers: true,
                        locate: true,
                        search: true,
                        ruler: true,
                        fit: true,
                        fullscreen: true,
                        scale: true,
                    },
                    layers: { fetch: true },
                    featureCards: { hover: true, click: true },
                    search: { limit: 7 },
                    contextMenu: true,
                    statusBar: true,
                }}
            ></platform-map>
            <div class="map-status">
                <span>${this.t('overview.generation')} <strong>${status?.current_generation ?? '—'}</strong></span>
                <span>${this.t('overview.status')} <strong>${status?.status ?? '—'}</strong></span>
                <span>${this.t('overview.rows')}
                    <strong>${status ? (status.rows_addresses ?? 0) + (status.rows_edges ?? 0) : '—'}</strong>
                </span>
            </div>
            </div>
        `;
    }
}

customElements.define('geo-overview-page', GeoOverviewPage);
