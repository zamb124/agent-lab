/**
 * Интеграции внешних сервисов для namespace (маршрут отдельно от карточки пространства).
 *
 * Маршрут: `/crm/spaces/:itemId/integrations` (parent: `space`).
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-cron-field.js';
import '@platform/lib/components/platform-timezone-picker.js';

const PROVIDER_AMOCRM = 'amocrm';

const INTEGRATION_TASK_TERMINAL = new Set(['completed', 'failed', 'cancelled', 'rolled_back']);
const INTEGRATION_TASK_POLL_MS = 1500;
const INTEGRATION_TASK_POLL_MAX = 400;

function amoSubdomainFromCrmSettings(cs) {
    if (!cs || typeof cs.integrations !== 'object' || cs.integrations === null) {
        return '';
    }
    const amo = cs.integrations.amocrm;
    if (!amo || typeof amo !== 'object') {
        return '';
    }
    return typeof amo.subdomain === 'string' ? amo.subdomain : '';
}

export class CRMSpaceIntegrationsPage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
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

    static styles = [
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
            .input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
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
                font-family: var(--font-mono, ui-monospace, monospace);
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

    connectedCallback() {
        super.connectedCallback();
        this.useEvent('crm/namespace_integration_entities_sync/failed', (ev) => {
            const payload = ev && ev.payload;
            if (!payload || typeof payload !== 'object') return;
            const body = payload.body;
            const detail = body && body.detail;
            if (
                detail &&
                typeof detail === 'object' &&
                detail.code === 'active_task_exists'
            ) {
                this.toast('integrations_page.amocrm_sync_active_conflict', { type: 'warning' });
                return;
            }
            const msg = typeof payload.message === 'string' ? payload.message : '';
            this.toast('integrations_page.amocrm_sync_task_failed', {
                type: 'error',
                vars: { message: msg },
            });
        });
        this.useEvent('crm/namespace_integration_custom_fields_sync/failed', (ev) => {
            const payload = ev && ev.payload;
            if (!payload || typeof payload !== 'object') return;
            const body = payload.body;
            const detail = body && body.detail;
            if (
                detail &&
                typeof detail === 'object' &&
                detail.code === 'active_task_exists'
            ) {
                this.toast('integrations_page.amocrm_fields_active_conflict', { type: 'warning' });
                return;
            }
            const msg = typeof payload.message === 'string' ? payload.message : '';
            this.toast('integrations_page.amocrm_fields_task_failed', {
                type: 'error',
                vars: { message: msg },
            });
        });
        this.useEvent(this._listOp.op.events.SUCCEEDED, (event) => {
            this._manifestLoading = false;
            const payload = event && event.payload && event.payload.result;
            const items = payload && Array.isArray(payload.items) ? payload.items : [];
            this._manifestItems = items;
            const amo = items.find((row) => row && row.provider_id === PROVIDER_AMOCRM);
            this._applyAutoSyncFieldsFromManifestRow(amo !== undefined ? amo : null);
        });
        this.useEvent(this._listOp.op.events.FAILED, () => {
            this._manifestLoading = false;
            this._manifestItems = [];
        });
        this.useEvent(this._integrationAutoNoteAiOp.op.events.FAILED, () => {
            this._listOp.run({ namespace_name: this.itemId });
        });
        this.useEvent(this._namespaces.resource.events.ITEM_LOADED, (event) => {
            const item = event && event.payload && event.payload.item;
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

    willUpdate(changed) {
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

    _applyAutoSyncFieldsFromManifestRow(row) {
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
        const items = Array.isArray(this._manifestItems) ? this._manifestItems : [];
        const found = items.find((row) => row && row.provider_id === PROVIDER_AMOCRM);
        return found !== undefined ? found : null;
    }

    _onSubInput(e) {
        this._subdomainDraft = e.target.value;
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
            this.toast('space_detail_page.amocrm_subdomain_required', { type: 'error' });
            return;
        }
        const returnPath = `/crm/spaces/${encodeURIComponent(this.itemId)}/integrations`;
        const url = await this._integrationAuthOp.run({
            namespace_name: this.itemId,
            provider_id: PROVIDER_AMOCRM,
            subdomain: sub,
            return_path: returnPath,
        });
        if (typeof url === 'string' && url.length > 0) {
            window.location.assign(url);
        }
    }

    async _pollCrmTaskOutcome(taskId) {
        for (let i = 0; i < INTEGRATION_TASK_POLL_MAX; i += 1) {
            const row = await this._taskGetOp.run({ task_id: taskId });
            if (row === null) {
                return { ok: false, status: 'missing', error_message: '' };
            }
            if (typeof row.status !== 'string') {
                throw new Error('task poll: status missing');
            }
            if (INTEGRATION_TASK_TERMINAL.has(row.status)) {
                if (row.status === 'completed') {
                    return { ok: true, status: 'completed', error_message: '' };
                }
                const msg = typeof row.error_message === 'string' ? row.error_message : '';
                return { ok: false, status: row.status, error_message: msg };
            }
            await new Promise((resolve) => {
                setTimeout(resolve, INTEGRATION_TASK_POLL_MS);
            });
        }
        return { ok: false, status: 'timeout', error_message: '' };
    }

    _toastTaskFailure(failedKey, outcome) {
        if (outcome.status === 'timeout') {
            this.toast('integrations_page.amocrm_task_poll_timeout', { type: 'warning' });
            return;
        }
        if (outcome.status === 'missing') {
            this.toast(failedKey, { type: 'error', vars: { message: '' } });
            return;
        }
        this.toast(failedKey, { type: 'error', vars: { message: outcome.error_message } });
    }

    _onAutoSyncSwitch(e) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'boolean') {
            throw new Error('auto-sync switch: ожидался detail.value (boolean)');
        }
        this._autoSyncEnabled = d.value;
    }

    _onAutoCronInput(e) {
        const d = e && e.detail;
        if (!d || typeof d.value !== 'string') {
            throw new Error('auto-sync cron: expected detail.value (string)');
        }
        this._autoSyncCron = d.value;
    }

    _onAutoTzInput(e) {
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
            return;
        }
        await this._integrationAutoSyncOp.run({
            namespace_name: this.itemId,
            provider_id: PROVIDER_AMOCRM,
            auto_sync_enabled: this._autoSyncEnabled,
            auto_sync_cron: this._autoSyncEnabled ? cronRaw : null,
            auto_sync_timezone: tzRaw.length > 0 ? tzRaw : 'UTC',
        });
        this._namespaces.get(this.itemId);
        this._listOp.run({ namespace_name: this.itemId });
    }

    async _onAutoNoteAiSwitch(e) {
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
            if (!entitiesStarted || typeof entitiesStarted.task_id !== 'string') {
                throw new Error('amocrm sync: task_id missing in response');
            }
            this.toast('integrations_page.amocrm_unified_sync_started', { type: 'success' });
            this._listOp.run({ namespace_name: this.itemId });
            const entitiesOutcome = await this._pollCrmTaskOutcome(entitiesStarted.task_id);
            if (!entitiesOutcome.ok) {
                this._toastTaskFailure('integrations_page.amocrm_sync_task_failed', entitiesOutcome);
                return;
            }
            const fieldsStarted = await this._integrationCustomFieldsSyncOp.run({
                namespace_name: this.itemId,
                provider_id: PROVIDER_AMOCRM,
            });
            if (fieldsStarted === null) return;
            if (!fieldsStarted || typeof fieldsStarted.task_id !== 'string') {
                throw new Error('amocrm fields: task_id missing in response');
            }
            this._listOp.run({ namespace_name: this.itemId });
            const fieldsOutcome = await this._pollCrmTaskOutcome(fieldsStarted.task_id);
            if (!fieldsOutcome.ok) {
                this._toastTaskFailure('integrations_page.amocrm_fields_task_failed', fieldsOutcome);
                return;
            }
            this.toast('integrations_page.amocrm_unified_sync_done', { type: 'success' });
        } finally {
            this._amoUnifiedSyncBusy = false;
        }
    }

    render() {
        if (typeof this.itemId !== 'string' || this.itemId.length === 0) {
            return html`
                <div class="center">
                    <p>${this.t('space_detail_page.no_id')}</p>
                </div>
            `;
        }
        const ns = this._namespace();
        if (ns === null) {
            return html`<div class="center"><glass-spinner size="lg"></glass-spinner></div>`;
        }

        const amoRow = this._amoManifestRow();
        const connected = amoRow && amoRow.connected === true;

        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${this.t('integrations_page.breadcrumb_tail')}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header
                    title=${this.t('integrations_page.title')}
                    subtitle=${this.t('integrations_page.subtitle', { name: ns.name })}
                ></page-header>
                <p class="hint" style="padding: 0 var(--space-4); margin-top: var(--space-1);">
                    ${this.t('integrations_page.scope_hint')}
                </p>
            </div>
            <div class="scroll">
                ${this._manifestLoading
                    ? html`<div class="center"><glass-spinner size="md"></glass-spinner></div>`
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
                        <label class="field-label">${this.t('space_detail_page.amocrm_subdomain_label')}</label>
                        <input
                            class="input"
                            type="text"
                            autocomplete="off"
                            placeholder=${this.t('space_detail_page.amocrm_subdomain_placeholder')}
                            .value=${this._subdomainDraft}
                            @input=${this._onSubInput}
                        />
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
                            ${this.t('space_detail_page.amocrm_connect')}
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
                            <label class="field-label">${this.t('integrations_page.auto_sync_cron_label')}</label>
                            <platform-cron-field
                                .value=${this._autoSyncCron}
                                placeholder=${this.t('integrations_page.auto_sync_cron_placeholder')}
                                ?disabled=${this._integrationAutoSyncOp.busy}
                                @input=${this._onAutoCronInput}
                                @change=${this._onAutoCronInput}
                            ></platform-cron-field>
                            <p class="hint">${this.t('integrations_page.auto_sync_cron_help')}</p>
                        </div>
                        <div class="field">
                            <label class="field-label">${this.t('integrations_page.auto_sync_tz_label')}</label>
                            <platform-timezone-picker
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

customElements.define('crm-space-integrations-page', CRMSpaceIntegrationsPage);
