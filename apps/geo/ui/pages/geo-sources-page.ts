/**
 * GeoSourcesPage — хаб импорта: статус конвейера, источники с запуском,
 * курсоры возобновления, очередь обогащения, статистика и регионы (CRUD).
 *
 * Таблицы напрямую из op-результатов; «Импорт» ставит тик источника
 * в очередь geo — тяжёлая работа только в воркере.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf, ResourceControllerOf } from '@platform/lib/base/use-resource.js';
import type {
    geoCursorResetOp,
    geoCursorsOp,
    geoEnrichOp,
    geoEnrichRetryOp,
    geoImportRunOp,
    geoImportStatusOp,
    geoRegionsResource,
    geoSourcesOp,
    geoStatsOp,
} from '@platform/lib/events/resources/geo-coverage.resource.js';
import type {
    GeoCursorItem,
    GeoRegionItem,
    GeoSourceItem,
    GeoStatsRow,
} from '@platform/lib/events/wire/geo.gen.js';
import '../modals/geo-region-editor-modal.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
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
    private _cursorsCtl: OpControllerOf<typeof geoCursorsOp>;
    private _enrichCtl: OpControllerOf<typeof geoEnrichOp>;
    private _cursorResetCtl: OpControllerOf<typeof geoCursorResetOp>;
    private _enrichRetryCtl: OpControllerOf<typeof geoEnrichRetryOp>;

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
            .card-actions { display: flex; align-items: center; gap: var(--space-2); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { text-align: left; padding: var(--space-2) var(--space-3); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); font-size: var(--text-xs); text-transform: uppercase; }
            td { color: var(--text-primary); border-top: 1px solid var(--glass-border-subtle); }
            .muted { color: var(--text-tertiary); }
            .num { font-variant-numeric: tabular-nums; }
            .err { color: var(--danger, #ef4444); font-size: var(--text-xs); }
            .pill {
                display: inline-block;
                padding: 1px var(--space-2);
                border-radius: var(--radius-full, 999px);
                font-size: var(--text-xs);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .pill.off { background: var(--glass-solid-medium); color: var(--text-tertiary); }
            .pill.warn { background: var(--warning-subtle, rgba(245, 158, 11, 0.15)); color: var(--warning, #f59e0b); }
            .pill.err { background: var(--danger-subtle, rgba(239, 68, 68, 0.15)); color: var(--danger, #ef4444); }
            .row-actions { display: flex; gap: var(--space-1); }
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                transition: background 0.15s ease, color 0.15s ease;
            }
            .icon-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .icon-btn.danger:hover { color: var(--danger, #ef4444); }
            .empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); font-size: var(--text-sm); }
            .stats-grid { display: grid; gap: var(--space-2); }
            .stats-row { display: flex; align-items: baseline; gap: var(--space-3); padding: var(--space-1) 0; border-top: 1px solid var(--glass-border-subtle); }
            .stats-src { min-width: 110px; font-weight: var(--font-medium); }
            .stats-items { color: var(--text-secondary); font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this._regionsCtl = this.useResource('geo/regions', { autoload: true });
        this._sourcesCtl = this.useOp('geo/sources');
        this._statsCtl = this.useOp('geo/stats');
        this._statusCtl = this.useOp('geo/import_status');
        this._runCtl = this.useOp('geo/import_run');
        this._cursorsCtl = this.useOp('geo/cursors');
        this._enrichCtl = this.useOp('geo/enrich');
        this._cursorResetCtl = this.useOp('geo/cursor_reset');
        this._enrichRetryCtl = this.useOp('geo/enrich_retry');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        for (const ctl of [this._statusCtl, this._sourcesCtl, this._statsCtl, this._cursorsCtl]) {
            if (!ctl.lastResult && !ctl.busy) void ctl.run({});
        }
        if (!this._enrichCtl.lastResult && !this._enrichCtl.busy) {
            void this._enrichCtl.run({ limit: 50 });
        }
    }

    private _runImport(source: string): void {
        void this._runCtl.run({ source });
    }

    private async _resetCursor(item: GeoCursorItem): Promise<void> {
        const res = await this._cursorResetCtl.run({
            source: item.source,
            region: item.region,
        });
        if (res !== null) void this._cursorsCtl.run({});
    }

    private async _retryEnrich(itemId: number): Promise<void> {
        const res = await this._enrichRetryCtl.run({ item_id: itemId });
        if (res !== null) void this._enrichCtl.run({ limit: 50 });
    }

    private _openRegionEditor(region: GeoRegionItem | null): void {
        this.openModal('geo.region_editor', {
            region,
            onApply: () => void this._regionsCtl.load(),
        });
    }

    private async _removeRegion(region: GeoRegionItem): Promise<void> {
        const confirmed = await platformConfirm(
            this.t('sources.confirm_remove_region', { name: region.name }),
            {
                title: this.t('sources.remove'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('sources.remove'),
                cancelText: this.t('cancel', {}, 'common'),
            },
        );
        if (!confirmed) return;
        this._regionsCtl.remove(region.name);
    }

    private _statusPill(status: string) {
        const cls = status === 'done' || status === 'idle' ? '' : status === 'failed' ? 'err' : 'warn';
        return html`<span class="pill ${cls}">${status || '—'}</span>`;
    }

    private _renderImportCard() {
        const status = this._statusCtl.lastResult;
        const stats = this._statsCtl.lastResult;
        return html`
            <div class="card">
                <div class="card-head">
                    <div class="card-title">${this.t('sources.import_title')}</div>
                    <div class="card-actions">
                        <platform-button size="sm" variant="ghost" ?busy=${this._runCtl.busy} @click=${() => this._runImport('tiles')}>
                            <platform-icon name="download" size="14"></platform-icon>
                            ${this.t('sources.tiles_run')}
                        </platform-button>
                        <platform-button size="sm" variant="secondary" ?busy=${this._runCtl.busy} @click=${() => this._runImport('osm')}>
                            <platform-icon name="refresh" size="14"></platform-icon>
                            ${this.t('sources.import_run')}
                        </platform-button>
                    </div>
                </div>
                <table>
                    <tbody>
                        <tr>
                            <td class="muted">${this.t('overview.generation')}</td>
                            <td><strong class="num">${status?.current_generation ?? '—'}</strong></td>
                        </tr>
                        <tr>
                            <td class="muted">${this.t('overview.status')}</td>
                            <td>${status ? this._statusPill(status.status) : '—'}${status?.source_name ? html` <span class="muted">${status.source_name}</span>` : ''}${status?.last_error ? html` <span class="err">${status.last_error}</span>` : ''}</td>
                        </tr>
                        <tr>
                            <td class="muted">${this.t('sources.totals')}</td>
                            <td class="num">${stats ? Object.entries(stats.totals).map(([k, v]) => `${k}: ${v}`).join(', ') : '—'}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;
    }

    private _renderSources(sources: GeoSourceItem[]) {
        return html`
            <div class="card">
                <div class="card-head"><div class="card-title">${this.t('sources.sources_title')}</div></div>
                <table>
                    <thead>
                        <tr>
                            <th>${this.t('sources.col_name')}</th>
                            <th>${this.t('sources.col_kind')}</th>
                            <th>${this.t('sources.col_license')}</th>
                            <th>${this.t('sources.col_enabled')}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sources.map((s) => html`
                            <tr>
                                <td><strong>${s.name}</strong> <span class="muted">${s.title}</span></td>
                                <td>${s.kind}</td>
                                <td class="muted">${s.license}</td>
                                <td><span class="pill ${s.enabled ? '' : 'off'}">${s.enabled ? this.t('sources.on') : this.t('sources.off')}</span></td>
                                <td>
                                    ${s.enabled && s.kind !== 'manual'
                                        ? html`<platform-button size="sm" variant="ghost" ?busy=${this._runCtl.busy} @click=${() => this._runImport(s.name)}>
                                              <platform-icon name="play" size="14"></platform-icon>
                                              ${this.t('sources.run_source')}
                                          </platform-button>`
                                        : ''}
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    private _renderCursors(items: GeoCursorItem[]) {
        return html`
            <div class="card">
                <div class="card-head"><div class="card-title">${this.t('sources.cursors_title')}</div></div>
                ${items.length === 0
                    ? html`<div class="empty">${this.t('sources.cursors_empty')}</div>`
                    : html`
                          <table>
                              <thead>
                                  <tr>
                                      <th>${this.t('sources.col_name')}</th>
                                      <th>${this.t('sources.col_region')}</th>
                                      <th>${this.t('sources.col_cursor')}</th>
                                      <th>${this.t('sources.col_status')}</th>
                                      <th>${this.t('sources.col_done')}</th>
                                      <th>${this.t('sources.col_updated')}</th>
                                      <th></th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${items.map((c) => html`
                                      <tr>
                                          <td><strong>${c.source}</strong></td>
                                          <td>${c.region}</td>
                                          <td class="muted num">${c.cursor}</td>
                                          <td>${this._statusPill(c.status)}</td>
                                          <td class="num">${c.rows_done}</td>
                                          <td class="muted">${c.updated_at?.slice(0, 16).replace('T', ' ') ?? '—'}</td>
                                          <td>
                                              <button
                                                  class="icon-btn"
                                                  title=${this.t('sources.cursor_reset')}
                                                  ?disabled=${this._cursorResetCtl.busy}
                                                  @click=${() => this._resetCursor(c)}
                                              ><platform-icon name="refresh" size="14"></platform-icon></button>
                                          </td>
                                      </tr>
                                      ${c.last_error
                                          ? html`<tr><td colspan="7" class="err">${c.last_error}</td></tr>`
                                          : ''}
                                  `)}
                              </tbody>
                          </table>
                      `}
            </div>
        `;
    }

    private _renderEnrich() {
        const res = this._enrichCtl.lastResult;
        const items = res?.items ?? [];
        return html`
            <div class="card">
                <div class="card-head">
                    <div class="card-title">${this.t('sources.enrich_title')}</div>
                    <div class="card-actions">
                        ${(res?.pending ?? 0) > 0
                            ? html`<span class="pill warn">${this.t('sources.enrich_pending', { count: res?.pending ?? 0 })}</span>`
                            : ''}
                        <platform-button size="sm" variant="ghost" ?busy=${this._runCtl.busy} @click=${() => this._runImport('enrich')}>
                            <platform-icon name="play" size="14"></platform-icon>
                            ${this.t('sources.enrich_run')}
                        </platform-button>
                    </div>
                </div>
                ${items.length === 0
                    ? html`<div class="empty">${this.t('sources.enrich_empty')}</div>`
                    : html`
                          <table>
                              <thead>
                                  <tr>
                                      <th>${this.t('sources.col_kind_label')}</th>
                                      <th>${this.t('sources.col_status')}</th>
                                      <th>${this.t('sources.col_attempts')}</th>
                                      <th>${this.t('sources.col_created')}</th>
                                      <th></th>
                                  </tr>
                              </thead>
                              <tbody>
                                  ${items.map((item) => html`
                                      <tr>
                                          <td><strong>${item.kind}</strong></td>
                                          <td>${this._statusPill(item.status)}</td>
                                          <td class="num">${item.attempts}</td>
                                          <td class="muted">${item.created_at.slice(0, 16).replace('T', ' ')}</td>
                                          <td>
                                              ${item.status === 'failed'
                                                  ? html`<button
                                                        class="icon-btn"
                                                        title=${this.t('sources.enrich_retry')}
                                                        ?disabled=${this._enrichRetryCtl.busy}
                                                        @click=${() => this._retryEnrich(item.id)}
                                                    ><platform-icon name="refresh" size="14"></platform-icon></button>`
                                                  : ''}
                                          </td>
                                      </tr>
                                      ${item.last_error
                                          ? html`<tr><td colspan="5" class="err">${item.last_error}</td></tr>`
                                          : ''}
                                  `)}
                              </tbody>
                          </table>
                      `}
            </div>
        `;
    }

    private _renderStats(rows: GeoStatsRow[]) {
        const bySource = new Map<string, GeoStatsRow[]>();
        for (const row of rows) {
            const list = bySource.get(row.source) ?? [];
            list.push(row);
            bySource.set(row.source, list);
        }
        return html`
            <div class="card">
                <div class="card-head"><div class="card-title">${this.t('sources.stats_title')}</div></div>
                ${bySource.size === 0
                    ? html`<div class="empty">${this.t('sources.stats_empty')}</div>`
                    : html`<div class="stats-grid">
                          ${[...bySource.entries()].map(([source, items]) => html`
                              <div class="stats-row">
                                  <span class="stats-src">${source}</span>
                                  <span class="stats-items num">${items.map((r) => `${r.region}/${r.entity}: ${r.rows}`).join(' · ')}</span>
                              </div>
                          `)}
                      </div>`}
            </div>
        `;
    }

    private _renderRegions(items: readonly GeoRegionItem[]) {
        return html`
            <div class="card">
                <div class="card-head">
                    <div class="card-title">${this.t('sources.regions_title')}</div>
                    <platform-button size="sm" variant="secondary" @click=${() => this._openRegionEditor(null)}>
                        <platform-icon name="plus" size="14"></platform-icon>
                        ${this.t('sources.add_region')}
                    </platform-button>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>${this.t('sources.col_name')}</th>
                            <th>${this.t('sources.col_kind')}</th>
                            <th>${this.t('sources.col_rows')}</th>
                            <th>${this.t('sources.col_imported')}</th>
                            <th>${this.t('sources.col_enabled')}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map((item) => html`
                            <tr>
                                <td><strong>${item.name}</strong> <span class="muted">${item.title}</span></td>
                                <td>${this.t(`sources.kind_${item.kind}`)}</td>
                                <td class="num">${(item.addresses ?? 0) + (item.edges ?? 0)}</td>
                                <td class="muted">${item.last_imported_at?.slice(0, 10) ?? '—'}</td>
                                <td><span class="pill ${item.enabled ? '' : 'off'}">${item.enabled ? this.t('sources.on') : this.t('sources.off')}</span></td>
                                <td>
                                    <div class="row-actions">
                                        <button class="icon-btn" title=${this.t('sources.edit')} @click=${() => this._openRegionEditor(item)}>
                                            <platform-icon name="edit" size="14"></platform-icon>
                                        </button>
                                        <button class="icon-btn danger" title=${this.t('sources.remove')} @click=${() => this._removeRegion(item)}>
                                            <platform-icon name="trash" size="14"></platform-icon>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        `;
    }

    override render() {
        const stats = this._statsCtl.lastResult;
        const sources = this._sourcesCtl.lastResult?.items ?? [];
        const cursors = this._cursorsCtl.lastResult?.items ?? [];
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                dense
                title=${this.t('sources.header_title')}
            ></page-header>
            <div class="grid">
                ${this._renderImportCard()}
                ${this._renderSources(sources)}
                ${this._renderCursors(cursors)}
                ${this._renderEnrich()}
                ${this._renderStats(stats?.rows ?? [])}
                ${this._renderRegions(this._regionsCtl.items)}
            </div>
        `;
    }
}

customElements.define('geo-sources-page', GeoSourcesPage);
