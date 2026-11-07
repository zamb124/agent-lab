/**
 * GeoAddressesPage — админ-справочник адресов.
 *
 * Вкладка «Справочник»: поиск через `geo/addresses/suggest`, таблица,
 * действия «Править» (geo.address_editor) и «Скрыть» (addresses/remove).
 * Вкладка «Аудит»: журнал оверлеев `geo/overrides`, откат правки адреса —
 * `geo/addresses/override_revert`. Мутации — только у company_admin
 * (бэкенд проверяет scope; UI лишь показывает кнопки).
 */

import { html, css } from 'lit';
import type { PropertyDeclarations } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type {
    geoAddressRevertOp,
    geoAddressRemoveOp,
    geoFeatureUnsuppressOp,
    geoEdgeOpenOp,
    geoOverridesOp,
} from '@platform/lib/events/resources/geo-admin.resource.js';
import type { geoAddressSuggestOp } from '@platform/lib/events/resources/geo-addresses.resource.js';
import type {
    GeoAddressHit,
    GeoOverrideItem,
} from '@platform/lib/events/wire/geo.gen.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/events/resources/geo-admin.resource.js';
import '@platform/lib/events/resources/geo-addresses.resource.js';
import '../modals/geo-address-editor-modal.js';

type Tab = 'directory' | 'audit';

export class GeoAddressesPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _suggestCtl: OpControllerOf<typeof geoAddressSuggestOp>;
    private _overridesCtl: OpControllerOf<typeof geoOverridesOp>;
    private _removeCtl: OpControllerOf<typeof geoAddressRemoveOp>;
    private _revertCtl: OpControllerOf<typeof geoAddressRevertOp>;
    private _unsuppressCtl: OpControllerOf<typeof geoFeatureUnsuppressOp>;
    private _edgeOpenCtl: OpControllerOf<typeof geoEdgeOpenOp>;

    declare _q: string;
    declare _tab: Tab;
    declare _items: GeoAddressHit[];
    private _searchTimer: number | null = null;

    static override properties: PropertyDeclarations = {
        _q: { state: true },
        _tab: { state: true },
        _items: { state: true },
    };

    constructor() {
        super();
        this._suggestCtl = this.useOp('geo/addresses_suggest');
        this._overridesCtl = this.useOp('geo/overrides');
        this._removeCtl = this.useOp('geo/addresses_remove');
        this._revertCtl = this.useOp('geo/addresses_revert');
        this._unsuppressCtl = this.useOp('geo/features_unsuppress');
        this._edgeOpenCtl = this.useOp('geo/edges_open');
        this._q = '';
        this._tab = 'directory';
        this._items = [];
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._searchTimer !== null) {
            window.clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
    }

    private _onSearchInput(value: string): void {
        this._q = value;
        if (this._searchTimer !== null) window.clearTimeout(this._searchTimer);
        const q = value.trim();
        if (q.length < 3) {
            this._items = [];
            return;
        }
        this._searchTimer = window.setTimeout(() => {
            void this._search(q);
        }, 400);
    }

    private async _search(q: string): Promise<void> {
        const res = await this._suggestCtl.run({ q, limit: 20 });
        this._items = res?.items ?? [];
    }

    private _openEditor(address: GeoAddressHit | null): void {
        this.openModal('geo.address_editor', {
            address,
            onApply: () => {
                if (this._q.trim().length >= 3) void this._search(this._q.trim());
            },
        });
    }

    private async _removeAddress(item: GeoAddressHit): Promise<void> {
        await this._removeCtl.run({
            osm_type: item.osm_type,
            osm_id: item.osm_id,
            reason: this.t('addresses.hide_reason'),
        });
        this._items = this._items.filter(
            (a) => !(a.osm_type === item.osm_type && a.osm_id === item.osm_id),
        );
    }

    private _switchTab(tab: Tab): void {
        this._tab = tab;
        if (tab === 'audit' && !this._overridesCtl.lastResult) {
            void this._overridesCtl.run({ limit: 100 });
        }
    }

    private async _revert(item: GeoOverrideItem): Promise<void> {
        if (item.entity === 'address') {
            await this._revertCtl.run({ osm_type: item.osm_type, osm_id: item.osm_id });
        } else if (item.kind === 'edge_mask') {
            await this._edgeOpenCtl.run({ osm_way_id: item.osm_id });
        } else {
            await this._unsuppressCtl.run({ entity: item.entity, osm_id: item.osm_id });
        }
        void this._overridesCtl.run({ limit: 100 });
    }

    private _renderDirectory() {
        const busy = this._suggestCtl.busy;
        return html`
            <div class="toolbar">
                <div class="search-box">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('addresses.search_label')}
                        placeholder=${this.t('addresses.search_placeholder')}
                        .value=${this._q}
                        @change=${(e: CustomEvent) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('addresses: search expects detail.value string');
                            }
                            this._onSearchInput(e.detail.value);
                        }}
                    ></platform-field>
                </div>
                <platform-button
                    size="sm"
                    variant="primary"
                    @click=${() => this._openEditor(null)}
                >
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this.t('addresses.add')}
                </platform-button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>${this.t('addresses.col_address')}</th>
                        <th>${this.t('addresses.col_source')}</th>
                        <th>${this.t('addresses.col_coords')}</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${this._items.length === 0
                        ? html`<tr><td colspan="4" class="muted">
                              ${busy
                                  ? this.t('addresses.searching')
                                  : this._q.trim().length >= 3
                                    ? this.t('addresses.no_results')
                                    : this.t('addresses.empty')}
                          </td></tr>`
                        : this._items.map(
                              (a) => html`
                                  <tr>
                                      <td>
                                          <strong>${a.display_name}</strong>
                                          <div class="muted">
                                              ${[a.city, a.street, a.housenumber, a.postcode]
                                                  .filter(Boolean)
                                                  .join(', ')}
                                          </div>
                                      </td>
                                      <td><span class="pill ${a.osm_type === 'manual' ? 'manual' : ''}">${a.osm_type}</span></td>
                                      <td class="muted">${a.lat.toFixed(5)}, ${a.lng.toFixed(5)}</td>
                                      <td class="actions">
                                          <platform-button
                                              size="sm"
                                              variant="ghost"
                                              title=${this.t('addresses.edit')}
                                              @click=${() => this._openEditor(a)}
                                          >
                                              <platform-icon name="edit" size="14"></platform-icon>
                                          </platform-button>
                                          <platform-button
                                              size="sm"
                                              variant="ghost"
                                              title=${this.t('addresses.hide')}
                                              ?busy=${this._removeCtl.busy}
                                              @click=${() => this._removeAddress(a)}
                                          >
                                              <platform-icon name="trash" size="14"></platform-icon>
                                          </platform-button>
                                      </td>
                                  </tr>
                              `,
                          )}
                </tbody>
            </table>
        `;
    }

    private _renderAudit() {
        const items = this._overridesCtl.lastResult?.items ?? [];
        return html`
            <table>
                <thead>
                    <tr>
                        <th>${this.t('audit.col_kind')}</th>
                        <th>${this.t('audit.col_object')}</th>
                        <th>${this.t('audit.col_reason')}</th>
                        <th>${this.t('audit.col_actor')}</th>
                        <th>${this.t('audit.col_when')}</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${items.length === 0
                        ? html`<tr><td colspan="6" class="muted">${this.t('audit.empty')}</td></tr>`
                        : items.map(
                              (o) => html`
                                  <tr>
                                      <td>
                                          <span class="pill ${o.suppressed ? 'danger' : ''}">
                                              ${this.t(`audit.kind_${o.kind}`)}
                                          </span>
                                      </td>
                                      <td><strong>${o.entity}</strong> <span class="muted">#${o.osm_id}</span></td>
                                      <td>${o.reason || '—'}</td>
                                      <td class="muted">${o.updated_by}</td>
                                      <td class="muted">${o.updated_at.slice(0, 16).replace('T', ' ')}</td>
                                      <td class="actions">
                                          <platform-button
                                              size="sm"
                                              variant="ghost"
                                              title=${this.t('audit.revert')}
                                              ?busy=${this._revertCtl.busy ||
                                              this._unsuppressCtl.busy ||
                                              this._edgeOpenCtl.busy}
                                              @click=${() => this._revert(o)}
                                          >
                                              <platform-icon name="rotate-ccw" size="14"></platform-icon>
                                          </platform-button>
                                      </td>
                                  </tr>
                              `,
                          )}
                </tbody>
            </table>
        `;
    }

    override render() {
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                dense
                title=${this.t('addresses.header_title')}
            ></page-header>
            <div class="tabs">
                <button
                    class="tab ${this._tab === 'directory' ? 'active' : ''}"
                    @click=${() => this._switchTab('directory')}
                >${this.t('addresses.tab_directory')}</button>
                <button
                    class="tab ${this._tab === 'audit' ? 'active' : ''}"
                    @click=${() => this._switchTab('audit')}
                >${this.t('addresses.tab_audit')}</button>
            </div>
            <div class="card">
                ${this._tab === 'directory' ? this._renderDirectory() : this._renderAudit()}
            </div>
        `;
    }

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .tabs { display: flex; gap: var(--space-2); margin-bottom: var(--space-3); }
            .tab {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .tab.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }
            .card {
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .toolbar {
                display: flex;
                align-items: flex-end;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }
            .search-box { flex: 1; max-width: 480px; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { text-align: left; padding: var(--space-2) var(--space-3); vertical-align: top; }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); font-size: var(--text-xs); text-transform: uppercase; }
            td { color: var(--text-primary); border-top: 1px solid var(--glass-border-subtle); }
            .muted { color: var(--text-tertiary); }
            .actions { white-space: nowrap; text-align: right; }
            .pill {
                display: inline-block;
                padding: 1px var(--space-2);
                border-radius: var(--radius-full, 999px);
                font-size: var(--text-xs);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .pill.manual { background: var(--glass-solid-medium); color: var(--text-secondary); }
            .pill.danger { background: color-mix(in srgb, var(--danger, #dc2626) 15%, transparent); color: var(--danger, #dc2626); }
        `,
    ];
}

customElements.define('geo-addresses-page', GeoAddressesPage);
