/**
 * Интеграции внешних сервисов для namespace (маршрут отдельно от карточки пространства).
 *
 * Маршрут: `/crm/namespaces/:itemId/integrations` (parent: `namespace`).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-cron-field.js';
import '@platform/lib/components/platform-timezone-picker.js';
import '@platform/lib/components/fields/platform-field.js';
import { CRM_TASK_UPDATED } from '../events/types.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const PROVIDER_AMOCRM = 'amocrm';

const INTEGRATION_TASK_TERMINAL = new Set(['completed', 'failed', 'cancelled', 'rolled_back']);
const INTEGRATION_TASK_WAIT_MS = 600_000;

function amoSubdomainFromCrmSettings(cs: unknown): string {
    if (!isPlainRecord(cs) || !isPlainRecord(cs.integrations)) {
        return '';
    }
    const amo = cs.integrations.amocrm;
    if (!isPlainRecord(amo)) {
        return '';
    }
    return typeof amo.subdomain === 'string' ? amo.subdomain : '';
}

function taskIdOf(value: unknown, label: string): string {
    if (!isPlainRecord(value) || typeof value.task_id !== 'string' || value.task_id.length === 0) {
        throw new Error(label);
    }
    return value.task_id;
}

export class CRMNamespaceIntegrationsPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        itemId: { type: String },
        _subdomainDraft: { state: true },
        _manifestItems: { state: true },
        _manifestLoading: { state: true },
        _amoUnifiedSyncBusy: { state: true },
        _autoSyncEnabled: { state: true },
        _autoSyncCron: { state: true },
        _autoSyncTimezone: { state: true },
        _autoNoteAiAnalyze: { state: true },
    };
    declare itemId: string;
    declare _subdomainDraft: unknown;
    declare _manifestItems: unknown;
    declare _manifestLoading: unknown;
    declare _amoUnifiedSyncBusy: unknown;
    declare _autoSyncEnabled: unknown;
    declare _autoSyncCron: unknown;
    declare _autoSyncTimezone: unknown;
    declare _autoNoteAiAnalyze: unknown;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }
            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .header-wrap { flex-shrink: 0; padding: 0 var(--space-4); }
            .scroll {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-2) var(--space-4) var(--space-4);
            }
            .panel {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-4);
                max-width: 520px;
            }
            .panel-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: 600;
                margin-bottom: var(--space-3);
            }
            .field { margin-bottom: var(--space-3); }
            .field-label {
                display: block;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
            }
            .field platform-field {
                display: block;
                width: 100%;
                box-sizing: border-box;
                min-width: 0;
            }
            platform-cron-field,
            platform-timezone-picker {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }
            .hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin: 0;
            }
            .actions-row-main {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                align-items: stretch;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            .actions-row-main .btn {
                flex: 1;
                min-width: 0;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .btn-primary {
                background: var(--accent);
                color: var(--text-on-accent, #fff);
                border-color: transparent;
            }
            .btn-soft {
                background: var(--glass-tint-medium);
                color: var(--text-secondary);
                border-color: transparent;
            }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .center {
                display: flex;
                justify-content: center;
                padding: var(--space-6);
            }
            .status {
                font-size: var(--text-sm);
                margin-bottom: var(--space-2);
            }
            .status-ok { color: var(--color-success, #22c55e); }
            .status-off { color: var(--text-tertiary); }
            .callback-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            .callback-url {
                flex: 1;
                min-width: 0;
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                word-break: break-all;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
            .auto-sync-section {
                margin-top: var(--space-4);
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .auto-sync-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
        `,
    ];

    private _namespaces: ResourceController;
    private _listOp: OpController;
    private _integrationAuthOp: OpController;
    private _integrationEntitiesSyncOp: OpController;
    private _integrationCustomFieldsSyncOp: OpController;
    private _integrationAutoSyncOp: OpController;
    private _integrationAutoNoteAiOp: OpController;
    private _taskGetOp: OpController;
    private _lastLoadedId: string;

    constructor() {
        super();
        this.itemId = '';
        this._subdomainDraft = '';
        this._manifestItems = [];
        this._manifestLoading = true;
        this._amoUnifiedSyncBusy = false;
        this._lastLoadedId = '';
        this._autoSyncEnabled = false;
        this._autoSyncCron = '0 * * * *';
        this._autoSyncTimezone = 'UTC';
        this._autoNoteAiAnalyze = false;

        this._namespaces = this.useResource('crm/namespaces');
        this._listOp = this.useOp('crm/namespace_integrations_list');
        this._integrationAuthOp = this.useOp('crm/namespace_integration_authorize');
        this._integrationEntitiesSyncOp = this.useOp('crm/namespace_integration_entities_sync');
        this._integrationCustomFieldsSyncOp = this.useOp('crm/namespace_integration_custom_fields_sync');
        this._integrationAutoSyncOp = this.useOp('crm/namespace_integration_auto_sync');
        this._integrationAutoNoteAiOp = this.useOp('crm/namespace_integration_auto_note_ai');
        this._taskGetOp = this.useOp('crm/task_get');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent('crm/namespace_integration_entities_sync/failed', (ev) => {
            const payload = ev.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('CRMNamespaceIntegrationsPage: sync failed payload required');
            }
            if (payload.code === 'conflict') {
                this.toast('integrations_page.amocrm_sync_active_conflict', { type: 'warning' });
                return;
            }
            if (typeof payload.message !== 'string') {
                throw new Error('CRMNamespaceIntegrationsPage: sync failed message required');
            }
            this.toast('integrations_page.amocrm_sync_task_failed', {
                type: 'error',
                vars: { message: payload.message },
            });
        });
        this.useEvent('crm/namespace_integration_custom_fields_sync/failed', (ev) => {
            const payload = ev.payload;
            if (!isPlainRecord(payload)) {
                throw new Error('CRMNamespaceIntegrationsPage: fields sync failed payload required');
            }
            if (payload.code === 'conflict') {
                this.toast('integrations_page.amocrm_fields_active_conflict', { type: 'warning' });
                return;
            }
            if (typeof payload.message !== 'string') {
                throw new Error('CRMNamespaceIntegrationsPage: fields sync failed message required');
            }
            this.toast('integrations_page.amocrm_fields_task_failed', {
                type: 'error',
                vars: { message: payload.message },
            });
        });
        this.useEvent(this._listOp.op.events.SUCCEEDED, (event) => {
            this._manifestLoading = false;
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const result = payload !== null && isPlainRecord(payload.result) ? payload.result : null;
            if (result === null || !Array.isArray(result.items)) {
                throw new Error('CRMNamespaceIntegrationsPage: integrations items required');
            }
            const rows: Record<string, unknown>[] = [];
            for (const row of result.items) {
                if (!isPlainRecord(row)) {
                    throw new Error('CRMNamespaceIntegrationsPage: integration row must be an object');
                }
                rows.push(row);
            }
            this._manifestItems = rows;
            const amo = rows.find((row) => row.provider_id === PROVIDER_AMOCRM);
            this._applyAutoSyncFieldsFromManifestRow(amo === undefined ? null : amo);
        });
        this.useEvent(this._listOp.op.events.FAILED, () => {
            this._manifestLoading = false;
            throw new Error('CRMNamespaceIntegrationsPage: integrations list failed');
        });
        this.useEvent(this._integrationAutoNoteAiOp.op.events.FAILED, () => {
            this._listOp.run({ namespace_name: this.itemId });
        });
        this.useEvent(this._namespaces.resource.events.ITEM_LOADED, (event) => {
            const p = isPlainRecord(event.payload) ? event.payload : null;
            const item = p !== null && isPlainRecord(p.item) ? p.item : null;
            if (!item || item.name !== this.itemId) return;
            this._subdomainDraft = amoSubdomainFromCrmSettings(item.crm_settings);
        });
        this.useEvent(this._namespaces.resource.events.LIST_LOADED, () => {
            const item = this._namespaces.byId[this.itemId];
            if (item !== undefined) {
                this._subdomainDraft = amoSubdomainFromCrmSettings(item.crm_settings);
            }
        });
    }

    override willUpdate(changed: PropertyValues<this>): void {
        if (!changed.has('itemId')) return;
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) return;
        if (this._lastLoadedId === this.itemId) return;
        this._lastLoadedId = this.itemId;
        this._manifestLoading = true;
        this._autoSyncEnabled = false;
        this._autoSyncCron = '0 * * * *';
        this._autoSyncTimezone = 'UTC';
        this._autoNoteAiAnalyze = false;
        this._namespaces.get(this.itemId);
        this._listOp.run({ namespace_name: this.itemId });
    }

    _applyAutoSyncFieldsFromManifestRow(row: Record<string, unknown> | null) {
        if (row === null) {
            return;
        }
        if (typeof row.auto_sync_enabled === 'boolean') {
            this._autoSyncEnabled = row.auto_sync_enabled;
        }
        if (typeof row.auto_sync_cron === 'string' && row.auto_sync_cron.length > 0) {
            this._autoSyncCron = row.auto_sync_cron;
        }
        if (typeof row.auto_sync_timezone === 'string' && row.auto_sync_timezone.length > 0) {
            this._autoSyncTimezone = row.auto_sync_timezone;
        }
        if (typeof row.auto_note_ai_analyze === 'boolean') {
            this._autoNoteAiAnalyze = row.auto_note_ai_analyze;
        }
    }

    _namespace() {
        const item = this._namespaces.byId[this.itemId];
        return item === undefined ? null : item;
    }

    _amoManifestRow() {
        const items = this._manifestItems;
        if (!Array.isArray(items)) {
            throw new Error('CRMNamespaceIntegrationsPage: _manifestItems must be array');
        }
        const found = items.find((row) => row && row.provider_id === PROVIDER_AMOCRM);
        return found !== undefined ? found : null;
    }

    _onSubdomainChange(e: CustomEvent) {
        this._subdomainDraft = typeof e.detail.value === 'string' ? e.detail.value : '';
    }

    _amocrmOauthCallbackUrl() {
        if (
            typeof globalThis === 'undefined'
            || globalThis.location === undefined
            || typeof globalThis.location.origin !== 'string'
            || globalThis.location.origin.length === 0
        ) {
            throw new Error('amocrm oauth callback: нет location.origin');
        }
        return `${globalThis.location.origin}/crm/api/v1/integrations/oauth/callback`;
    }

    _onCopyAmocrmOAuthCallback() {
        this.copyToClipboard(this._amocrmOauthCallbackUrl(), {
            success_i18n_key: 'integrations_page.amocrm_oauth_callback_toast_ok',
            error_i18n_key: 'integrations_page.amocrm_oauth_callback_toast_err',
        });
    }

    async _onAmoConnect() {
        const sub = typeof this._subdomainDraft === 'string' ? this._subdomainDraft.trim() : '';
        if (sub.length === 0) {
            this.toast('namespace_detail_page.amocrm_subdomain_required', { type: 'error' });
            throw new Error('CRMNamespaceIntegrationsPage: subdomain required');
        }
        if (
            typeof globalThis === 'undefined'
            || globalThis.location === undefined
            || typeof globalThis.location.origin !== 'string'
            || globalThis.location.origin.length === 0
            || typeof globalThis.location.host !== 'string'
            || globalThis.location.host.length === 0
        ) {
            throw new Error('CRMNamespaceIntegrationsPage: location.origin/host required');
        }
        const returnPath = `/crm/namespaces/${encodeURIComponent(this.itemId)}/integrations`;
        const result = await this._integrationAuthOp.run({
            namespace_name: this.itemId,
            provider_id: PROVIDER_AMOCRM,
            subdomain: sub,
            return_path: returnPath,
            return_origin: globalThis.location.origin,
            brand_host: globalThis.location.host,
        });
        if (!isPlainRecord(result) || typeof result.authorize_url !== 'string' || result.authorize_url.length === 0) {
            throw new Error('CRMNamespaceIntegrationsPage: authorize_url required');
        }
        window.location.assign(result.authorize_url);
    }

    async _waitCrmTaskOutcome(taskId: string): Promise<{ ok: boolean; status: string; error_message: string }> {
        const seeded = await this._taskGetOp.run({ task_id: taskId });
        if (seeded !== null) {
            if (!isPlainRecord(seeded) || typeof seeded.status !== 'string') {
                throw new Error('crm task wait: status missing');
            }
            if (INTEGRATION_TASK_TERMINAL.has(seeded.status)) {
                if (seeded.status === 'completed') {
                    return { ok: true, status: 'completed', error_message: '' };
                }
                const msg = typeof seeded.error_message === 'string' ? seeded.error_message : '';
                return { ok: false, status: seeded.status, error_message: msg };
            }
        }
        return new Promise((resolve) => {
            let settled = false;
            const finish = (outcome: { ok: boolean; status: string; error_message: string }) => {
                if (settled) {
                    return;
                }
                settled = true;
                window.clearTimeout(timerId);
                unsub();
                resolve(outcome);
            };
            const onUpdated = (event: PlatformEvent) => {
                const payload = isPlainRecord(event.payload) ? event.payload : null;
                const task = payload !== null && isPlainRecord(payload.task) ? payload.task : null;
                if (task === null || task.task_id !== taskId) {
                    return;
                }
                if (typeof task.status !== 'string' || !INTEGRATION_TASK_TERMINAL.has(task.status)) {
                    return;
                }
                if (task.status === 'completed') {
                    finish({ ok: true, status: 'completed', error_message: '' });
                    return;
                }
                const msg = typeof task.error_message === 'string' ? task.error_message : '';
                finish({ ok: false, status: task.status, error_message: msg });
            };
            const unsub = this.useEvent(CRM_TASK_UPDATED, onUpdated);
            const timerId = window.setTimeout(() => {
                finish({ ok: false, status: 'timeout', error_message: '' });
            }, INTEGRATION_TASK_WAIT_MS);
        });
    }

    _toastTaskFailure(failedKey: string, outcome: { ok: boolean; status: string; error_message: string }) {
        if (outcome.status === 'timeout') {
            this.toast('integrations_page.amocrm_task_poll_timeout', { type: 'warning' });
            return;
        }
        this.toast(failedKey, { type: 'error', vars: { message: outcome.error_message } });
    }

    _onAutoSyncSwitch(e: CustomEvent) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'boolean') {
            throw new Error('auto-sync switch: ожидался detail.value (boolean)');
        }
        this._autoSyncEnabled = d.value;
    }

    _onAutoCronInput(e: CustomEvent) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'string') {
            throw new Error('auto-sync cron: expected detail.value (string)');
        }
        this._autoSyncCron = d.value;
    }

    _onAutoTzInput(e: CustomEvent) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'string') {
            throw new Error('auto-sync timezone: expected detail.value (string)');
        }
        this._autoSyncTimezone = d.value;
    }

    async _onSaveAutoSync() {
        const cronRaw = typeof this._autoSyncCron === 'string' ? this._autoSyncCron.trim() : '';
        const tzRaw = typeof this._autoSyncTimezone === 'string' ? this._autoSyncTimezone.trim() : '';
        if (this._autoSyncEnabled && cronRaw.length === 0) {
            this.toast('integrations_page.auto_sync_cron_required', { type: 'error' });
            throw new Error('CRMNamespaceIntegrationsPage: auto_sync_cron required');
        }
        if (this._autoSyncEnabled && tzRaw.length === 0) {
            throw new Error('CRMNamespaceIntegrationsPage: auto_sync_timezone required');
        }
        await this._integrationAutoSyncOp.run({
            namespace_name: this.itemId,
            provider_id: PROVIDER_AMOCRM,
            auto_sync_enabled: this._autoSyncEnabled,
            auto_sync_cron: this._autoSyncEnabled ? cronRaw : null,
            auto_sync_timezone: tzRaw.length > 0 ? tzRaw : null,
        });
        this._namespaces.get(this.itemId);
        this._listOp.run({ namespace_name: this.itemId });
    }

    async _onAutoNoteAiSwitch(e: CustomEvent<{ value?: unknown }>) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'boolean') {
            throw new Error('auto note ai: expected detail.value (boolean)');
        }
        await this._integrationAutoNoteAiOp.run({
            namespace_name: this.itemId,
            provider_id: PROVIDER_AMOCRM,
            auto_note_ai_analyze: d.value,
        });
        this._namespaces.get(this.itemId);
        this._listOp.run({ namespace_name: this.itemId });
    }

    async _onAmoUnifiedSync() {
        if (this._amoUnifiedSyncBusy) return;
        this._amoUnifiedSyncBusy = true;
        try {
            const entitiesStarted = await this._integrationEntitiesSyncOp.run({
                namespace_name: this.itemId,
                provider_id: PROVIDER_AMOCRM,
            });
            if (entitiesStarted === null) return;
            const entitiesTaskId = taskIdOf(entitiesStarted, 'amocrm sync: task_id missing in response');
            this.toast('integrations_page.amocrm_unified_sync_started', { type: 'success' });
            this._listOp.run({ namespace_name: this.itemId });
            const entitiesOutcome = await this._waitCrmTaskOutcome(entitiesTaskId);
            if (!entitiesOutcome.ok) {
                this._toastTaskFailure('integrations_page.amocrm_sync_task_failed', entitiesOutcome);
                return;
            }
            const fieldsStarted = await this._integrationCustomFieldsSyncOp.run({
                namespace_name: this.itemId,
                provider_id: PROVIDER_AMOCRM,
            });
            if (fieldsStarted === null) return;
            const fieldsTaskId = taskIdOf(fieldsStarted, 'amocrm fields: task_id missing in response');
            this._listOp.run({ namespace_name: this.itemId });
            const fieldsOutcome = await this._waitCrmTaskOutcome(fieldsTaskId);
            if (!fieldsOutcome.ok) {
                this._toastTaskFailure('integrations_page.amocrm_fields_task_failed', fieldsOutcome);
                return;
            }
            this.toast('integrations_page.amocrm_unified_sync_done', { type: 'success' });
        } finally {
            this._amoUnifiedSyncBusy = false;
        }
    }

    override render(): TemplateResult {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return html`
                <div class="center">
                    <p>${this.t('namespace_detail_page.no_id')}</p>
                </div>
            `;
        }
        const ns = this._namespace();
        if (ns === null) {
            return html`<div class="center"><platform-spinner size="lg"></platform-spinner></div>`;
        }

        const amoRow = this._amoManifestRow();
        const connected = amoRow && amoRow.connected === true;
        const namespaceName = ns.name;
        const namespaceLabel = namespaceName === undefined || namespaceName === null ? '' : String(namespaceName);

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${this.t('integrations_page.breadcrumb_tail')}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${this.t('integrations_page.title')}
                    subtitle=${this.t('integrations_page.subtitle', { name: namespaceLabel })}
                ></page-header>
                <p class="hint" style="padding: 0 var(--space-4); margin-top: var(--space-1);">
                    ${this.t('integrations_page.scope_hint')}
                </p>
            </div>
            <div class="scroll">
                ${this._manifestLoading
                    ? html`<div class="center"><platform-spinner size="md"></platform-spinner></div>`
                    : html`
                <div class="panel">
                    <div class="panel-title">
                        <platform-icon name="link" size="18"></platform-icon>
                        ${this.t('integrations_page.provider_amocrm')}
                    </div>
                    <p class="status ${connected ? 'status-ok' : 'status-off'}">
                        ${connected
                            ? this.t('integrations_page.status_connected')
                            : this.t('integrations_page.status_disconnected')}
                    </p>
                    <div class="field">
                        <platform-field
                            type="string"
                            mode="edit"
                            input-type="text"
                            .label=${this.t('namespace_detail_page.amocrm_subdomain_label')}
                            .placeholder=${this.t('namespace_detail_page.amocrm_subdomain_placeholder')}
                            .value=${this._subdomainDraft}
                            @change=${this._onSubdomainChange}
                        ></platform-field>
                    </div>
                    <p class="hint">${this.t('integrations_page.amocrm_oauth_credentials')}</p>
                    <p class="hint">${this.t('integrations_page.amocrm_oauth_redirect')}</p>
                    <div class="callback-row">
                        <code class="callback-url">${this._amocrmOauthCallbackUrl()}</code>
                        <button
                            type="button"
                            class="btn btn-soft"
                            @click=${this._onCopyAmocrmOAuthCallback}
                        >
                            ${this.t('integrations_page.amocrm_oauth_callback_copy')}
                        </button>
                    </div>
                    <div class="actions-row-main">
                        <button
                            class="btn btn-primary"
                            type="button"
                            ?disabled=${this._integrationAuthOp.busy || this._amoUnifiedSyncBusy}
                            @click=${this._onAmoConnect}
                        >
                            ${this.t('namespace_detail_page.amocrm_connect')}
                        </button>
                        <button
                            class="btn btn-soft"
                            type="button"
                            ?disabled=${this._integrationAuthOp.busy
                                || this._amoUnifiedSyncBusy
                                || this._integrationEntitiesSyncOp.busy
                                || this._integrationCustomFieldsSyncOp.busy}
                            @click=${this._onAmoUnifiedSync}
                        >
                            ${this.t('integrations_page.amocrm_sync_unified')}
                        </button>
                    </div>
                    ${connected
                        ? html`
                    <div class="auto-sync-section">
                        <div class="panel-title">
                            <platform-icon name="clock" size="18"></platform-icon>
                            ${this.t('integrations_page.auto_sync_title')}
                        </div>
                        <p class="hint">${this.t('integrations_page.auto_sync_hint')}</p>
                        <div class="auto-sync-row">
                            <platform-switch
                                .checked=${this._autoSyncEnabled}
                                ?disabled=${this._integrationAutoSyncOp.busy}
                                label=${this.t('integrations_page.auto_sync_toggle')}
                                @change=${this._onAutoSyncSwitch}
                            ></platform-switch>
                        </div>
                        <div class="field">
                            <platform-cron-field
                                .label=${this.t('integrations_page.auto_sync_cron_label')}
                                .value=${this._autoSyncCron}
                                placeholder=${this.t('integrations_page.auto_sync_cron_placeholder')}
                                ?disabled=${this._integrationAutoSyncOp.busy}
                                @input=${this._onAutoCronInput}
                                @change=${this._onAutoCronInput}
                            ></platform-cron-field>
                            <p class="hint">${this.t('integrations_page.auto_sync_cron_help')}</p>
                        </div>
                        <div class="field">
                            <platform-timezone-picker
                                .label=${this.t('integrations_page.auto_sync_tz_label')}
                                placeholder=${this.t('integrations_page.auto_sync_tz_placeholder')}
                                .value=${this._autoSyncTimezone}
                                ?disabled=${this._integrationAutoSyncOp.busy}
                                @input=${this._onAutoTzInput}
                                @change=${this._onAutoTzInput}
                            ></platform-timezone-picker>
                            <p class="hint">${this.t('integrations_page.auto_sync_tz_help')}</p>
                        </div>
                        <button
                            class="btn btn-primary"
                            type="button"
                            ?disabled=${this._integrationAutoSyncOp.busy
                                || this._integrationAuthOp.busy
                                || this._amoUnifiedSyncBusy}
                            @click=${this._onSaveAutoSync}
                        >
                            ${this.t('integrations_page.auto_sync_save')}
                        </button>
                    </div>
                    <div class="auto-sync-section">
                        <div class="panel-title">
                            <platform-icon name="sparkle" size="18"></platform-icon>
                            ${this.t('integrations_page.auto_note_ai_title')}
                        </div>
                        <p class="hint">${this.t('integrations_page.auto_note_ai_hint')}</p>
                        <div class="auto-sync-row">
                            <platform-switch
                                .checked=${this._autoNoteAiAnalyze}
                                ?disabled=${this._integrationAutoNoteAiOp.busy
                                    || this._integrationAuthOp.busy
                                    || this._amoUnifiedSyncBusy}
                                label=${this.t('integrations_page.auto_note_ai_toggle')}
                                @change=${this._onAutoNoteAiSwitch}
                            ></platform-switch>
                        </div>
                    </div>
                        `
                        : nothing}
                </div>
                `}
            </div>
        `;
    }
}

customElements.define('crm-namespace-integrations-page', CRMNamespaceIntegrationsPage);
