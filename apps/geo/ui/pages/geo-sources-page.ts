/**
 * GeoSourcesPage — реестр покрытия: регионы, источники, статистика, курсоры.
 *
 * Таблицы напрямую из op-результатов; «Импорт» ставит `GEO_OSM_SYNC_TICK`
 * в очередь geo — тяжёлая работа только в воркере.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf, ResourceControllerOf } from '@platform/lib/base/use-resource.js';
import type {
    geoImportRunOp,
    geoImportStatusOp,
    geoRegionsResource,
    geoSourcesOp,
    geoStatsOp,
} from '@platform/lib/events/resources/geo-coverage.resource.js';
import type { GeoSourceItem } from '@platform/lib/events/wire/geo.gen.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class GeoSourcesPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _regionsCtl: ResourceControllerOf<typeof geoRegionsResource>;
    private _sourcesCtl: OpControllerOf<typeof geoSourcesOp>;
    private _statsCtl: OpControllerOf<typeof geoStatsOp>;
    private _statusCtl: OpControllerOf<typeof geoImportStatusOp>;
    private _runCtl: OpControllerOf<typeof geoImportRunOp>;

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .grid { display: grid; gap: var(--space-4); padding-bottom: var(--space-4); }
            .card {
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .card-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-3);
            }
            .card-title { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { text-align: left; padding: var(--space-2) var(--space-3); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); font-size: var(--text-xs); text-transform: uppercase; }
            td { color: var(--text-primary); border-top: 1px solid var(--glass-border-subtle); }
            .muted { color: var(--text-tertiary); }
            .pill {
                display: inline-block;
                padding: 1px var(--space-2);
                border-radius: var(--radius-full, 999px);
                font-size: var(--text-xs);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .pill.off { background: var(--glass-solid-medium); color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this._regionsCtl = this.useResource('geo/regions', { autoload: true });
        this._sourcesCtl = this.useOp('geo/sources');
        this._statsCtl = this.useOp('geo/stats');
        this._statusCtl = this.useOp('geo/import_status');
        this._runCtl = this.useOp('geo/import_run');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._statusCtl.lastResult && !this._statusCtl.busy) {
            void this._statusCtl.run({});
        }
        if (!this._sourcesCtl.lastResult && !this._sourcesCtl.busy) {
            void this._sourcesCtl.run({});
        }
        if (!this._statsCtl.lastResult && !this._statsCtl.busy) {
            void this._statsCtl.run({});
        }
    }

    private _runImport(): void {
        void this._runCtl.run({});
    }

    private _renderRegions() {
        const items = this._regionsCtl.items;
        return html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('sources.col_name')}</th>
                        <th>${this.t('sources.col_kind')}</th>
                        <th>${this.t('sources.col_rows')}</th>
                        <th>${this.t('sources.col_imported')}</th>
                        <th>${this.t('sources.col_enabled')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((item) => html`
                        <tr>
                            <td><strong>${item.name}</strong> <span class="muted">${item.title}</span></td>
                            <td>${this.t(`sources.kind_${item.kind}`)}</td>
                            <td>${(item.addresses ?? 0) + (item.edges ?? 0)}</td>
                            <td class="muted">${item.last_imported_at?.slice(0, 10) ?? '—'}</td>
                            <td><span class="pill ${item.enabled ? '' : 'off'}">${item.enabled ? this.t('sources.on') : this.t('sources.off')}</span></td>
                        </tr>
                    `)}
                </tbody>
            </table>
        `;
    }

    override render() {
        const status = this._statusCtl.lastResult;
        const stats = this._statsCtl.lastResult;
        const sources = this._sourcesCtl.lastResult?.items ?? [];
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('sources.header_title')}
                subtitle=${this.t('sources.header_subtitle')}
            ></page-header>
            <div class="grid">
                <div class="card">
                    <div class="card-head">
                        <div class="card-title">${this.t('sources.import_title')}</div>
                        <platform-button size="sm" variant="secondary" ?busy=${this._runCtl.busy} @click=${() => this._runImport()}>
                            <platform-icon name="refresh" size="14"></platform-icon>
                            ${this.t('sources.import_run')}
                        </platform-button>
                    </div>
                    <table>
                        <tbody>
                            <tr>
                                <td class="muted">${this.t('overview.generation')}</td>
                                <td><strong>${status?.current_generation ?? '—'}</strong></td>
                            </tr>
                            <tr>
                                <td class="muted">${this.t('overview.status')}</td>
                                <td>${status?.status ?? '—'}${status?.last_error ? html` <span class="muted">— ${status.last_error}</span>` : ''}</td>
                            </tr>
                            <tr>
                                <td class="muted">${this.t('sources.totals')}</td>
                                <td>${stats ? Object.entries(stats.totals).map(([k, v]) => `${k}: ${v}`).join(', ') : '—'}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-head"><div class="card-title">${this.t('sources.regions_title')}</div></div>
                    ${this._renderRegions()}
                </div>

                <div class="card">
                    <div class="card-head"><div class="card-title">${this.t('sources.sources_title')}</div></div>
                    <table>
                        <thead>
                            <tr>
                                <th>${this.t('sources.col_name')}</th>
                                <th>${this.t('sources.col_kind')}</th>
                                <th>${this.t('sources.col_license')}</th>
                                <th>${this.t('sources.col_enabled')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sources.map((s: GeoSourceItem) => html`
                                <tr>
                                    <td><strong>${s.name}</strong> <span class="muted">${s.title}</span></td>
                                    <td>${s.kind}</td>
                                    <td class="muted">${s.license}</td>
                                    <td><span class="pill ${s.enabled ? '' : 'off'}">${s.enabled ? this.t('sources.on') : this.t('sources.off')}</span></td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

customElements.define('geo-sources-page', GeoSourcesPage);
