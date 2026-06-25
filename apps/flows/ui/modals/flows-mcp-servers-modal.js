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
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-file-attachments.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { renderMcpServerIcon } from '../_helpers/mcp-server-icon.js';

const SERVER_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]{1,63}$/;
const TRANSPORT_TYPES = Object.freeze(['http', 'sse']);

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
const PLATFORM_MCP_SLUGS = Object.freeze(['browser', 'search']);

/**
 * @param {unknown} h
 * @returns {string}
 */
function headersObjectToJsonString(h) {
    if (!isPlainObject(h) || Object.keys(h).length === 0) {
        return '{}';
    }
    return JSON.stringify(h, null, 2);
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
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .flows-header-action-create {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 50%);
                flex-shrink: 0;
                cursor: pointer;
                color: var(--platform-btn-primary-text, #ffffff);
                background: var(--platform-btn-primary-bg, #99a6f9);
                box-shadow: var(--platform-btn-primary-shadow, none);
                transition: var(--motion-transition-interactive);
            }
            .flows-header-action-create platform-icon {
                display: flex;
            }
            .flows-header-action-create:hover:not(:disabled) {
                background: var(--platform-btn-primary-bg-hover, #8794f0);
                box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
            }
            .flows-header-action-create:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .mcp-cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                max-height: min(70vh, 640px);
                overflow-y: auto;
                padding: var(--space-1);
            }
            .mcp-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
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
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
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
            }
            .mcp-card-actions .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 32px;
                min-height: 32px;
                padding: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .mcp-card-actions .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
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
                background: var(--info-subtle, rgba(59, 130, 246, 0.12));
                color: var(--info, #3b82f6);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .mcp-chip-warn {
                background: var(--warning-subtle, rgba(245, 158, 11, 0.12));
                color: var(--warning, #f59e0b);
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
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .mcp-field textarea { min-height: 120px; font-family: var(--font-mono, ui-monospace, monospace); font-size: var(--text-sm); }
            .mcp-presets { display: flex; flex-wrap: wrap; gap: var(--space-2); }
            .mcp-preset {
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .mcp-preset:hover { color: var(--text-primary); border-color: var(--accent); }
            .mcp-form-err { font-size: var(--text-sm); color: var(--error, #ef4444); }
            .mcp-test-feedback {
                font-size: var(--text-sm);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            .mcp-test-feedback.ok {
                background: var(--success-subtle, rgba(34, 197, 94, 0.12));
                color: var(--success, #22c55e);
            }
            .mcp-test-feedback.err {
                background: var(--error-subtle, rgba(239, 68, 68, 0.12));
                color: var(--error, #ef4444);
            }
            .mcp-card-actions .icon-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
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
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
            }
            .mcp-branding-slugs {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .mcp-branding-slug {
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .mcp-branding-slug:hover {
                color: var(--text-primary);
                border-color: var(--accent);
            }
            .mcp-branding-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
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
                justify-content: flex-end;
                margin-bottom: var(--space-2);
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
        `,
    ];

    constructor() {
        super();
        this.headerSavePrimary = true;
        this.size = 'lg';
        this._saving = false;
        this._view = 'list';
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
        this._catalogSlugs = [];
        this._brandingForm = { server_id: '', icon_file_id: '' };
        this._brandingUploadFiles = [];
        this._brandingError = null;
        this._brandingSaving = false;
        this._brandingLoading = false;
        this._activeCompanySel = this.select((s) => s.auth.activeCompanyId);
        this._servers = this.useResource('flows/mcp_servers', { autoload: true });
        this._update = this.useOp('flows/mcp_server_update');
        this._syncOp = this.useOp('flows/mcp_server_sync');
        this._testOp = this.useOp('flows/mcp_server_test');
        this._resetCatalogOp = this.useOp('flows/mcp_server_reset_catalog_defaults');
        this._brandingLoadOp = this.useOp('flows/mcp_branding_load');
        this._brandingUpsertOp = this.useOp('flows/mcp_branding_upsert');
        this._brandingRemoveOp = this.useOp('flows/mcp_branding_remove');
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        if (changedProperties.has('open') && this.open) {
            this._view = 'list';
            this._editing = null;
            this._formError = null;
            this._saving = false;
            this._testFeedback = null;
            this._testingServerId = null;
            this._brandingError = null;
            this._brandingSaving = false;
            this._brandingUploadFiles = [];
            this._resetFormFields();
            this._resetBrandingFormFields();
            this.size = 'lg';
        }
    }

    _resetBrandingFormFields() {
        this._brandingForm = { server_id: '', icon_file_id: '' };
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

    async _loadBranding() {
        this._brandingLoading = true;
        try {
            const payload = await this._brandingLoadOp.run({});
            if (!isPlainObject(payload)) {
                throw new Error('flows-mcp-servers-modal: branding load invalid response');
            }
            this._brandingItems = asArray(payload.items);
            this._catalogSlugs = asArray(payload.catalog_slugs).filter((slug) => typeof slug === 'string');
        } finally {
            this._brandingLoading = false;
        }
    }

    async _goBranding() {
        this._view = 'branding';
        this._brandingError = null;
        this._resetBrandingFormFields();
        this._brandingUploadFiles = [];
        await this._loadBranding();
    }

    _brandingSlugSuggestions() {
        const seen = new Set();
        const out = [];
        for (const slug of PLATFORM_MCP_SLUGS) {
            if (!seen.has(slug)) {
                seen.add(slug);
                out.push(slug);
            }
        }
        for (const slug of this._catalogSlugs) {
            if (typeof slug === 'string' && slug.length > 0 && !seen.has(slug)) {
                seen.add(slug);
                out.push(slug);
            }
        }
        return out.slice(0, 48);
    }

    _brandingCanSave() {
        const f = this._brandingForm;
        return SERVER_ID_PATTERN.test(f.server_id) && f.icon_file_id.length > 0;
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
            await this._loadBranding();
            this._servers.load();
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
                cancelText: this.t('mcp_servers_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._brandingRemoveOp.run({ server_id: serverId });
        await this._loadBranding();
        this._servers.load();
    }

    _applyBrandingSlug(slug) {
        if (typeof slug !== 'string' || slug.length === 0) {
            return;
        }
        this._brandingForm = { ...this._brandingForm, server_id: slug };
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
            this._servers.load();
        } finally {
            this._saving = false;
        }
    }

    async _sync(s) {
        await this._syncOp.run({ server_id: s.server_id });
        this._servers.load();
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
        this._servers.load();
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
                cancelText: this.t('mcp_servers_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._resetCatalogOp.run({ server_id: s.server_id });
        this._servers.load();
    }

    async _delete(s) {
        const ok = await platformConfirm(
            this.t('mcp_servers_modal.delete_message', { id: s.server_id }),
            {
                title: this.t('mcp_servers_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('mcp_servers_modal.action_delete'),
                cancelText: this.t('mcp_servers_modal.action_cancel'),
            },
        );
        if (!ok) {
            return;
        }
        await this._servers.remove(s.server_id);
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
        const items = asArray(this._servers.items);
        if (this._servers.loading && items.length === 0) {
            return html`<div class="mcp-empty"><glass-spinner></glass-spinner></div>`;
        }
        if (items.length === 0) {
            return html`<div class="mcp-empty">${this.t('mcp_servers_modal.empty')}</div>`;
        }
        return items.map((s) => html`
            <div class="mcp-card">
                <div class="mcp-card-top">
                    <div class="mcp-card-head-row">
                        <div class="mcp-card-icon">${renderMcpServerIcon(s, 28)}</div>
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
                        <button type="button" class="icon-btn" @click=${() => this._sync(s)}
                            title=${this.t('mcp_servers_modal.action_sync_aria')}>
                            <platform-icon name="rotate-ccw" size="16"></platform-icon>
                        </button>
                        <button type="button" class="icon-btn" @click=${() => this._test(s)}
                            ?disabled=${this._testingServerId === s.server_id}
                            title=${this.t('mcp_servers_modal.action_test_aria')}>
                            ${this._testingServerId === s.server_id
                                ? html`<glass-spinner size="sm"></glass-spinner>`
                                : html`<platform-icon name="check" size="16"></platform-icon>`}
                        </button>
                        <button type="button" class="icon-btn" @click=${() => this._editServer(s)}
                            title=${this.t('mcp_servers_modal.action_edit_aria')}>
                            <platform-icon name="edit" size="16"></platform-icon>
                        </button>
                        <button type="button" class="icon-btn" @click=${() => this._delete(s)}
                            title=${this.t('mcp_servers_modal.action_delete_aria')}>
                            <platform-icon name="trash" size="16"></platform-icon>
                        </button>
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
                            <button
                                type="button"
                                class="text-action"
                                @click=${() => this._resetCatalogDefaults(s)}>
                                ${this.t('mcp_servers_modal.action_reset_defaults')}
                            </button>
                        </div>
                    `
                    : ''}
            </div>
        `);
    }

    _renderListView() {
        const brandingBtn = this._isSystemCompany()
            ? html`
                <div class="mcp-list-toolbar">
                    <button type="button" class="mcp-branding-link" @click=${() => { void this._goBranding(); }}>
                        ${this.t('mcp_servers_modal.branding_title')}
                    </button>
                </div>
            `
            : html``;
        return html`
            ${brandingBtn}
            <div class="mcp-cards">${this._renderList()}</div>
        `;
    }

    _renderBrandingView() {
        if (this._brandingLoading && this._brandingItems.length === 0) {
            return html`<div class="mcp-empty"><glass-spinner></glass-spinner></div>`;
        }
        const slugSuggestions = this._brandingSlugSuggestions();
        return html`
            <div class="mcp-branding-form">
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
                            this._brandingForm = { ...this._brandingForm, server_id: v };
                            this._brandingError = null;
                        }}
                    ></platform-field>
                </div>
                ${slugSuggestions.length > 0
                    ? html`
                        <div class="mcp-branding-slugs">
                            ${repeat(
                                slugSuggestions,
                                (slug) => slug,
                                (slug) => html`
                                    <button
                                        type="button"
                                        class="mcp-branding-slug"
                                        @click=${() => this._applyBrandingSlug(slug)}
                                    ><code>${slug}</code></button>
                                `,
                            )}
                        </div>
                    `
                    : ''}
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
                    : ''}
                <div>
                    <button
                        type="button"
                        class="mcp-preset"
                        ?disabled=${!this._brandingCanSave() || this._brandingSaving || this._brandingUpsertOp.busy}
                        @click=${() => { void this._saveBranding(); }}
                    >
                        ${this.t('mcp_servers_modal.branding_add')}
                    </button>
                </div>
            </div>
            <div class="mcp-cards">
                ${this._brandingItems.length === 0
                    ? html`<div class="mcp-empty">${this.t('mcp_servers_modal.branding_empty')}</div>`
                    : repeat(
                        this._brandingItems,
                        (row) => (typeof row.server_id === 'string' ? row.server_id : ''),
                        (row) => html`
                            <div class="mcp-branding-row">
                                <div class="mcp-branding-row-icon">
                                    ${renderMcpServerIcon(row, 32)}
                                </div>
                                <div class="mcp-branding-row-meta">
                                    <code>${row.server_id}</code>
                                </div>
                                <div class="mcp-branding-row-actions">
                                    <button
                                        type="button"
                                        class="icon-btn"
                                        title=${this.t('mcp_servers_modal.action_delete_aria')}
                                        @click=${() => { void this._deleteBranding(row.server_id); }}
                                    >
                                        <platform-icon name="trash" size="16"></platform-icon>
                                    </button>
                                </div>
                            </div>
                        `,
                    )}
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
                    <div class="mcp-presets">
                        <button type="button" class="mcp-preset" @click=${() => this._applyPreset('bearer')}>
                            ${this.t('mcp_servers_modal.preset_bearer')}
                        </button>
                        <button type="button" class="mcp-preset" @click=${() => this._applyPreset('apikey')}>
                            ${this.t('mcp_servers_modal.preset_api_key')}
                        </button>
                        <button type="button" class="mcp-preset" @click=${() => this._applyPreset('basic')}>
                            ${this.t('mcp_servers_modal.preset_basic')}
                        </button>
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
            return this.t('mcp_servers_modal.branding_title');
        }
        return this.t('mcp_servers_modal.title');
    }

    renderHeaderActions() {
        if (this._view === 'list') {
            const addLabel = this.t('mcp_servers_modal.action_add');
            return html`
                <button
                    type="button"
                    class="flows-header-action-create"
                    title=${addLabel}
                    aria-label=${addLabel}
                    @click=${() => this._goAdd()}
                >
                    <platform-icon name="plus" size="16"></platform-icon>
                </button>
            `;
        }
        if (this._view === 'branding') {
            return html`
                <button
                    type="button"
                    class="header-btn"
                    @click=${() => this._goList()}
                    title=${this.t('mcp_servers_modal.action_back_aria')}
                    aria-label=${this.t('mcp_servers_modal.action_back_aria')}
                >
                    <platform-icon name="chevron-left" size="16"></platform-icon>
                </button>
            `;
        }
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        return html`
            <button
                type="button"
                class="header-btn"
                @click=${() => this._goList()}
                title=${this.t('mcp_servers_modal.action_back_aria')}
                aria-label=${this.t('mcp_servers_modal.action_back_aria')}
            >
                <platform-icon name="chevron-left" size="16"></platform-icon>
            </button>
            ${isEdit
                ? html`
                    <button
                        type="button"
                        class="header-btn"
                        @click=${() => this._testFromForm()}
                        ?disabled=${this._testOp.busy}
                        title=${this.t('mcp_servers_modal.action_test_aria')}
                        aria-label=${this.t('mcp_servers_modal.action_test_connection')}
                    >
                        ${this._testOp.busy
                            ? html`<glass-spinner size="sm"></glass-spinner>`
                            : html`<platform-icon name="check" size="16"></platform-icon>`}
                    </button>
                `
                : ''}
        `;
    }

    renderSaveHeaderButton() {
        if (this._view !== 'form') {
            return html``;
        }
        const isEdit = typeof this._editing === 'string' && this._editing.length > 0;
        const saveLabel = isEdit
            ? this.t('mcp_servers_modal.action_save')
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
