/**
 * OfficeCatalogRagModal — RAG-индексация каталога документов.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import {
    buildAdvancedRetrievalPayloadFromPanel,
    defaultRetrievalPanelValue,
    packAdvancedRetrievalPayload,
    packSearchRequestOptions,
    panelValueFromSearchOptions,
} from '@platform/lib/rag/pack_search_request_options.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/rag/platform-rag-retrieval-panel.js';
import '@platform/lib/components/glass-spinner.js';

const STATUS_OP = 'office/catalog_rag_status';
const ENABLE_OP = 'office/catalog_rag_enable';
const DISABLE_OP = 'office/catalog_rag_disable';
const REBUILD_OP = 'office/catalog_rag_rebuild';
const SETTINGS_OP = 'office/catalog_rag_settings';
const CATALOGS_NAME = 'office/catalogs';

export class OfficeCatalogRagModal extends PlatformFormModal {
    static modalKind = 'office.catalog_rag';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        catalogTitle: { type: String },
        _retrievalPanel: { state: true },
        _platformDefaults: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .rag-grid {
                display: grid;
                gap: var(--space-4);
            }
            .switch-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .switch-label {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: 500;
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .totals {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2);
            }
            .total-item {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
            }
            .total-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .total-value {
                font-size: var(--text-lg);
                font-weight: 600;
                color: var(--text-primary);
            }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .loading-row {
                padding: var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .search-options-section {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding-top: var(--space-2);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .search-options-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.catalogId = '';
        this.catalogTitle = '';
        this._retrievalPanel = defaultRetrievalPanelValue();
        this._platformDefaults = null;
        this._status = this.useOp(STATUS_OP);
        this._enable = this.useOp(ENABLE_OP);
        this._disable = this.useOp(DISABLE_OP);
        this._rebuild = this.useOp(REBUILD_OP);
        this._settings = this.useOp(SETTINGS_OP);
        this._catalogs = this.useResource(CATALOGS_NAME);
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.catalogId === 'string' && this.catalogId.length > 0) {
            this._status.run({ catalog_id: this.catalogId });
        }
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('_status') || changed.has('catalogId')) {
            this._syncRetrievalPanelFromStatus();
        }
    }

    _syncRetrievalPanelFromStatus() {
        const status = this._statusPayload();
        if (!status) {
            return;
        }
        const searchOptions = status.search_options;
        this._retrievalPanel = panelValueFromSearchOptions(
            searchOptions && typeof searchOptions === 'object' ? searchOptions : null,
        );
        const platformDefaults = status.platform_defaults;
        this._platformDefaults = platformDefaults && typeof platformDefaults === 'object'
            ? platformDefaults
            : null;
    }

    renderHeader() {
        const title = typeof this.catalogTitle === 'string' ? this.catalogTitle.trim() : '';
        if (title.length > 0) {
            return this.t('catalog_rag_modal.header_with_title', { title });
        }
        return this.t('catalog_rag_modal.header');
    }

    renderSaveHeaderButton() {
        return '';
    }

    _statusPayload() {
        const result = this._status.lastResult;
        if (!result || typeof result !== 'object') {
            return null;
        }
        return result;
    }

    _locale() {
        const locale = this._localeSel.value;
        return typeof locale === 'string' && locale.length > 0 ? locale : 'ru';
    }

    _formatUpdatedAt(value) {
        if (typeof value !== 'string' || value.length === 0) {
            return this.t('catalog_rag_modal.updated_never');
        }
        return formatPlatformDateTime(value, this._locale());
    }

    async _onToggleEnabled(e) {
        const enabled = e.detail && e.detail.value === true;
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            return;
        }
        if (enabled) {
            await this._enable.run({ catalog_id: this.catalogId });
        } else {
            await this._disable.run({ catalog_id: this.catalogId });
        }
        this._catalogs.load(null);
    }

    async _onRebuild() {
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            return;
        }
        await this._rebuild.run({ catalog_id: this.catalogId });
        this._catalogs.load(null);
    }

    async _onToggleIncludeSubcatalogs(e) {
        const includeSubcatalogs = e.detail && e.detail.value === true;
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            return;
        }
        await this._settings.run({
            catalog_id: this.catalogId,
            include_subcatalogs: includeSubcatalogs,
        });
        this._catalogs.load(null);
    }

    async _onSaveSearchOptions() {
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            return;
        }
        const panel = this._retrievalPanel;
        if (!panel || typeof panel !== 'object' || Array.isArray(panel)) {
            throw new Error('OfficeCatalogRagModal: invalid retrieval panel state');
        }
        /** @type {Record<string, unknown>} */
        const packed = { catalog_id: this.catalogId };
        if (panel.usePlatformDefaults === true) {
            packed.clear_search_options = true;
        } else {
            const panelPayload = buildAdvancedRetrievalPayloadFromPanel(panel);
            Object.assign(
                packed,
                packSearchRequestOptions(panelPayload),
                packAdvancedRetrievalPayload(panelPayload),
            );
        }
        await this._settings.run(packed);
        this._catalogs.load(null);
    }

    _onRetrievalPanelChange(e) {
        const value = e.detail && e.detail.value;
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            throw new Error('OfficeCatalogRagModal: invalid retrieval panel value');
        }
        this._retrievalPanel = value;
    }

    _renderTotals(totals) {
        if (!totals || typeof totals !== 'object') {
            return '';
        }
        const rows = [
            { key: 'ready', label: this.t('catalog_rag_modal.totals_ready') },
            { key: 'pending', label: this.t('catalog_rag_modal.totals_pending') },
            { key: 'failed', label: this.t('catalog_rag_modal.totals_failed') },
            { key: 'absent', label: this.t('catalog_rag_modal.totals_absent') },
        ];
        return html`
            <div class="totals">
                ${rows.map((row) => html`
                    <div class="total-item">
                        <div class="total-label">${row.label}</div>
                        <div class="total-value">${totals[row.key]}</div>
                    </div>
                `)}
            </div>
        `;
    }

    renderBody() {
        const status = this._statusPayload();
        const busy = this._status.busy || this._enable.busy || this._disable.busy
            || this._rebuild.busy || this._settings.busy;
        if (this._status.busy && !status) {
            return html`<div class="loading-row"><glass-spinner></glass-spinner></div>`;
        }
        const enabled = status && status.enabled === true;
        const includeSubcatalogs = status && status.include_subcatalogs === true;
        const totals = status && status.totals;
        const updatedAt = status && status.rag_index_updated_at;
        return html`
            <div class="rag-grid">
                <div class="switch-row">
                    <div>
                        <div class="switch-label">${this.t('catalog_rag_modal.enabled_label')}</div>
                        <div class="hint">${this.t('catalog_rag_modal.enabled_hint')}</div>
                    </div>
                    <platform-switch
                        ?checked=${enabled}
                        ?disabled=${busy}
                        @change=${this._onToggleEnabled}
                    ></platform-switch>
                </div>
                ${enabled ? html`
                    <div class="switch-row">
                        <div>
                            <div class="switch-label">${this.t('catalog_rag_modal.include_subcatalogs_label')}</div>
                            <div class="hint">${this.t('catalog_rag_modal.include_subcatalogs_hint')}</div>
                        </div>
                        <platform-switch
                            ?checked=${includeSubcatalogs}
                            ?disabled=${busy}
                            @change=${this._onToggleIncludeSubcatalogs}
                        ></platform-switch>
                    </div>
                    <div class="search-options-section">
                        <div class="switch-label">${this.t('catalog_rag_modal.search_options_title')}</div>
                        <div class="search-options-hint">${this.t('catalog_rag_modal.search_options_hint')}</div>
                        <platform-rag-retrieval-panel
                            compact
                            .value=${this._retrievalPanel}
                            .platformDefaults=${this._platformDefaults}
                            ?disabled=${busy}
                            @change=${this._onRetrievalPanelChange}
                        ></platform-rag-retrieval-panel>
                        <button
                            type="button"
                            class="btn btn-secondary"
                            ?disabled=${busy}
                            @click=${this._onSaveSearchOptions}
                        >
                            ${this.t('catalog_rag_modal.search_options_save')}
                        </button>
                    </div>
                    ${this._renderTotals(totals)}
                    <div class="hint">
                        ${includeSubcatalogs
                            ? this.t('catalog_rag_modal.subtree_scope_hint')
                            : this.t('catalog_rag_modal.current_catalog_scope_hint')}
                    </div>
                    <div class="hint">
                        ${this.t('catalog_rag_modal.updated_at', { value: this._formatUpdatedAt(updatedAt) })}
                    </div>
                ` : ''}
            </div>
        `;
    }

    renderFooter() {
        const status = this._statusPayload();
        const enabled = status && status.enabled === true;
        const busy = this._status.busy || this._enable.busy || this._disable.busy
            || this._rebuild.busy || this._settings.busy;
        return html`
            <div class="footer-actions">
                <button class="btn btn-secondary" type="button" @click=${() => this.close()}>${this.t('catalog_rag_modal.close')}</button>
                ${enabled ? html`
                    <button class="btn btn-primary" type="button" ?disabled=${busy} @click=${this._onRebuild}>
                        ${this.t('catalog_rag_modal.rebuild')}
                    </button>
                ` : ''}
            </div>
        `;
    }
}

registerModalKind(OfficeCatalogRagModal.modalKind, 'office-catalog-rag-modal');

customElements.define('office-catalog-rag-modal', OfficeCatalogRagModal);
