/**
 * flows-mcp-servers-modal — управление MCP-серверами компании.
 *
 * Список в виде карточек; форма создания/редактирования: поля, Headers (JSON), пресеты.
 * useResource('flows/mcp_servers'); update — flows/mcp_server_update; sync/test — useOp.
 */

import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { buildFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-file-attachments.js';
import '@platform/lib/components/platform-picker-card.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import { renderMcpServerIcon } from '../_helpers/mcp-server-icon.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';

const SERVER_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]{1,63}$/;
const TRANSPORT_TYPES = Object.freeze(['http', 'sse']);
const INSTALLED_PAGE_SIZE = 50;
const CATALOG_PAGE_SIZE = 50;
const BRANDING_PAGE_SIZE = 40;
const BRANDING_SUGGEST_LIMIT = 8;

/**
 * @param {unknown} raw
 * @returns {'http'|'sse'}
 */
function normalizeMcpTransportType(raw) {
    if (typeof raw !== 'string') {
        return 'http';
    }
    const t = raw.trim().toLowerCase();
    if (t === 'http' || t === 'sse') {
        return t;
    }
    return 'http';
}

const HEADER_PRESET_BEARER = '{\n  "Authorization": "Bearer @var:token"\n}';
const HEADER_PRESET_API_KEY = '{\n  "X-API-Key": "@var:api_key"\n}';
const HEADER_PRESET_BASIC = '{\n  "Authorization": "Basic @var:basic_credentials"\n}';
const HEADER_PRESET_OPTIONS = Object.freeze([
    Object.freeze({ id: 'bearer', titleKey: 'mcp_servers_modal.preset_bearer', icon: 'key' }),
    Object.freeze({ id: 'apikey', titleKey: 'mcp_servers_modal.preset_api_key', icon: 'key' }),
    Object.freeze({ id: 'basic', titleKey: 'mcp_servers_modal.preset_basic', icon: 'lock' }),
]);
const PLATFORM_MCP_SLUGS = Object.freeze(['browser', 'search']);

/**
 * @param {unknown} h
 * @returns {string}
 */
function headersObjectToJsonString(h) {
    if (!isPlainObject(h) || Object.keys(h).length === 0) {
        return '{}';
    }
    return formatJsonPretty(h);
}

/**
 * @param {string} text
 * @returns {Record<string, string>}
 */
function parseHeadersJson(text) {
    if (typeof text !== 'string') {
        throw new Error('mcp headers: string required');
    }
    const trimmed = text.trim();
    if (trimmed.length === 0) {
        return {};
    }
    const parsed = JSON.parse(trimmed);
    if (!isPlainObject(parsed)) {
        throw new Error('mcp headers: JSON must be an object');
    }
    const out = {};
    for (const [k, v] of Object.entries(parsed)) {
        if (typeof v === 'string') {
            out[k] = v;
        } else {
            throw new Error('mcp headers: every value must be a string');
        }
    }
    return out;
}

export class FlowsMcpServersModal extends PlatformModal {
    static modalKind = 'flows.mcp_servers';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        _view: { state: true },
        _editing: { state: true },
        _form: { state: true },
        _formError: { state: true },
        _saving: { state: true },
        _testFeedback: { state: true },
        _testingServerId: { state: true },
        _search: { state: true },
        _installedItems: { state: true },
        _installedTotal: { state: true },
        _installedLoading: { state: true },
        _installedError: { state: true },
        _catalogItems: { state: true },
        _catalogTotal: { state: true },
        _catalogLoading: { state: true },
        _catalogError: { state: true },
        _brandingItems: { state: true },
        _brandingTotal: { state: true },
        _brandingSearch: { state: true },
        _brandingSlugSuggestions: { state: true },
        _brandingEditingSlug: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        panelShellStyles,
        glassStyles,
        css`
            .flows-header-action-create {
                display: none;
            }
            .mcp-title-row platform-modal-search-field {
                margin-left: auto;
            }
            .mcp-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-width: 0;
                width: 100%;
                font-size: var(--text-sm);
                line-height: 1.2;
            }
            .mcp-title-text {
                flex-shrink: 0;
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-tight);
                color: var(--text-primary);
            }
            .modal-title:has(.mcp-title-row) {
                white-space: normal;
                overflow: visible;
                text-overflow: clip;
            }
            .mcp-cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                max-height: min(70vh, 640px);
                overflow-y: auto;
                padding: var(--space-1);
            }
            .mcp-cards.is-fullscreen {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                max-height: none;
                flex: 1;
                min-height: 0;
                align-content: start;
            }
            @media (max-width: 1280px) {
                .mcp-cards.is-fullscreen {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (max-width: 768px) {
                .mcp-cards.is-fullscreen {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
            .mcp-card {
                gap: var(--space-2);
                padding: var(--space-4);
            }
            .mcp-card-shell {
                min-width: 0;
                display: flex;
                flex-direction: column;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--shadow-xs);
                overflow: hidden;
                flex: none;
            }
            .mcp-card-top {
                display: flex;
                flex-wrap: wrap;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .mcp-card-head-row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                min-width: 0;
                flex: 1;
            }
            .mcp-card-icon {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .mcp-card-icon .mcp-server-icon-img {
                width: 28px;
                height: 28px;
                object-fit: contain;
            }
            .mcp-card-titles h3 {
                margin: 0;
                font-size: var(--text-md);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .mcp-card-titles .sub {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-top: 2px;
            }
            .mcp-card-actions {
                display: inline-flex;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            .mcp-card-url {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                word-break: break-all;
            }
            .mcp-card-meta {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .mcp-chip {
                display: inline-block;
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--info-subtle);
                color: var(--info);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .mcp-chip-warn {
                background: var(--warning-subtle);
                color: var(--warning);
            }
            .mcp-card-footer {
                display: flex;
                justify-content: flex-end;
            }
            .mcp-headers-line {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
            }
            .mcp-empty { text-align: center; color: var(--text-tertiary); padding: var(--space-6); }
            .mcp-form {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                max-height: min(75vh, 720px);
                overflow-y: auto;
                padding: var(--space-1);
            }
            .mcp-field { display: flex; flex-direction: column; gap: var(--space-1); }
            .mcp-field label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            .mcp-field .hint { font-size: var(--text-xs); color: var(--text-tertiary); }
            .mcp-field input, .mcp-field select, .mcp-field textarea {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                color: var(--text-primary);
                font: inherit;
            }
            .mcp-field textarea { min-height: 120px; font-family: var(--font-mono); font-size: var(--text-sm); }
            .mcp-header-presets {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: var(--space-2);
            }
            .mcp-header-presets platform-picker-card {
                min-width: 0;
            }
            .mcp-form-err { font-size: var(--text-sm); color: var(--error); }
            .mcp-test-feedback {
                font-size: var(--text-sm);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            .mcp-test-feedback.ok {
                background: var(--success-subtle);
                color: var(--success);
            }
            .mcp-test-feedback.err {
                background: var(--error-subtle);
                color: var(--error);
            }
            .mcp-branding-toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .mcp-branding-form {
                gap: var(--space-3);
                padding: var(--space-4);
            }
            .mcp-branding-layout {
                display: grid;
                grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
                gap: var(--space-4);
                min-height: min(70vh, 680px);
            }
            .mcp-branding-composer {
                position: sticky;
                top: 0;
                align-self: start;
            }
            .mcp-branding-slugs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .mcp-branding-preview {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
            }
            .mcp-branding-preview-icon {
                width: 64px;
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                flex-shrink: 0;
            }
            .mcp-branding-preview-icon .mcp-server-icon-img {
                width: 48px;
                height: 48px;
                object-fit: contain;
            }
            .mcp-branding-preview-text {
                min-width: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .mcp-branding-gallery {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .mcp-branding-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: var(--space-3);
                align-content: start;
            }
            .mcp-branding-card {
                position: relative;
                min-height: 150px;
                padding: var(--space-4) var(--space-3) var(--space-3);
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                cursor: pointer;
            }
            .mcp-branding-card[aria-selected='true'] {
                border-color: var(--accent);
                box-shadow: 0 0 0 1px var(--accent-subtle);
            }
            .mcp-branding-card-icon {
                width: 56px;
                height: 56px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
            }
            .mcp-branding-card-icon .mcp-server-icon-img {
                width: 40px;
                height: 40px;
                object-fit: contain;
            }
            .mcp-branding-card-title {
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm);
            }
            .mcp-branding-card-hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .mcp-branding-card-delete {
                position: absolute;
                top: var(--space-2);
                right: var(--space-2);
            }
            @media (max-width: 768px) {
                .mcp-branding-layout {
                    grid-template-columns: minmax(0, 1fr);
                }
                .mcp-branding-composer {
                    position: static;
                }
            }
            .mcp-branding-row-icon {
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                flex-shrink: 0;
            }
            .mcp-branding-row-icon .mcp-server-icon-img {
                width: 32px;
                height: 32px;
                object-fit: contain;
            }
            .mcp-branding-row-meta {
                flex: 1;
                min-width: 0;
            }
            .mcp-branding-row-meta code {
                font-size: var(--text-sm);
            }
            .mcp-branding-row-actions {
                display: inline-flex;
                gap: var(--space-1);
            }
            .mcp-list-toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .mcp-list-tabs {
                min-width: min(360px, 100%);
                flex: 1;
                max-width: 520px;
            }
            .mcp-error-panel {
                text-align: center;
                color: var(--error);
                padding: var(--space-6);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
            }
            .mcp-branding-link {
                border: none;
                background: transparent;
                color: var(--accent);
                font-size: var(--text-sm);
                cursor: pointer;
                padding: var(--space-1) var(--space-2);
            }
            .mcp-branding-link:hover {
                text-decoration: underline;
            }
            .mcp-load-more {
                display: flex;
                justify-content: center;
                padding: var(--space-3) 0 var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.headerSavePrimary = true;
        this.size = 'lg';
        this._saving = false;
        this._view = 'list';
        this._listTab = 'installed';
        this._editing = null;
        this._form = {
            server_id: '',
            name: '',
            url: '',
            transport_type: 'http',
            description: '',
            headers_json: '{}',
        };
        this._formError = null;
        this._testFeedback = null;
        this._testingServerId = null;
        this._brandingItems = [];
        this._brandingTotal = 0;
        this._brandingSearch = '';
        this._brandingSlugSuggestions = [];
        this._brandingEditingSlug = '';
        this._brandingForm = { server_id: '', icon_file_id: '' };
        this._brandingUploadFiles = [];
        this._brandingError = null;
        this._brandingSaving = false;
        this._brandingLoading = false;
        this._activeCompanySel = this.select((s) => s.auth.activeCompanyId);
        this._servers = this.useResource('flows/mcp_servers');
        this._serversListOp = this.useOp('flows/mcp_servers_list');
        this._update = this.useOp('flows/mcp_server_update');
        this._syncOp = this.useOp('flows/mcp_server_sync');
        this._testOp = this.useOp('flows/mcp_server_test');
        this._resetCatalogOp = this.useOp('flows/mcp_server_reset_catalog_defaults');
        this._brandingLoadOp = this.useOp('flows/mcp_branding_load');
        this._brandingSlugSuggestOp = this.useOp('flows/mcp_branding_slug_suggest');
        this._brandingUpsertOp = this.useOp('flows/mcp_branding_upsert');
        this._brandingRemoveOp = this.useOp('flows/mcp_branding_remove');
        this._catalogLoadOp = this.useOp('flows/mcp_catalog_store_load');
        this._catalogInstallOp = this.useOp('flows/mcp_catalog_install');
        this._catalogUninstallOp = this.useOp('flows/mcp_catalog_uninstall');
        this._catalogItems = [];
        this._catalogLoading = false;
        this._catalogError = null;
        this._catalogInstallingId = null;
        this._catalogTotal = 0;
        this._installedItems = [];
        this._installedTotal = 0;
        this._installedLoading = false;
        this._installedError = null;
        this._catalogSearchTimer = null;
        this._installedSearchTimer = null;
        this._brandingSearchTimer = null;
        this._brandingSlugTimer = null;
        this._search = '';
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this._view = 'list';
            this._listTab = 'installed';
            this._editing = null;
            this._formError = null;
            this._saving = false;
            this._testFeedback = null;
            this._testingServerId = null;
            this._brandingError = null;
            this._brandingSaving = false;
            this._brandingUploadFiles = [];
            this._search = '';
            this._catalogItems = [];
            this._catalogLoading = false;
            this._catalogError = null;
            this._catalogInstallingId = null;
            this._catalogTotal = 0;
            this._installedItems = [];
            this._installedTotal = 0;
            this._installedLoading = false;
            this._installedError = null;
            this._brandingItems = [];
            this._brandingTotal = 0;
            this._brandingSearch = '';
            this._brandingSlugSuggestions = [];
            this._brandingEditingSlug = '';
            if (this._catalogSearchTimer !== null) {
                clearTimeout(this._catalogSearchTimer);
                this._catalogSearchTimer = null;
            }
            if (this._installedSearchTimer !== null) {
                clearTimeout(this._installedSearchTimer);
                this._installedSearchTimer = null;
            }
            if (this._brandingSearchTimer !== null) {
                clearTimeout(this._brandingSearchTimer);
                this._brandingSearchTimer = null;
            }
            if (this._brandingSlugTimer !== null) {
                clearTimeout(this._brandingSlugTimer);
                this._brandingSlugTimer = null;
            }
            this._resetFormFields();
            this._resetBrandingFormFields();
            this.size = 'lg';
            void this._loadInstalled({ reset: true });
        }
    }

    disconnectedCallback() {
        if (this._catalogSearchTimer !== null) {
            clearTimeout(this._catalogSearchTimer);
            this._catalogSearchTimer = null;
        }
        if (this._installedSearchTimer !== null) {
            clearTimeout(this._installedSearchTimer);
            this._installedSearchTimer = null;
        }
        if (this._brandingSearchTimer !== null) {
            clearTimeout(this._brandingSearchTimer);
            this._brandingSearchTimer = null;
        }
        if (this._brandingSlugTimer !== null) {
            clearTimeout(this._brandingSlugTimer);
            this._brandingSlugTimer = null;
        }
        super.disconnectedCallback();
    }

    _onSearchInput(e) {
        const v = e.detail?.value;
        if (typeof v !== 'string') {
            throw new TypeError('flows-mcp-servers-modal: search expects string detail.value');
        }
        if (this._view === 'branding') {
            this._brandingSearch = v;
            if (this._brandingSearchTimer !== null) {
                clearTimeout(this._brandingSearchTimer);
            }
            this._brandingSearchTimer = setTimeout(() => {
                this._brandingSearchTimer = null;
                void this._loadBranding({ reset: true });
            }, 250);
            return;
        }
        if (this._view !== 'list') {
            return;
        }
        this._search = v;
        if (this._listTab === 'catalog') {
            if (this._catalogSearchTimer !== null) {
                clearTimeout(this._catalogSearchTimer);
            }
            this._catalogSearchTimer = setTimeout(() => {
                this._catalogSearchTimer = null;
                void this._loadCatalog({ reset: true });
            }, 250);
            return;
        }
        if (this._installedSearchTimer !== null) {
            clearTimeout(this._installedSearchTimer);
        }
        this._installedSearchTimer = setTimeout(() => {
            this._installedSearchTimer = null;
            void this._loadInstalled({ reset: true });
        }, 250);
    }

    _renderInstalledEmptyState(messageKey) {
        return html`
            <div class="mcp-empty">
                <div>${this.t(messageKey)}</div>
                <platform-button variant="primary" density="compact" @click=${() => { void this._switchListTab('catalog'); }}>
                    ${this.t('mcp_servers_modal.action_open_catalog')}
                </platform-button>
            </div>
        `;
    }

    _hasPlatformDefaults(items) {
        const ids = new Set(
            items
                .map((item) => (typeof item.server_id === 'string' ? item.server_id : ''))
                .filter((id) => id.length > 0),
        );
        return PLATFORM_MCP_SLUGS.every((slug) => ids.has(slug));
    }

    _isOptInCatalogServer(server) {
        return server.source === 'catalog' && server.catalog_auto_provisioned !== true;
    }

    async _retryServersLoad() {
        await this._loadInstalled({ reset: true });
    }

    async _loadInstalled({ reset = false } = {}) {
        this._installedLoading = true;
        this._installedError = null;
        const offset = reset ? 0 : this._installedItems.length;
        try {
            const payload = await this._serversListOp.run({
                search: this._search,
                limit: INSTALLED_PAGE_SIZE,
                offset,
            });
            if (!isPlainObject(payload)) {
                throw new Error('flows-mcp-servers-modal: installed load invalid response');
            }
            const nextItems = asArray(payload.items);
            this._installedItems = reset ? nextItems : [...this._installedItems, ...nextItems];
            if (typeof payload.total !== 'number') {
                throw new Error('flows-mcp-servers-modal: installed load total required');
            }
            this._installedTotal = payload.total;
        } catch (err) {
            this._installedError = err instanceof Error ? err.message : String(err);
            if (reset) {
                this._installedItems = [];
                this._installedTotal = 0;
            }
        } finally {
            this._installedLoading = false;
        }
    }

    async _loadCatalog({ reset = false } = {}) {
        this._catalogLoading = true;
        this._catalogError = null;
        const offset = reset ? 0 : this._catalogItems.length;
        try {
            const payload = await this._catalogLoadOp.run({
                search: this._search,
                limit: CATALOG_PAGE_SIZE,
                offset,
            });
            if (!isPlainObject(payload)) {
                throw new Error('flows-mcp-servers-modal: catalog load invalid response');
            }
            const nextItems = asArray(payload.items);
            this._catalogItems = reset ? nextItems : [...this._catalogItems, ...nextItems];
            if (typeof payload.total !== 'number') {
                throw new Error('flows-mcp-servers-modal: catalog load total required');
            }
            this._catalogTotal = payload.total;
        } catch (err) {
            this._catalogError = err instanceof Error ? err.message : String(err);
            if (reset) {
                this._catalogItems = [];
                this._catalogTotal = 0;
            }
        } finally {
            this._catalogLoading = false;
        }
    }

    async _switchListTab(tab) {
        if (tab !== 'installed' && tab !== 'catalog') {
            throw new Error(`flows-mcp-servers-modal: invalid list tab ${tab}`);
        }
        this._listTab = tab;
        if (tab === 'catalog' && this._catalogItems.length === 0 && this._catalogError === null) {
            await this._loadCatalog({ reset: true });
        }
        if (tab === 'installed' && this._installedItems.length === 0 && this._installedError === null) {
            await this._loadInstalled({ reset: true });
        }
    }

    async _installCatalogEntry(entry) {
        if (!isPlainObject(entry) || typeof entry.catalog_id !== 'string') {
            throw new Error('flows-mcp-servers-modal: catalog install requires catalog_id');
        }
        this._catalogInstallingId = entry.catalog_id;
        try {
            await this._catalogInstallOp.run({ catalog_id: entry.catalog_id });
            await Promise.all([
                this._loadInstalled({ reset: true }),
                this._loadCatalog({ reset: true }),
            ]);
        } finally {
            this._catalogInstallingId = null;
        }
    }

    async _uninstallCatalogEntry(entry) {
        if (!isPlainObject(entry) || typeof entry.catalog_id !== 'string') {
            throw new Error('flows-mcp-servers-modal: catalog uninstall requires catalog_id');
        }
        const title = typeof entry.title === 'string' ? entry.title : entry.catalog_id;
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.catalog_uninstall_message', { title }),
            {
                title: this.t('mcp_servers_modal.catalog_uninstall_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('mcp_servers_modal.catalog_uninstall'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._catalogUninstallOp.run({ catalog_id: entry.catalog_id });
        await Promise.all([
            this._loadInstalled({ reset: true }),
            this._loadCatalog({ reset: true }),
        ]);
    }

    _renderHeaderSearch() {
        const value = this._view === 'branding' ? this._brandingSearch : this._search;
        const placeholderKey = this._view === 'branding'
            ? 'mcp_servers_modal.branding_search_placeholder'
            : 'mcp_servers_modal.search_placeholder';
        return html`
            <platform-modal-search-field
                layout="header"
                .value=${value}
                placeholder=${this.t(placeholderKey)}
                @change=${this._onSearchInput}
            ></platform-modal-search-field>
        `;
    }

    _resetBrandingFormFields() {
        this._brandingForm = { server_id: '', icon_file_id: '' };
        this._brandingEditingSlug = '';
        this._brandingSlugSuggestions = [];
    }

    _isSystemCompany() {
        return this._activeCompanySel.value === 'system';
    }

    _brandingUploadSpec() {
        return buildFileCreateSpecJson({
            sourceKind: 'platform_auxiliary',
            sourceRef: {},
            postCreate: { is_public: true },
        });
    }

    async _loadBranding({ reset = false } = {}) {
        this._brandingLoading = true;
        const offset = reset ? 0 : this._brandingItems.length;
        try {
            const payload = await this._brandingLoadOp.run({
                search: this._brandingSearch,
                limit: BRANDING_PAGE_SIZE,
                offset,
            });
            if (!isPlainObject(payload)) {
                throw new Error('flows-mcp-servers-modal: branding load invalid response');
            }
            const nextItems = asArray(payload.items);
            this._brandingItems = reset ? nextItems : [...this._brandingItems, ...nextItems];
            if (typeof payload.total !== 'number') {
                throw new Error('flows-mcp-servers-modal: branding load total required');
            }
            this._brandingTotal = payload.total;
        } catch (err) {
            if (reset) {
                this._brandingItems = [];
                this._brandingTotal = 0;
            }
            throw err;
        } finally {
            this._brandingLoading = false;
        }
    }

    async _loadBrandingSlugSuggestions(search) {
        const payload = await this._brandingSlugSuggestOp.run({
            search,
            limit: BRANDING_SUGGEST_LIMIT,
        });
        if (!isPlainObject(payload)) {
            throw new Error('flows-mcp-servers-modal: branding slug suggest invalid response');
        }
        this._brandingSlugSuggestions = asArray(payload.slugs).filter((slug) => typeof slug === 'string');
    }

    async _goBranding() {
        this._view = 'branding';
        this._brandingError = null;
        this._resetBrandingFormFields();
        this._brandingUploadFiles = [];
        this._brandingSearch = '';
        await Promise.all([
            this._loadBranding({ reset: true }),
            this._loadBrandingSlugSuggestions(''),
        ]);
    }

    _brandingCanSave() {
        const f = this._brandingForm;
        return SERVER_ID_PATTERN.test(f.server_id) && f.icon_file_id.length > 0;
    }

    _setBrandingSlug(value) {
        this._brandingForm = { ...this._brandingForm, server_id: value };
        this._brandingError = null;
        if (this._brandingSlugTimer !== null) {
            clearTimeout(this._brandingSlugTimer);
        }
        this._brandingSlugTimer = setTimeout(() => {
            this._brandingSlugTimer = null;
            void this._loadBrandingSlugSuggestions(value);
        }, 200);
    }

    _onBrandingFilesChange(event) {
        const detail = event.detail;
        if (!isPlainObject(detail)) {
            throw new TypeError('flows-mcp-servers-modal: branding files-change detail required');
        }
        const files = asArray(detail.files);
        this._brandingUploadFiles = files;
        const last = files.length > 0 ? files[files.length - 1] : null;
        if (last && typeof last.file_id === 'string' && last.file_id.length > 0) {
            this._brandingForm = { ...this._brandingForm, icon_file_id: last.file_id };
        } else {
            this._brandingForm = { ...this._brandingForm, icon_file_id: '' };
        }
        this._brandingError = null;
    }

    async _saveBranding() {
        if (!this._brandingCanSave()) {
            this._brandingError = this.t('mcp_servers_modal.branding_error_invalid');
            return;
        }
        this._brandingSaving = true;
        this._brandingError = null;
        try {
            await this._brandingUpsertOp.run({
                server_id: this._brandingForm.server_id.trim(),
                icon_file_id: this._brandingForm.icon_file_id,
            });
            this._resetBrandingFormFields();
            this._brandingUploadFiles = [];
            await this._loadBranding({ reset: true });
            void this._loadInstalled({ reset: true });
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._brandingError = message;
        } finally {
            this._brandingSaving = false;
        }
    }

    async _deleteBranding(serverId) {
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.branding_delete_message', { id: serverId }),
            {
                title: this.t('mcp_servers_modal.branding_delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('mcp_servers_modal.action_delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._brandingRemoveOp.run({ server_id: serverId });
        await this._loadBranding({ reset: true });
        void this._loadInstalled({ reset: true });
    }

    _applyBrandingSlug(slug) {
        if (typeof slug !== 'string' || slug.length === 0) {
            return;
        }
        this._brandingForm = { ...this._brandingForm, server_id: slug };
        this._brandingError = null;
    }

    _editBranding(row) {
        if (!isPlainObject(row) || typeof row.server_id !== 'string') {
            throw new Error('flows-mcp-servers-modal: branding row with server_id required');
        }
        const iconFileId = typeof row.icon_file_id === 'string' ? row.icon_file_id : '';
        this._brandingForm = { server_id: row.server_id, icon_file_id: iconFileId };
        this._brandingEditingSlug = row.server_id;
        this._brandingUploadFiles = [];
        this._brandingError = null;
    }

    _resetFormFields() {
        this._form = {
            server_id: '',
            name: '',
            url: '',
            transport_type: 'http',
            description: '',
            headers_json: '{}',
        };
    }

    _formCanSave() {
        const f = this._form;
        return SERVER_ID_PATTERN.test(f.server_id) && f.name.trim().length > 0 && f.url.trim().length > 0;
    }

    _goList() {
        this._view = 'list';
        this._editing = null;
        this._formError = null;
        this._resetFormFields();
    }

    _goAdd() {
        this._view = 'form';
        this._editing = null;
        this._formError = null;
        this._resetFormFields();
    }

    _editServer(s) {
        this._view = 'form';
        this._editing = s.server_id;
        this._formError = null;
        const h = s.headers;
        const headersStr = isPlainObject(h) ? headersObjectToJsonString(h) : '{}';
        this._form = {
            server_id: s.server_id,
            name: s.name,
            url: s.url,
            transport_type: normalizeMcpTransportType(s.transport_type),
            description: asString(s.description),
            headers_json: headersStr,
        };
    }

    _transportLabel(value) {
        if (value === 'http') {
            return this.t('mcp_servers_modal.transport_http');
        }
        if (value === 'sse') {
            return this.t('mcp_servers_modal.transport_sse');
        }
        return this.t('mcp_servers_modal.transport_unknown');
    }

    _formatLastSync(s) {
        const raw = s.last_sync_at;
        if (raw === null || raw === undefined) {
            return this.t('mcp_servers_modal.sync_never');
        }
        if (raw instanceof Date) {
            if (Number.isNaN(raw.getTime())) {
                return this.t('mcp_servers_modal.sync_invalid');
            }
            return new Intl.DateTimeFormat(undefined, {
                dateStyle: 'short',
                timeStyle: 'medium',
            }).format(raw);
        }
        if (typeof raw === 'string' && raw.length > 0) {
            const d = new Date(raw);
            if (Number.isNaN(d.getTime())) {
                return this.t('mcp_servers_modal.sync_invalid');
            }
            return new Intl.DateTimeFormat(undefined, {
                dateStyle: 'short',
                timeStyle: 'medium',
            }).format(d);
        }
        return this.t('mcp_servers_modal.sync_invalid');
    }

    _headerNamesSummary(s) {
        if (!isPlainObject(s.headers)) {
            return this.t('mcp_servers_modal.headers_none');
        }
        const keys = Object.keys(s.headers);
        if (keys.length === 0) {
            return this.t('mcp_servers_modal.headers_none');
        }
        return this.t('mcp_servers_modal.headers_keys_prefix') + keys.join(', ');
    }

    _toolsCount(s) {
        if (Array.isArray(s.cached_tools)) {
            return s.cached_tools.length;
        }
        return 0;
    }

    async _save() {
        if (this._saving) {
            return;
        }
        const f = this._form;
        if (!this._formCanSave()) {
            return;
        }
        let headers;
        try {
            headers = parseHeadersJson(f.headers_json);
        } catch (e) {
            const msg = e instanceof Error ? e.message : 'mcp headers parse';
            this._formError = msg;
            return;
        }
        this._formError = null;
        this._saving = true;
        try {
            if (this._editing) {
                await this._update.run({
                    server_id: f.server_id,
                    body: {
                        name: f.name,
                        url: f.url,
                        transport_type: f.transport_type,
                        description: f.description,
                        headers,
                    },
                });
            } else {
                await this._servers.create({
                    server_id: f.server_id,
                    name: f.name,
                    url: f.url,
                    transport_type: f.transport_type,
                    description: f.description,
                    headers,
                });
            }
            this._goList();
            await this._loadInstalled({ reset: true });
        } finally {
            this._saving = false;
        }
    }

    async _sync(s) {
        await this._syncOp.run({ server_id: s.server_id });
        await this._loadInstalled({ reset: true });
    }

    async _runTest(serverId) {
        if (typeof serverId !== 'string' || serverId.length === 0) {
            throw new Error('flows-mcp-servers-modal: serverId required for test');
        }
        this._testingServerId = serverId;
        this._testFeedback = null;
        try {
            const result = await this._testOp.run({ server_id: serverId });
            if (result !== null) {
                if (!isPlainObject(result) || typeof result.tools_count !== 'number') {
                    throw new TypeError('flows-mcp-servers-modal: MCP test result must include tools_count');
                }
                this._testFeedback = {
                    serverId,
                    ok: true,
                    toolsCount: result.tools_count,
                };
                return;
            }
            if (typeof this._testOp.error !== 'string') {
                throw new Error('flows-mcp-servers-modal: MCP test failed without error message');
            }
            this._testFeedback = {
                serverId,
                ok: false,
                message: this._testOp.error,
            };
        } finally {
            this._testingServerId = null;
        }
    }

    async _test(s) {
        await this._runTest(s.server_id);
    }

    async _testFromForm() {
        if (typeof this._editing !== 'string' || this._editing.length === 0) {
            return;
        }
        await this._runTest(this._editing);
    }

    _renderTestFeedback(serverId) {
        const fb = this._testFeedback;
        if (!fb || fb.serverId !== serverId) {
            return html``;
        }
        if (fb.ok === true) {
            return html`
                <div class="mcp-test-feedback ok" role="status">
                    ${this.t('mcp_servers_modal.test_result_ok', { n: fb.toolsCount })}
                </div>
            `;
        }
        return html`
            <div class="mcp-test-feedback err" role="alert">
                ${this.t('mcp_servers_modal.test_result_error', { message: fb.message })}
            </div>
        `;
    }

    async _onToggleActive(s, e) {
        const d = e.detail;
        if (!d || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'boolean') {
            throw new Error('mcp: platform-switch must emit detail.value boolean');
        }
        await this._update.run({ server_id: s.server_id, body: { is_active: d.value } });
        await this._loadInstalled({ reset: true });
    }

    _sourceLabel(source) {
        if (source === 'platform') {
            return this.t('mcp_servers_modal.source_platform');
        }
        if (source === 'catalog') {
            return this.t('mcp_servers_modal.source_catalog');
        }
        if (source === 'manual') {
            return this.t('mcp_servers_modal.source_manual');
        }
        return this.t('mcp_servers_modal.source_unknown');
    }

    async _resetCatalogDefaults(s) {
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.reset_confirm_message', { id: s.server_id }),
            {
                title: this.t('mcp_servers_modal.reset_confirm_title'),
                variant: 'danger',
                confirmVariant: 'primary',
                confirmText: this.t('mcp_servers_modal.action_reset_defaults'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._resetCatalogOp.run({ server_id: s.server_id });
        await this._loadInstalled({ reset: true });
    }

    async _delete(s) {
        if (this._isOptInCatalogServer(s) && typeof s.catalog_id === 'string' && s.catalog_id.length > 0) {
            await this._uninstallCatalogEntry({ catalog_id: s.catalog_id, title: s.name });
            return;
        }
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.delete_message', { id: s.server_id }),
            {
                title: this.t('mcp_servers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('mcp_servers_modal.action_delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._servers.remove(s.server_id);
        await this._loadInstalled({ reset: true });
    }

    _applyPreset(preset) {
        if (preset === 'bearer') {
            this._form = { ...this._form, headers_json: HEADER_PRESET_BEARER };
        } else if (preset === 'apikey') {
            this._form = { ...this._form, headers_json: HEADER_PRESET_API_KEY };
        } else if (preset === 'basic') {
            this._form = { ...this._form, headers_json: HEADER_PRESET_BASIC };
        }
        this._formError = null;
    }

    _renderList() {
        const allItems = this._installedItems;
        if (typeof this._installedError === 'string' && this._installedError.length > 0) {
            return html`
                <div class="mcp-error-panel" role="alert">
                    <div>${this.t('mcp_servers_modal.load_error', { message: this._installedError })}</div>
                    <platform-button variant="primary" density="compact" @click=${() => { void this._retryServersLoad(); }}>
                        ${this.t('mcp_servers_modal.action_retry')}
                    </platform-button>
                </div>
            `;
        }
        if (this._installedLoading && allItems.length === 0) {
            return html`<div class="mcp-empty"><glass-spinner></glass-spinner></div>`;
        }
        if (allItems.length === 0) {
            return this._search.trim().length > 0
                ? html`<div class="mcp-empty">${this.t('mcp_servers_modal.empty_search')}</div>`
                : this._renderInstalledEmptyState('mcp_servers_modal.empty_init_pending');
        }
        if (!this._hasPlatformDefaults(allItems) && this._search.trim().length === 0) {
            return this._renderInstalledEmptyState('mcp_servers_modal.empty_init_pending');
        }
        return html`
            ${allItems.map((s) => html`
            <div class="mcp-card mcp-card-shell">
                <div class="mcp-card-top">
                    <div class="mcp-card-head-row">
                        <div class="mcp-card-icon glass-subtle">${renderMcpServerIcon(s, 28)}</div>
                        <div class="mcp-card-titles">
                            <h3>${s.name}</h3>
                            <div class="sub"><code>${s.server_id}</code></div>
                        </div>
                    </div>
                    <div class="mcp-card-actions">
                        <platform-switch
                            size="sm"
                            ?checked=${s.is_active === true}
                            @change=${(e) => { e.stopPropagation(); this._onToggleActive(s, e); }}
                        ></platform-switch>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            @click=${() => this._sync(s)}
                            title=${this.t('mcp_servers_modal.action_sync_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_sync_aria')}
                        >
                            <platform-icon name="rotate-ccw" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            @click=${() => this._test(s)}
                            ?disabled=${this._testingServerId === s.server_id}
                            title=${this.t('mcp_servers_modal.action_test_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_test_aria')}
                        >
                            ${this._testingServerId === s.server_id
                                ? html`<glass-spinner size="sm"></glass-spinner>`
                                : html`<platform-icon name="check" size="16"></platform-icon>`}
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            @click=${() => this._editServer(s)}
                            title=${this.t('mcp_servers_modal.action_edit_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_edit_aria')}
                        >
                            <platform-icon name="edit" size="16"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            danger
                            ?disabled=${s.source === 'platform'}
                            @click=${() => this._delete(s)}
                            title=${this.t('mcp_servers_modal.action_delete_aria')}
                            aria-label=${this.t('mcp_servers_modal.action_delete_aria')}
                        >
                            <platform-icon name="trash" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="mcp-card-url">${s.url}</div>
                <div class="mcp-card-meta">
                    <span class="mcp-chip">${this._transportLabel(s.transport_type)}</span>
                    <span class="mcp-chip">${this._sourceLabel(s.source)}</span>
                    ${s.override_locked === true
                        ? html`<span class="mcp-chip mcp-chip-warn">${this.t('mcp_servers_modal.override_locked')}</span>`
                        : ''}
                    <span>${this.t('mcp_servers_modal.tools_count', { n: this._toolsCount(s) })}</span>
                    <span>${this.t('mcp_servers_modal.sync_label')} ${this._formatLastSync(s)}</span>
                </div>
                <div class="mcp-headers-line">${this._headerNamesSummary(s)}</div>
                ${this._renderTestFeedback(s.server_id)}
                ${s.source === 'catalog'
                    ? html`
                        <div class="mcp-card-footer">
                            <platform-button
                                variant="ghost"
                                density="compact"
                                @click=${() => this._resetCatalogDefaults(s)}>
                                ${this.t('mcp_servers_modal.action_reset_defaults')}
                            </platform-button>
                        </div>
                    `
                    : ''}
            </div>
            `)}
            ${this._installedItems.length < this._installedTotal
                ? this._renderLoadMore(() => this._loadInstalled(), this._installedLoading)
                : html``}
        `;
    }

    _renderCatalogList() {
        if (typeof this._catalogError === 'string' && this._catalogError.length > 0) {
            return html`
                <div class="mcp-error-panel" role="alert">
                    <div>${this.t('mcp_servers_modal.catalog_load_error', { message: this._catalogError })}</div>
                    <platform-button variant="primary" density="compact" @click=${() => { void this._loadCatalog({ reset: true }); }}>
                        ${this.t('mcp_servers_modal.action_retry')}
                    </platform-button>
                </div>
            `;
        }
        if (this._catalogLoading && this._catalogItems.length === 0) {
            return html`<div class="mcp-empty"><glass-spinner></glass-spinner></div>`;
        }
        if (this._catalogItems.length === 0) {
            const msg = this._search.trim().length > 0
                ? this.t('mcp_servers_modal.catalog_empty_search')
                : this.t('mcp_servers_modal.catalog_empty');
            return html`<div class="mcp-empty">${msg}</div>`;
        }
        return html`
        ${this._catalogItems.map((entry) => {
            const catalogId = typeof entry.catalog_id === 'string' ? entry.catalog_id : '';
            const title = typeof entry.title === 'string' ? entry.title : catalogId;
            const installed = entry.installed === true;
            const platformCurated = entry.platform_curated === true;
            const toolCount = typeof entry.tool_count_snapshot === 'number' ? entry.tool_count_snapshot : 0;
            const installing = this._catalogInstallingId === catalogId;
            return html`
                <div class="mcp-card mcp-card-shell">
                    <div class="mcp-card-top">
                        <div class="mcp-card-head-row">
                            <div class="mcp-card-icon glass-subtle">${renderMcpServerIcon(entry, 28)}</div>
                            <div class="mcp-card-titles">
                                <h3>${title}</h3>
                                <div class="sub"><code>${catalogId}</code></div>
                            </div>
                        </div>
                        <div class="mcp-card-actions">
                            ${installed
                                ? html`
                                    <span class="mcp-chip">${this.t('mcp_servers_modal.catalog_installed')}</span>
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="dense"
                                        danger
                                        @click=${() => { void this._uninstallCatalogEntry(entry); }}
                                        title=${this.t('mcp_servers_modal.catalog_uninstall')}
                                        aria-label=${this.t('mcp_servers_modal.catalog_uninstall')}
                                    >
                                        <platform-icon name="trash" size="16"></platform-icon>
                                    </platform-button>
                                `
                                : html`
                                    <platform-button
                                        variant="primary"
                                        density="compact"
                                        ?disabled=${installing || this._catalogInstallOp.busy}
                                        @click=${() => { void this._installCatalogEntry(entry); }}
                                    >
                                        ${installing
                                            ? html`<glass-spinner size="sm"></glass-spinner>`
                                            : this.t('mcp_servers_modal.catalog_install')}
                                    </platform-button>
                                `}
                        </div>
                    </div>
                    <div class="mcp-card-url">${typeof entry.upstream_url === 'string' ? entry.upstream_url : ''}</div>
                    <div class="mcp-card-meta">
                        <span class="mcp-chip">${this._transportLabel(entry.transport_type)}</span>
                        ${platformCurated
                            ? html`<span class="mcp-chip">${this.t('mcp_servers_modal.platform_curated')}</span>`
                            : html``}
                        <span>${this.t('mcp_servers_modal.catalog_tools_count', { n: toolCount })}</span>
                    </div>
                    ${typeof entry.description === 'string' && entry.description.length > 0
                        ? html`<div class="mcp-headers-line">${entry.description}</div>`
                        : ''}
                </div>
            `;
        })}
        ${this._catalogItems.length < this._catalogTotal
            ? this._renderLoadMore(() => this._loadCatalog(), this._catalogLoading)
            : html``}
        `;
    }

    _renderListTabs() {
        const catalogLabel = this._catalogTotal > 0
            ? this.t('mcp_servers_modal.tab_catalog_count', { n: this._catalogTotal })
            : this.t('mcp_servers_modal.tab_catalog');
        const installedLabel = this._installedTotal > 0
            ? this.t('mcp_servers_modal.tab_installed_count', { n: this._installedTotal })
            : this.t('mcp_servers_modal.tab_installed');
        return html`
            <platform-segmented-control
                class="mcp-list-tabs"
                full-width
                density="compact"
                .value=${this._listTab}
                .items=${[
                    { value: 'installed', label: installedLabel },
                    { value: 'catalog', label: catalogLabel },
                ]}
                aria-label=${this.t('mcp_servers_modal.tabs_aria')}
                @change=${(e) => { void this._switchListTab(e.detail.value); }}
            ></platform-segmented-control>
        `;
    }

    _renderLoadMore(handler, loading) {
        return html`
            <div class="mcp-load-more">
                <platform-button variant="ghost" density="compact" ?disabled=${loading} @click=${() => { void handler(); }}>
                    ${loading ? html`<glass-spinner size="sm"></glass-spinner>` : this.t('mcp_servers_modal.load_more')}
                </platform-button>
            </div>
        `;
    }

    _renderListView() {
        const brandingBtn = this._isSystemCompany()
            ? html`
                <platform-button variant="ghost" density="compact" @click=${() => { void this._goBranding(); }}>
                    ${this.t('mcp_servers_modal.branding_title')}
                </platform-button>
            `
            : html``;
        const listContent = this._listTab === 'catalog' ? this._renderCatalogList() : this._renderList();
        return html`
            <div class="mcp-list-toolbar">
                ${this._renderListTabs()}
                ${brandingBtn}
            </div>
            <div class="mcp-cards ${this._isFullscreen ? 'is-fullscreen' : ''}">${listContent}</div>
        `;
    }

    _renderBrandingView() {
        if (this._brandingLoading && this._brandingItems.length === 0) {
            return html`<div class="mcp-empty"><glass-spinner></glass-spinner></div>`;
        }
        const slugSuggestions = this._brandingSlugSuggestions;
        const selectedPreview = this._brandingItems.find((row) => row.server_id === this._brandingForm.server_id);
        const emptyKey = this._brandingSearch.trim().length > 0
            ? 'mcp_servers_modal.branding_empty_search'
            : 'mcp_servers_modal.branding_empty';
        return html`
            <div class="mcp-branding-layout">
                <section class="mcp-branding-composer mcp-card-shell mcp-branding-form">
                    <div class="mcp-field">
                        <label>${this.t('mcp_servers_modal.branding_slug')}</label>
                        <platform-field
                            type="string"
                            mode="edit"
                            .value=${this._brandingForm.server_id}
                            placeholder=${this.t('mcp_servers_modal.placeholder_id')}
                            @change=${(e) => {
                                const v = e.detail.value;
                                if (typeof v !== 'string') {
                                    throw new TypeError('flows-mcp-servers-modal: branding server_id expects string');
                                }
                                this._setBrandingSlug(v);
                            }}
                        ></platform-field>
                    </div>
                    ${slugSuggestions.length > 0
                        ? html`
                            <div class="mcp-branding-slugs" aria-label=${this.t('mcp_servers_modal.branding_slug_suggest_aria')}>
                                ${repeat(
                                    slugSuggestions,
                                    (slug) => slug,
                                    (slug) => html`
                                        <platform-button
                                            variant="ghost"
                                            density="compact"
                                            @click=${() => this._applyBrandingSlug(slug)}
                                        ><code>${slug}</code></platform-button>
                                    `,
                                )}
                            </div>
                        `
                        : html``}
                    <div class="mcp-branding-preview mcp-card-shell">
                        <div class="mcp-branding-preview-icon">
                            ${selectedPreview ? renderMcpServerIcon(selectedPreview, 48) : html`<platform-icon name="image" size="28"></platform-icon>`}
                        </div>
                        <div class="mcp-branding-preview-text">
                            ${selectedPreview
                                ? this.t('mcp_servers_modal.branding_edit_hint')
                                : this.t('mcp_servers_modal.branding_preview_hint')}
                        </div>
                    </div>
                    <div class="mcp-field">
                        <label>${this.t('mcp_servers_modal.branding_upload')}</label>
                        <platform-file-attachments
                            .files=${this._brandingUploadFiles}
                            upload-op-name="platform/file_create"
                            .uploadSpec=${this._brandingUploadSpec()}
                            @files-change=${(e) => this._onBrandingFilesChange(e)}
                        ></platform-file-attachments>
                    </div>
                    ${this._brandingError
                        ? html`<div class="mcp-form-err" role="alert">${this._brandingError}</div>`
                        : html``}
                    <platform-button
                        variant="primary"
                        ?disabled=${!this._brandingCanSave() || this._brandingSaving || this._brandingUpsertOp.busy}
                        @click=${() => { void this._saveBranding(); }}
                    >
                        ${this.t('mcp_servers_modal.branding_add')}
                    </platform-button>
                </section>
                <section class="mcp-branding-gallery" aria-label=${this.t('mcp_servers_modal.branding_gallery_aria')}>
                    ${this._brandingItems.length === 0
                        ? html`<div class="mcp-empty">${this.t(emptyKey)}</div>`
                        : html`
                            <div class="mcp-branding-grid">
                                ${repeat(
                                    this._brandingItems,
                                    (row) => (typeof row.server_id === 'string' ? row.server_id : ''),
                                    (row) => html`
                                        <article
                                            class="mcp-branding-card mcp-card-shell"
                                            role="button"
                                            tabindex="0"
                                            aria-selected=${this._brandingEditingSlug === row.server_id ? 'true' : 'false'}
                                            @click=${() => this._editBranding(row)}
                                            @keydown=${(e) => {
                                                if (e.key === 'Enter' || e.key === ' ') {
                                                    e.preventDefault();
                                                    this._editBranding(row);
                                                }
                                            }}
                                        >
                                            <div class="mcp-branding-card-delete">
                                                <platform-button
                                                    variant="ghost"
                                                    icon-only
                                                    density="dense"
                                                    danger
                                                    title=${this.t('mcp_servers_modal.action_delete_aria')}
                                                    aria-label=${this.t('mcp_servers_modal.action_delete_aria')}
                                                    @click=${(e) => { e.stopPropagation(); void this._deleteBranding(row.server_id); }}
                                                >
                                                    <platform-icon name="trash" size="16"></platform-icon>
                                                </platform-button>
                                            </div>
                                            <div class="mcp-branding-card-icon">
                                                ${renderMcpServerIcon(row, 40)}
                                            </div>
                                            <code class="mcp-branding-card-title">${row.server_id}</code>
                                            <span class="mcp-branding-card-hint">${this.t('mcp_servers_modal.branding_card_edit')}</span>
                                        </article>
                                    `,
                                )}
                            </div>
                        `}
                    ${this._brandingItems.length < this._brandingTotal
                        ? this._renderLoadMore(() => this._loadBranding(), this._brandingLoading)
                        : html``}
                </section>
            </div>
        `;
    }

    _renderForm() {
        const f = this._form;
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        const phId = isEdit ? '' : this.t('mcp_servers_modal.placeholder_id');
        const phName = isEdit ? '' : this.t('mcp_servers_modal.placeholder_name');
        const phUrl = isEdit ? '' : this.t('mcp_servers_modal.placeholder_url');
        const phDesc = isEdit ? '' : this.t('mcp_servers_modal.placeholder_description');
        const phHeaders = isEdit ? '' : this.t('mcp_servers_modal.placeholder_headers');
        const transportEnumConfig = {
            values: TRANSPORT_TYPES.map((t) => ({
                value: t,
                label: this._transportLabel(t),
            })),
        };
        return html`
            <div class="mcp-form">
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_id')}</label>
                    <span class="hint">${this.t('mcp_servers_modal.hint_id')}</span>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${f.server_id}
                        placeholder=${phId}
                        ?disabled=${isEdit}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: server_id expects string detail.value');
                            }
                            this._form = { ...this._form, server_id: v };
                        }}
                    ></platform-field>
                </div>
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_name')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${f.name}
                        placeholder=${phName}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: name expects string detail.value');
                            }
                            this._form = { ...this._form, name: v };
                        }}
                    ></platform-field>
                </div>
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_url')}</label>
                    <span class="hint">${this.t('mcp_servers_modal.hint_url')}</span>
                    <platform-field
                        type="string"
                        mode="edit"
                        input-type="url"
                        .value=${f.url}
                        placeholder=${phUrl}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: url expects string detail.value');
                            }
                            this._form = { ...this._form, url: v };
                        }}
                    ></platform-field>
                </div>
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_transport')}</label>
                    <span class="hint">${this.t('mcp_servers_modal.hint_transport')}</span>
                    <platform-field
                        type="enum"
                        mode="edit"
                        .value=${f.transport_type}
                        .config=${transportEnumConfig}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: transport_type expects string detail.value');
                            }
                            this._form = { ...this._form, transport_type: v };
                        }}
                    ></platform-field>
                </div>
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_description')}</label>
                    <platform-field
                        type="string"
                        mode="edit"
                        .value=${f.description}
                        placeholder=${phDesc}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: description expects string detail.value');
                            }
                            this._form = { ...this._form, description: v };
                        }}
                    ></platform-field>
                </div>
                <div class="mcp-field">
                    <label>${this.t('mcp_servers_modal.label_headers')}</label>
                    <span class="hint">${this.t('mcp_servers_modal.hint_headers')}</span>
                    <div class="mcp-header-presets">
                        ${repeat(
                            HEADER_PRESET_OPTIONS,
                            (preset) => preset.id,
                            (preset) => html`
                                <platform-picker-card
                                    title=${this.t(preset.titleKey)}
                                    value=${preset.id}
                                    @select=${(e) => {
                                        const presetId = e.detail.value;
                                        if (typeof presetId !== 'string') {
                                            throw new TypeError('flows-mcp-servers-modal: header preset value must be string');
                                        }
                                        this._applyPreset(presetId);
                                    }}
                                >
                                    <div slot="icon">
                                        <platform-icon name=${preset.icon} size="22"></platform-icon>
                                    </div>
                                </platform-picker-card>
                            `,
                        )}
                    </div>
                    <platform-field
                        type="text"
                        mode="edit"
                        .value=${f.headers_json}
                        placeholder=${phHeaders}
                        @change=${(e) => {
                            const v = e.detail.value;
                            if (typeof v !== 'string') {
                                throw new TypeError('flows-mcp-servers-modal: headers_json expects string detail.value');
                            }
                            this._form = { ...this._form, headers_json: v };
                            this._formError = null;
                        }}
                    ></platform-field>
                </div>
                ${this._formError
                    ? html`<div class="mcp-form-err" role="alert">${this._formError}</div>`
                    : ''}
                ${typeof this._editing === 'string' && this._editing.length > 0
                    ? this._renderTestFeedback(this._editing)
                    : ''}
            </div>
        `;
    }

    renderHeader() {
        if (this._view === 'form') {
            return typeof this._editing === 'string' && this._editing.length > 0
                ? this.t('mcp_servers_modal.title_form_edit')
                : this.t('mcp_servers_modal.title_form_add');
        }
        if (this._view === 'branding') {
            return html`
                <div class="mcp-title-row">
                    <span class="mcp-title-text">${this.t('mcp_servers_modal.branding_title')}</span>
                    ${this._renderHeaderSearch()}
                </div>
            `;
        }
        return html`
            <div class="mcp-title-row">
                <span class="mcp-title-text">${this.t('mcp_servers_modal.title')}</span>
                ${this._renderHeaderSearch()}
            </div>
        `;
    }

    renderHeaderActions() {
        if (this._view === 'list') {
            const addLabel = this.t('mcp_servers_modal.action_add');
            const showAdd = this._listTab === 'installed';
            return html`
                ${showAdd
                    ? html`
                        <platform-button
                            variant="primary"
                            icon-only
                            density="dense"
                            aria-label=${addLabel}
                            @click=${() => this._goAdd()}
                        >
                            <platform-icon name="plus" size="16"></platform-icon>
                        </platform-button>
                    `
                    : ''}
            `;
        }
        if (this._view === 'branding') {
            return html`
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    @click=${() => this._goList()}
                    title=${this.t('mcp_servers_modal.action_back_aria')}
                    aria-label=${this.t('mcp_servers_modal.action_back_aria')}
                >
                    <platform-icon name="chevron-left" size="16"></platform-icon>
                </platform-button>
            `;
        }
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                @click=${() => this._goList()}
                title=${this.t('mcp_servers_modal.action_back_aria')}
                aria-label=${this.t('mcp_servers_modal.action_back_aria')}
            >
                <platform-icon name="chevron-left" size="16"></platform-icon>
            </platform-button>
            ${isEdit
                ? html`
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        @click=${() => this._testFromForm()}
                        ?disabled=${this._testOp.busy}
                        title=${this.t('mcp_servers_modal.action_test_aria')}
                        aria-label=${this.t('mcp_servers_modal.action_test_connection')}
                    >
                        ${this._testOp.busy
                            ? html`<glass-spinner size="sm"></glass-spinner>`
                            : html`<platform-icon name="check" size="16"></platform-icon>`}
                    </platform-button>
                `
                : ''}
        `;
    }

    renderFooter() {
        if (this._view !== 'form') {
            return html``;
        }
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        const saveLabel = isEdit
            ? this.t('common.action_save')
            : this.t('mcp_servers_modal.action_add');
        const disabled = !this._formCanSave() || this._saving || this._update.busy;
        return html`
            <platform-button ?disabled=${this._saving} @click=${() => this._goList()}>${this.t('common.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${disabled} @click=${() => { this._save(); }}>
                ${saveLabel}
            </platform-button>
        `;
    }

    renderSaveHeaderButton() {
        if (this._view !== 'form') {
            return html``;
        }
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        const saveLabel = isEdit
            ? this.t('common.action_save')
            : this.t('mcp_servers_modal.action_add');
        const disabled = !this._formCanSave() || this._saving || this._update.busy;
        return this._renderHeaderSaveIcon({
            onClick: () => { this._save(); },
            disabled,
            title: saveLabel,
        });
    }

    renderBody() {
        if (this._view === 'form') {
            return this._renderForm();
        }
        if (this._view === 'branding') {
            return this._renderBrandingView();
        }
        return this._renderListView();
    }
}

customElements.define('flows-mcp-servers-modal', FlowsMcpServersModal);
registerModalKind(FlowsMcpServersModal.modalKind, 'flows-mcp-servers-modal');
