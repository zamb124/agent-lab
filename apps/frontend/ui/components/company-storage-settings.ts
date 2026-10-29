/**
 * Настройка объектных хранилищ компании: подключения, проверка и маршрут по типу файла.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-spinner.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { OpController, FormController, SliceController } from '@platform/lib/base/use-resource.js';

const ROUTE_KINDS = Object.freeze([
    { id: 'default', labelKey: 'settings_page.storage_default_route' },
    { id: 'crm_entity', labelKey: 'settings_page.storage_kind_crm_entity' },
    { id: 'office_document', labelKey: 'settings_page.storage_kind_office_document' },
    { id: 'mail_message', labelKey: 'settings_page.storage_kind_mail_message' },
    { id: 'wiki_page', labelKey: 'settings_page.storage_kind_wiki_page' },
    { id: 'rag_document', labelKey: 'settings_page.storage_kind_rag_document' },
    { id: 'sync_message', labelKey: 'settings_page.storage_kind_sync_message' },
    { id: 'sync_call_recording', labelKey: 'settings_page.storage_kind_sync_call_recording' },
    { id: 'sync_speech_segment', labelKey: 'settings_page.storage_kind_sync_speech_segment' },
    { id: 'sync_channel_asset', labelKey: 'settings_page.storage_kind_sync_channel_asset' },
    { id: 'flow_asset', labelKey: 'settings_page.storage_kind_flow_asset' },
    { id: 'flow_session', labelKey: 'settings_page.storage_kind_flow_session' },
    { id: 'code_agent_source', labelKey: 'settings_page.storage_kind_code_agent_source' },
    { id: 'work_item', labelKey: 'settings_page.storage_kind_work_item' },
    { id: 'calendar_event', labelKey: 'settings_page.storage_kind_calendar_event' },
    { id: 'browser_artifact', labelKey: 'settings_page.storage_kind_browser_artifact' },
    { id: 'generated_ephemeral', labelKey: 'settings_page.storage_kind_generated_ephemeral' },
]);

const PROVIDERS = Object.freeze([
    { value: 'seaweedfs', label: 'SeaweedFS' },
    { value: 'aws', label: 'S3' },
]);

function anyRecord(value: unknown): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error('company-storage-settings: object required');
    }
    return value;
}

function recordList(value: unknown, label: string): Record<string, unknown>[] {
    if (!Array.isArray(value)) {
        throw new Error(`company-storage-settings: ${label} must be an array`);
    }
    return value.map((item) => {
        if (!isPlainRecord(item)) {
            throw new Error(`company-storage-settings: ${label} row must be an object`);
        }
        return anyRecord(item);
    });
}

function migrationProgress(value: unknown): Record<string, unknown> | null {
    if (value === null || value === undefined) {
        return null;
    }
    return anyRecord(value);
}

export class CompanyStorageSettings extends PlatformElement {
    static override styles: CSSResultGroup = css`
        :host { display: block; }
        .lead {
            color: var(--text-secondary);
            margin: 0 0 var(--space-4) 0;
            max-width: 68ch;
        }
        .layout {
            display: grid;
            grid-template-columns: minmax(0, 1.2fr) minmax(320px, 420px);
            gap: var(--space-6);
            align-items: start;
        }
        @media (max-width: 767px) {
            .layout { grid-template-columns: minmax(0, 1fr); }
        }
        .card {
            background: var(--bg-elevated);
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            display: flex;
            flex-direction: column;
            gap: var(--space-3);
        }
        h3 {
            margin: 0;
            color: var(--text-primary);
            font-size: var(--text-md);
        }
        .connection {
            display: flex;
            flex-direction: column;
            gap: var(--space-1);
            padding: var(--space-3);
            border-radius: var(--radius-md);
            border: 1px solid var(--glass-border-subtle);
        }
        .connection-head {
            display: flex;
            justify-content: space-between;
            gap: var(--space-3);
            align-items: center;
        }
        .name { color: var(--text-primary); font-weight: var(--font-semibold); }
        .meta { color: var(--text-secondary); font-size: var(--text-sm); }
        .state { font-size: var(--text-sm); font-weight: var(--font-medium); }
        .state[data-state='active'] { color: var(--success); }
        .state[data-state='draining'] { color: var(--warning); }
        .state[data-state='verifying'] { color: var(--info); }
        .state[data-state='retired'] { color: var(--text-tertiary); }
        .actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
        .routes { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-6); }
        .locked {
            color: var(--text-secondary);
            font-size: var(--text-sm);
            margin: 0;
        }
        .progress {
            margin-top: var(--space-4);
            color: var(--text-primary);
        }
        .error { color: var(--error); margin: 0; }
    `;

    constructor() {
        super();
        this._list = this.useOp('frontend/company_storages_load');
        this._probe = this.useOp('frontend/company_storages_probe');
        this._create = this.useOp('frontend/company_storages_create');
        this._remove = this.useOp('frontend/company_storages_delete');
        this._route = this.useOp('frontend/company_storage_routes_set');
        this._rotate = this.useOp('frontend/company_storages_rotate');
        this._move = this.useOp('frontend/company_storage_migrations_start');
        this._form = this.useForm('frontend/company_storage_create_form');
        this._progress = this.useSlice('frontend/company_storage_migration');
        this._rotateId = '';
        this._rotateKey = '';
        this._rotateSecret = '';
        this._moveId = '';
        this._moveTarget = '';
    }
    private _list: OpController;
    private _probe: OpController;
    private _create: OpController;
    private _remove: OpController;
    private _route: OpController;
    private _rotate: OpController;
    private _move: OpController;
    private _form: FormController;
    private _progress: SliceController;
    private _rotateId: string;
    private _rotateKey: string;
    private _rotateSecret: string;
    private _moveId: string;
    private _moveTarget: string;


    override connectedCallback(): void {
        super.connectedCallback();
        this._list.run(null);
    }

    _snapshot() {
        const result = this._list.lastResult;
        if (result === null) {
            return { storages: [], routes: [] };
        }
        const snapshot = anyRecord(result);
        return {
            storages: recordList(snapshot.storages, 'storages'),
            routes: recordList(snapshot.routes, 'routes'),
        };
    }

    _stateLabel(state: string) {
        if (state === 'active') return this.t('settings_page.storage_state_active');
        if (state === 'verifying') return this.t('settings_page.storage_state_verifying');
        if (state === 'draining') return this.t('settings_page.storage_state_draining');
        if (state === 'retired') return this.t('settings_page.storage_state_retired');
        return this.t('settings_page.storage_state_verifying');
    }

    _options(storages: Array<Record<string, unknown>>) {
        const options = [{ value: 'platform', label: this.t('settings_page.storage_platform') }];
        for (const row of storages) {
            const storageId = row.storage_id;
            const name = row.name;
            if (typeof storageId !== 'string' || storageId.length === 0 || typeof name !== 'string' || name.length === 0) {
                throw new Error('company-storage-settings: storage option requires storage_id and name');
            }
            options.push({ value: storageId, label: name });
        }
        return options;
    }

    _selected(routes: Array<Record<string, unknown>>, kindId: string) {
        const match = routes.find((row) => row.source_kind === kindId);
        if (match === undefined) return 'platform';
        if (typeof match.storage_id !== 'string' || match.storage_id.length === 0) {
            throw new Error('company-storage-settings: route storage_id required');
        }
        return match.storage_id;
    }

    _probeConnection() {
        const draft = anyRecord(this._form.draft);
        this._probe.run({
            provider: draft.provider,
            endpoint_url: draft.endpoint_url,
            region_name: draft.region_name,
            bucket_name: draft.bucket_name,
            path_style: draft.path_style,
            access_key_id: draft.access_key_id,
            secret_access_key: draft.secret_access_key,
        });
    }

    async _deleteStorage(row: Record<string, unknown>) {
        const name = row.name;
        if (typeof name !== 'string') {
            throw new Error('company-storage-settings: storage name required');
        }
        const ok = await platformConfirm(
            this.t('settings_page.storage_delete_body', { name }),
            {
                title: this.t('settings_page.storage_delete_title'),
                variant: 'danger',
                confirmText: this.t('settings_page.storage_confirm'),
                cancelText: this.t('settings_page.storage_cancel'),
                confirmVariant: 'danger',
            },
        );
        if (ok !== true) return;
        this._remove.run({ storage_id: row.storage_id });
    }

    _probeKeys(row: Record<string, unknown>) {
        this._probe.run({
            provider: row.provider,
            endpoint_url: row.endpoint_url,
            region_name: row.region_name,
            bucket_name: row.bucket_name,
            path_style: row.path_style,
            access_key_id: this._rotateKey,
            secret_access_key: this._rotateSecret,
        });
    }

    _saveKeys(row: Record<string, unknown>) {
        this._rotate.run({
            storage_id: row.storage_id,
            access_key_id: this._rotateKey,
            secret_access_key: this._rotateSecret,
        });
    }

    _startMove(row: Record<string, unknown>) {
        this._move.run({
            source_storage_id: row.storage_id,
            target_storage_id: this._moveTarget,
        });
    }

    _migrationLabel(state: string) {
        if (state === 'running') return this.t('settings_page.storage_migration_running');
        if (state === 'completed') return this.t('settings_page.storage_migration_completed');
        if (state === 'failed') return this.t('settings_page.storage_migration_failed');
        return this.t('settings_page.storage_migration_running');
    }

    _migrationState(progress: Record<string, unknown>): string {
        if (typeof progress.state !== 'string' || progress.state.length === 0) {
            throw new Error('company-storage-settings: migration state required');
        }
        return progress.state;
    }

    _migrationCounts(progress: Record<string, unknown>): { moved: string | number; total: string | number } {
        const moved = progress.files_moved;
        const total = progress.files_total;
        if ((typeof moved !== 'number' && typeof moved !== 'string') || (typeof total !== 'number' && typeof total !== 'string')) {
            throw new Error('company-storage-settings: migration counts required');
        }
        return { moved, total };
    }

    _assignRoute(kindId: string, storageId: unknown) {
        if (typeof storageId !== 'string' || storageId.length === 0) {
            throw new Error('company-storage-settings: route storage_id required');
        }
        const sourceKind = kindId === 'default' ? null : kindId;
        this._route.run({ storage_id: storageId, source_kind: sourceKind });
    }

    override render(): TemplateResult {
        const snapshot = this._snapshot();
        const storages = snapshot.storages;
        const routes = snapshot.routes;
        const draft = anyRecord(this._form.draft);
        const progress = migrationProgress(this._progress.value.progress);
        const options = this._options(storages);
        return html`
            <p class="lead">${this.t('settings_page.storage_lead')}</p>
            <div class="layout">
                <section class="card">
                    <h3>${this.t('settings_page.storage_connections')}</h3>
                    ${this._list.lastResult === null ? html`<platform-spinner></platform-spinner>` : nothing}
                    ${this._list.lastResult !== null && storages.length === 0
                        ? html`<p class="locked">${this.t('settings_page.storage_empty_connections')}</p>`
                        : nothing}
                    ${storages.map((row) => {
                        const storageId = row.storage_id;
                        const state = row.state;
                        if (typeof storageId !== 'string' || storageId.length === 0 || typeof state !== 'string') {
                            throw new Error('company-storage-settings: storage row requires storage_id and state');
                        }
                        return html`
                        <article class="connection">
                            <div class="connection-head">
                                <span class="name">${row.name}</span>
                                <span class="state" data-state=${state}>${this._stateLabel(state)}</span>
                            </div>
                            <div class="meta">${row.endpoint_url}</div>
                            <div class="meta">${row.bucket_name} · ${row.region_name}</div>
                            <div class="actions">
                                <platform-button variant="secondary" @click=${() => { this._rotateId = storageId; this.requestUpdate(); }}>
                                    ${this.t('settings_page.storage_rotate')}
                                </platform-button>
                                <platform-button variant="secondary" @click=${() => { this._moveId = storageId; this.requestUpdate(); }}>
                                    ${this.t('settings_page.storage_move')}
                                </platform-button>
                                <platform-button variant="danger" @click=${() => this._deleteStorage(row)}>
                                    ${this.t('settings_page.storage_delete')}
                                </platform-button>
                            </div>
                            ${this._rotateId === storageId ? html`
                                <platform-field type="text" label=${this.t('settings_page.storages_access_key')}
                                    .value=${this._rotateKey}
                                    @change=${(event: CustomEvent) => { this._rotateKey = event.detail.value; this.requestUpdate(); }}></platform-field>
                                <platform-field type="password" label=${this.t('settings_page.storages_secret')}
                                    .value=${this._rotateSecret}
                                    @change=${(event: CustomEvent) => { this._rotateSecret = event.detail.value; this.requestUpdate(); }}></platform-field>
                                <div class="actions">
                                    <platform-button variant="secondary" ?disabled=${this._probe.busy} @click=${() => this._probeKeys(row)}>
                                        ${this.t('settings_page.storage_rotate_test')}
                                    </platform-button>
                                    <platform-button variant="primary" ?disabled=${this._rotate.busy} @click=${() => this._saveKeys(row)}>
                                        ${this.t('settings_page.storage_rotate_save')}
                                    </platform-button>
                                </div>
                            ` : nothing}
                            ${this._moveId === storageId ? html`
                                <platform-field type="enum" label=${this.t('settings_page.storage_move')}
                                    .value=${this._moveTarget}
                                    .config=${{ values: options.filter((option) => option.value !== storageId) }}
                                    @change=${(event: CustomEvent) => { this._moveTarget = event.detail.value; this.requestUpdate(); }}></platform-field>
                                <platform-button variant="primary" ?disabled=${this._move.busy || this._moveTarget === ''} @click=${() => this._startMove(row)}>
                                    ${this.t('settings_page.storage_move_start')}
                                </platform-button>
                            ` : nothing}
                        </article>
                    `;
                    })}
                </section>
                <section class="card">
                    <h3>${this.t('settings_page.storage_new')}</h3>
                    <platform-field type="text" label=${this.t('settings_page.storages_name')}
                        .value=${draft.name}
                        @change=${(event: CustomEvent) => this._form.setField('name', event.detail.value)}></platform-field>
                    <platform-field type="enum" label=${this.t('settings_page.storage_provider')}
                        .value=${draft.provider}
                        .config=${{ values: PROVIDERS }}
                        @change=${(event: CustomEvent) => this._form.setField('provider', event.detail.value)}></platform-field>
                    <platform-field type="text" label=${this.t('settings_page.storages_endpoint')}
                        .value=${draft.endpoint_url}
                        @change=${(event: CustomEvent) => this._form.setField('endpoint_url', event.detail.value)}></platform-field>
                    <platform-field type="text" label=${this.t('settings_page.storages_region')}
                        .value=${draft.region_name}
                        @change=${(event: CustomEvent) => this._form.setField('region_name', event.detail.value)}></platform-field>
                    <platform-field type="text" label=${this.t('settings_page.storages_bucket')}
                        .value=${draft.bucket_name}
                        @change=${(event: CustomEvent) => this._form.setField('bucket_name', event.detail.value)}></platform-field>
                    <platform-field type="text" label=${this.t('settings_page.storages_access_key')}
                        .value=${draft.access_key_id}
                        @change=${(event: CustomEvent) => this._form.setField('access_key_id', event.detail.value)}></platform-field>
                    <platform-field type="password" label=${this.t('settings_page.storages_secret')}
                        .value=${draft.secret_access_key}
                        @change=${(event: CustomEvent) => this._form.setField('secret_access_key', event.detail.value)}></platform-field>
                    <platform-field type="boolean" label=${this.t('settings_page.storage_path_style')}
                        .value=${draft.path_style}
                        @change=${(event: CustomEvent) => this._form.setField('path_style', event.detail.value)}></platform-field>
                    <div class="actions">
                        <platform-button variant="secondary" ?disabled=${this._probe.busy} @click=${() => this._probeConnection()}>
                            ${this.t('settings_page.storage_test')}
                        </platform-button>
                        <platform-button variant="primary" ?disabled=${this._form.submitting} @click=${() => this._form.submit()}>
                            ${this.t('settings_page.storage_save')}
                        </platform-button>
                    </div>
                </section>
            </div>
            <section class="routes">
                <h3>${this.t('settings_page.storage_routes')}</h3>
                <p class="locked">${this.t('settings_page.storage_platform_locked')}</p>
                ${ROUTE_KINDS.map((kind) => html`
                    <platform-field
                        type="enum"
                        label=${this.t(kind.labelKey)}
                        .value=${this._selected(routes, kind.id)}
                        .config=${{ values: options }}
                        @change=${(event: CustomEvent) => this._assignRoute(kind.id, event.detail.value)}
                    ></platform-field>
                `)}
            </section>
            ${progress === null ? nothing : html`
                <section class="card progress">
                    <h3>${this.t('settings_page.storage_migration_title')}</h3>
                    <p>${this._migrationLabel(this._migrationState(progress))} · ${this.t('settings_page.storage_migration_counts', this._migrationCounts(progress))}</p>
                    ${typeof progress.last_error === 'string' && progress.last_error !== ''
                        ? html`<p class="error">${progress.last_error}</p>`
                        : nothing}
                </section>
            `}
        `;
    }
}

customElements.define('company-storage-settings', CompanyStorageSettings);
