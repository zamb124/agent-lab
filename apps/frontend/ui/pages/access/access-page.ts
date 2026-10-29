/**
 * Access Explorer — master-detail админка явных грантов для company admin.
 */
import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';
import '../../components/sheets/access-why-sheet.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { OpController, ResourceController, SliceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { RouterState } from '@platform/lib/events/reducers/router.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

const OBJECT_TYPES = Object.freeze([
    'wiki_page',
    'document_file',
    'document_catalog',
    'crm_entity',
    'crm_namespace',
    'flow',
    'tool',
    'sync_channel',
    'work_queue',
    'mailbox_binding',
    'platform_namespace',
]);

const TYPE_ICONS = Object.freeze({
    wiki_page: 'book-open',
    document_file: 'file',
    document_catalog: 'folder',
    crm_entity: 'users',
    crm_namespace: 'folder',
    flow: 'workflow',
    tool: 'variable',
    sync_channel: 'chat',
    work_queue: 'clock',
    mailbox_binding: 'mail',
    platform_namespace: 'folder',
    flow_ui_share: 'chat',
    flow_branch: 'workflow',
});

const OBJECT_SEARCH_DEBOUNCE_MS = 250;

interface ExplorerUiState {
    mode: 'people' | 'objects';
    userId: string;
    objectType: string;
    objectKey: string;
    pickerTypeFilter: string;
    grantTypeFilter: string;
    relationFilter: string;
    sourceFilter: string;
    peopleQuery: string;
    objectsQuery: string;
    whyOpen: boolean;
    whyUserId: string;
    whyObjectType: string;
    whyObjectKey: string;
    mobilePane: string;
}

function requireUiString(value: unknown, label: string): string {
    if (typeof value !== 'string') {
        throw new Error(`access page: ${label} must be a string`);
    }
    return value;
}

function readExplorerUi(value: unknown): ExplorerUiState {
    if (!isPlainRecord(value)) {
        throw new Error('access page: explorer ui state required');
    }
    const mode = value.mode;
    if (mode !== 'people' && mode !== 'objects') {
        throw new Error('access page: mode must be people or objects');
    }
    if (value.whyOpen !== true && value.whyOpen !== false) {
        throw new Error('access page: whyOpen must be boolean');
    }
    return {
        mode,
        userId: requireUiString(value.userId, 'userId'),
        objectType: requireUiString(value.objectType, 'objectType'),
        objectKey: requireUiString(value.objectKey, 'objectKey'),
        pickerTypeFilter: requireUiString(value.pickerTypeFilter, 'pickerTypeFilter'),
        grantTypeFilter: requireUiString(value.grantTypeFilter, 'grantTypeFilter'),
        relationFilter: requireUiString(value.relationFilter, 'relationFilter'),
        sourceFilter: requireUiString(value.sourceFilter, 'sourceFilter'),
        peopleQuery: requireUiString(value.peopleQuery, 'peopleQuery'),
        objectsQuery: requireUiString(value.objectsQuery, 'objectsQuery'),
        whyOpen: value.whyOpen,
        whyUserId: requireUiString(value.whyUserId, 'whyUserId'),
        whyObjectType: requireUiString(value.whyObjectType, 'whyObjectType'),
        whyObjectKey: requireUiString(value.whyObjectKey, 'whyObjectKey'),
        mobilePane: requireUiString(value.mobilePane, 'mobilePane'),
    };
}

function requireRowString(row: Record<string, unknown>, field: string): string {
    const value = row[field];
    if (typeof value !== 'string' || value.length === 0) {
        throw new Error(`access page: ${field} required`);
    }
    return value;
}

function resultItems(value: unknown): Record<string, unknown>[] | null {
    if (!isPlainRecord(value) || !Array.isArray(value.items)) {
        return null;
    }
    const items: Record<string, unknown>[] = [];
    for (const item of value.items) {
        if (!isPlainRecord(item)) {
            throw new Error('access page: row must be an object');
        }
        items.push(item);
    }
    return items;
}


export class FrontendAccessPage extends PlatformPage {
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        frontendIslandPageBodyStyles,
        css`
            :host { display: block; }

            .layout {
                display: grid;
                grid-template-columns: 320px minmax(0, 1fr);
                gap: var(--space-4);
                min-height: 56vh;
                align-items: start;
            }
            .pane {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                min-height: 24rem;
            }
            .pane-master { padding: var(--space-3); }
            .pane-detail { padding: var(--space-4); position: relative; }
            .mode-row {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }
            .mode-btn, .chip {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                padding: var(--space-2) var(--space-3);
            }
            .mode-btn[aria-pressed="true"],
            .chip[aria-pressed="true"] {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            .search { margin-bottom: var(--space-3); }
            .picker-list { display: flex; flex-direction: column; gap: var(--space-2); }
            .picker-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                text-align: left;
                padding: var(--space-3);
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                cursor: pointer;
            }
            .picker-item:hover, .picker-item[aria-current="true"] {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
            }
            .picker-meta { font-size: var(--text-xs); color: var(--text-tertiary); }
            .summary {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin: var(--space-3) 0;
            }
            .detail-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .detail-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .detail-open {
                color: var(--accent);
                font-size: var(--text-sm);
                text-decoration: none;
            }
            .grant-list { display: flex; flex-direction: column; gap: var(--space-2); }
            .grant-row {
                display: grid;
                grid-template-columns: 28px minmax(0, 1fr) auto;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-surface);
            }
            .grant-row[data-why="true"] { cursor: pointer; }
            .grant-main { min-width: 0; }
            .grant-title-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .grant-title {
                color: var(--text-primary);
                font-weight: var(--font-medium);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .relation-chip {
                flex-shrink: 0;
                padding: 0 var(--space-2);
                border-radius: var(--radius-full);
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                line-height: 1.6;
            }
            .grant-sub { font-size: var(--text-xs); color: var(--text-tertiary); }
            .grant-actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
                opacity: 0;
            }
            .grant-row:hover .grant-actions,
            .grant-row:focus-within .grant-actions {
                opacity: 1;
            }
            .empty {
                padding: var(--space-8) var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
            }
            .empty-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                margin-bottom: var(--space-2);
            }
            .skeleton-row {
                height: 3rem;
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                margin-bottom: var(--space-2);
            }
            .why-drawer {
                margin-top: var(--space-4);
                padding: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .why-meta {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }
            .why-item {
                padding: var(--space-3) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
            }
            .back-btn {
                display: none;
                margin-bottom: var(--space-3);
                border: 0;
                background: transparent;
                color: var(--accent);
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .id-btn {
                border: 0;
                background: transparent;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
                padding: 0;
            }
            .forbidden { padding: var(--space-8); text-align: center; }

            @media (max-width: 767px) {
                .layout { grid-template-columns: 1fr; }
                .layout[data-mobile-pane="picker"] .pane-detail { display: none; }
                .layout[data-mobile-pane="detail"] .pane-master { display: none; }
                .back-btn { display: inline-flex; align-items: center; gap: var(--space-2); }
                .grant-row { grid-template-columns: 28px minmax(0, 1fr); }
                .grant-actions {
                    grid-column: 1 / -1;
                    opacity: 1;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._members = this.useResource('frontend/team', { autoload: true });
        this._ui = this.useSlice('frontend/authz_explorer_ui');
        this._byUser = this.useOp('frontend/authz_explorer_by_user');
        this._byObject = this.useOp('frontend/authz_explorer_by_object');
        this._why = this.useOp('frontend/authz_explorer_why');
        this._objects = this.useOp('frontend/authz_explorer_objects');
        this._revokeOp = this.useOp('frontend/authz_explorer_revoke');
        this._authSel = this.select((state) => state.auth.user);
        this._routeSel = this.select((state) => state.router);
        this._lastRouteSig = '';
        this._lastObjectsSig = '';
        this._objectsSearchTimer = 0;
    }
    private _members: ResourceController;
    private _ui: ControllerFor<'frontend/authz_explorer_ui'>;
    private _byUser: OpController;
    private _byObject: OpController;
    private _why: OpController;
    private _objects: OpController;
    private _revokeOp: OpController;
    private _authSel: SelectController<AuthUser | null>;
    private _routeSel: SelectController<RouterState>;
    private _lastRouteSig: string;
    private _lastObjectsSig: string;
    private _objectsSearchTimer: number;


    override disconnectedCallback(): void {
        if (this._objectsSearchTimer !== 0) {
            window.clearTimeout(this._objectsSearchTimer);
            this._objectsSearchTimer = 0;
        }
        super.disconnectedCallback();
    }

    override updated() {
        this._syncFromRoute();
        this._syncObjectSearch();
    }

    _canAdmin() {
        const user = this._authSel.value;
        return Boolean(user && user.canAdmin === true);
    }

    _syncFromRoute() {
        const route = this._routeSel.value;
        if (!route || route.routeKey !== 'access') {
            return;
        }
        const search = typeof route.search === 'string' ? route.search : '';
        const params = new URLSearchParams(search);
        const userId = params.get('user_id');
        const objectType = params.get('object_type');
        const objectKey = params.get('object_key');
        const sig = `${userId === null ? '' : userId}\n${objectType === null ? '' : objectType}\n${objectKey === null ? '' : objectKey}`;
        if (sig === this._lastRouteSig) {
            return;
        }
        this._lastRouteSig = sig;
        if (typeof userId === 'string' && userId.length > 0) {
            this._ui.selectUser({ userId });
            void this._byUser.run({ user_id: userId });
            return;
        }
        if (typeof objectType === 'string' && objectType.length > 0
            && typeof objectKey === 'string' && objectKey.length > 0) {
            this._ui.selectObject({ objectType, objectKey });
            void this._byObject.run({ object_type: objectType, object_key: objectKey });
        }
    }

    _canSearchObjects() {
        const ui = readExplorerUi(this._ui.value);
        return ui.objectsQuery.trim().length >= 2 || ui.pickerTypeFilter !== '';
    }

    _syncObjectSearch() {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode !== 'objects') {
            return;
        }
        if (!this._canSearchObjects()) {
            this._lastObjectsSig = '';
            return;
        }
        const sig = `${ui.objectsQuery.trim()}\n${ui.pickerTypeFilter}`;
        if (sig === this._lastObjectsSig) {
            return;
        }
        this._lastObjectsSig = sig;
        if (this._objectsSearchTimer !== 0) {
            window.clearTimeout(this._objectsSearchTimer);
        }
        this._objectsSearchTimer = window.setTimeout(() => {
            this._objectsSearchTimer = 0;
            const current = readExplorerUi(this._ui.value);
            if (current.mode !== 'objects') {
                return;
            }
            const query = current.objectsQuery.trim();
            if (query.length < 2 && current.pickerTypeFilter === '') {
                return;
            }
            void this._objects.run({
                q: query,
                object_type: current.pickerTypeFilter === '' ? null : current.pickerTypeFilter,
            });
        }, OBJECT_SEARCH_DEBOUNCE_MS);
    }

    _writeUrl(search: string) {
        this.navigate('access', {}, { search });
    }

    _selectUser(userId: unknown) {
        if (typeof userId !== 'string' || userId.length === 0) {
            throw new Error('access page: user_id required');
        }
        this._writeUrl(`?user_id=${encodeURIComponent(userId)}`);
    }

    _selectObject(objectType: string, objectKey: string) {
        this._writeUrl(
            `?object_type=${encodeURIComponent(objectType)}&object_key=${encodeURIComponent(objectKey)}`,
        );
    }

    _setMode(mode: string) {
        this._ui.setMode({ mode });
        this._writeUrl('');
        this._lastRouteSig = '\n\n';
        if (mode === 'objects') {
            this._lastObjectsSig = '';
        }
    }

    _filteredMembers() {
        const query = readExplorerUi(this._ui.value).peopleQuery.trim().toLowerCase();
        const items = this._members.items;
        if (query === '') {
            return items;
        }
        return items.filter((member) => {
            const name = typeof member.name === 'string' ? member.name.toLowerCase() : '';
            const email = typeof member.email === 'string' ? member.email.toLowerCase() : '';
            return name.includes(query) || email.includes(query);
        });
    }

    _currentRows() {
        const ui = readExplorerUi(this._ui.value);
        const payload = ui.mode === 'people' ? this._byUser.lastResult : this._byObject.lastResult;
        const items = resultItems(payload);
        if (items === null) {
            return [];
        }
        return items.filter((row) => {
            if (ui.grantTypeFilter !== '' && row.object_type !== ui.grantTypeFilter) {
                return false;
            }
            if (ui.relationFilter !== '' && row.relation !== ui.relationFilter) {
                return false;
            }
            if (ui.sourceFilter !== '' && row.grant_source !== ui.sourceFilter) {
                return false;
            }
            return true;
        });
    }

    _busy() {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'people') {
            return this._byUser.busy && !this._byUser.lastResult;
        }
        return this._byObject.busy && !this._byObject.lastResult;
    }

    _whyEnabled(row: Record<string, unknown>) {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'objects' && row.subject_kind !== 'user') {
            return false;
        }
        return true;
    }

    _openWhy(row: Record<string, unknown>) {
        if (!this._whyEnabled(row)) {
            return;
        }
        const ui = readExplorerUi(this._ui.value);
        const userId = ui.mode === 'people' ? ui.userId : row.subject_id;
        if (typeof userId !== 'string' || userId.length === 0) {
            return;
        }
        const objectType = ui.mode === 'people' ? row.object_type : ui.objectType;
        const objectKey = ui.mode === 'people' ? row.object_key : ui.objectKey;
        this._ui.openWhy({ userId, objectType, objectKey });
        if (window.matchMedia('(max-width: 767px)').matches) {
            this.openBottomSheet('frontend.access_why', {
                userId,
                objectType,
                objectKey,
                objectTitle: this._rowTitle(row),
            });
            return;
        }
        void this._why.run({
            user_id: userId,
            object_type: objectType,
            object_key: objectKey,
        });
    }

    async _revoke(row: Record<string, unknown>) {
        if (row.can_revoke !== true) {
            return;
        }
        const title = this._rowTitle(row);
        const confirmed = await platformConfirm(
            this.t('access_page.confirm_revoke', { title }),
        );
        if (confirmed !== true) {
            return;
        }
        await this._revokeOp.run({
            object_type: row.object_type,
            object_key: row.object_key,
            relation: row.relation,
            subject_kind: row.subject_kind,
            subject_id: row.subject_id,
        });
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'people' && ui.userId !== '') {
            void this._byUser.run({ user_id: ui.userId });
        }
        if (ui.mode === 'objects' && ui.objectType !== '' && ui.objectKey !== '') {
            void this._byObject.run({
                object_type: ui.objectType,
                object_key: ui.objectKey,
            });
        }
    }

    _rowTitle(row: Record<string, unknown>) {
        if (row.title_status === 'loaded' && typeof row.title === 'string' && row.title.length > 0) {
            return row.title;
        }
        if (row.title_status === 'unavailable') {
            return this.t('access_page.title_unavailable');
        }
        return this.t('access_page.title_missing');
    }

    _groupLabel(subjectId: unknown) {
        if (typeof subjectId !== 'string' || subjectId.length === 0) {
            throw new Error('access page: group subject_id required');
        }
        const slash = subjectId.lastIndexOf('/');
        const shortName = slash >= 0 ? subjectId.slice(slash + 1) : subjectId;
        if (shortName.length === 0) {
            throw new Error('access page: group name is empty');
        }
        return this.t('access_page.subject_group', { name: shortName });
    }

    _copyObjectId(objectType: unknown, objectKey: unknown) {
        if (typeof objectType !== 'string' || typeof objectKey !== 'string') {
            throw new Error('access page: object id required');
        }
        this.copyToClipboard(`${objectType}:${objectKey}`, {
            success_i18n_key: 'frontend:access_page.toast_copied',
            error_i18n_key: 'frontend:access_page.err_clipboard',
        });
    }

    _retryHydrate() {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'people' && ui.userId !== '') {
            void this._byUser.run({ user_id: ui.userId });
            return;
        }
        if (ui.objectType !== '' && ui.objectKey !== '') {
            void this._byObject.run({
                object_type: ui.objectType,
                object_key: ui.objectKey,
            });
        }
    }

    _pickerTypeEnumConfig() {
        return {
            values: [
                { value: '', label: this.t('access_page.filter_all_types') },
                ...OBJECT_TYPES.map((typeName) => ({
                    value: typeName,
                    label: this.t(`access_page.type_${typeName}`),
                })),
            ],
        };
    }

    override render(): TemplateResult {
        if (!this._canAdmin()) {
            return html`
                <platform-breadcrumbs></platform-breadcrumbs>
                <page-header
                    title=${this.t('access_page.title')}
                    subtitle=${this.t('access_page.subtitle')}
                ></page-header>
                <div class="page-body forbidden">
                    <div class="empty-title">${this.t('access_page.forbidden_title')}</div>
                    <div>${this.t('access_page.forbidden_description')}</div>
                </div>
            `;
        }
        const ui = readExplorerUi(this._ui.value);
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                title=${this.t('access_page.title')}
                subtitle=${this.t('access_page.subtitle')}
            ></page-header>
            <div class="page-body">
                <div class="layout" data-mobile-pane=${ui.mobilePane}>
                    <section class="pane pane-master">${this._renderMaster()}</section>
                    <section class="pane pane-detail">${this._renderDetail()}</section>
                </div>
            </div>
        `;
    }

    _renderMaster() {
        const ui = readExplorerUi(this._ui.value);
        return html`
            <div class="mode-row" role="tablist">
                <button
                    type="button"
                    class="mode-btn"
                    aria-pressed=${ui.mode === 'people' ? 'true' : 'false'}
                    @click=${() => this._setMode('people')}
                >${this.t('access_page.mode_people')}</button>
                <button
                    type="button"
                    class="mode-btn"
                    aria-pressed=${ui.mode === 'objects' ? 'true' : 'false'}
                    @click=${() => this._setMode('objects')}
                >${this.t('access_page.mode_objects')}</button>
            </div>
            ${ui.mode === 'people' ? this._renderPeoplePicker() : this._renderObjectPicker()}
        `;
    }

    _renderPeoplePicker() {
        const ui = readExplorerUi(this._ui.value);
        const members = this._filteredMembers();
        return html`
            <platform-field
                class="search"
                type="string"
                input-type="search"
                mode="edit"
                label=${this.t('access_page.search_people')}
                .value=${ui.peopleQuery}
                @change=${(e: CustomEvent) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('access page: people query expects detail.value string');
                    }
                    this._ui.setPeopleQuery({ peopleQuery: e.detail.value });
                }}
            ></platform-field>
            ${this._members.loading && this._members.items.length === 0
                ? html`<div class="skeleton-row"></div><div class="skeleton-row"></div>`
                : nothing}
            ${!this._members.loading && members.length === 0
                ? html`
                    <div class="empty">
                        <div class="empty-title">${this.t('access_page.search_empty')}</div>
                        <button type="button" class="chip" @click=${() => this._ui.resetPickerSearch(null)}>
                            ${this.t('access_page.reset_filters')}
                        </button>
                    </div>
                `
                : html`
                    <div class="picker-list">
                        ${members.map((member) => html`
                            <button
                                type="button"
                                class="picker-item"
                                aria-current=${ui.userId === member.user_id ? 'true' : 'false'}
                                @click=${() => this._selectUser(member.user_id)}
                            >
                                <platform-user-chip user-id=${member.user_id} size="sm"></platform-user-chip>
                                <span class="picker-meta">${this._roleLabel(member)}</span>
                            </button>
                        `)}
                    </div>
                `}
        `;
    }

    _roleLabel(member: Record<string, unknown>) {
        const roles = Array.isArray(member.roles) ? member.roles : [];
        if (roles.length === 0) {
            return '';
        }
        return roles.map((role) => this.t(`team_roles.${role}`)).join(', ');
    }

    _renderObjectPicker() {
        const ui = readExplorerUi(this._ui.value);
        const result = this._objects.lastResult;
        const listed = resultItems(result);
        const items = listed === null ? [] : listed;
        const canSearch = this._canSearchObjects();
        return html`
            <platform-field
                class="search"
                type="enum"
                mode="edit"
                label=${this.t('access_page.picker_type_label')}
                .value=${ui.pickerTypeFilter}
                .config=${this._pickerTypeEnumConfig()}
                @change=${(e: CustomEvent) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('access page: picker type expects detail.value string');
                    }
                    this._ui.setPickerTypeFilter({ pickerTypeFilter: e.detail.value });
                    this._lastObjectsSig = '';
                }}
            ></platform-field>
            <platform-field
                class="search"
                type="string"
                input-type="search"
                mode="edit"
                label=${this.t('access_page.search_objects')}
                .value=${ui.objectsQuery}
                @change=${(e: CustomEvent) => {
                    if (!e.detail || typeof e.detail.value !== 'string') {
                        throw new Error('access page: objects query expects detail.value string');
                    }
                    this._ui.setObjectsQuery({ objectsQuery: e.detail.value });
                }}
            ></platform-field>
            ${!canSearch
                ? html`
                    <div class="empty">
                        <div class="empty-title">${this.t('access_page.search_hint')}</div>
                    </div>
                `
                : this._objects.busy && items.length === 0
                    ? html`<div class="skeleton-row"></div><div class="skeleton-row"></div>`
                    : !this._objects.busy && items.length === 0
                        ? html`
                            <div class="empty">
                                <div class="empty-title">${this.t('access_page.search_empty')}</div>
                                <button type="button" class="chip" @click=${() => this._ui.resetPickerSearch(null)}>
                                    ${this.t('access_page.reset_filters')}
                                </button>
                            </div>
                        `
                        : html`
                            <div class="picker-list">
                                ${items.map((hit) => {
                                    const objectType = requireRowString(hit, 'object_type');
                                    const objectKey = requireRowString(hit, 'object_key');
                                    return html`
                                    <button
                                        type="button"
                                        class="picker-item"
                                        aria-current=${ui.objectKey === objectKey ? 'true' : 'false'}
                                        @click=${() => this._selectObject(objectType, objectKey)}
                                    >
                                        <platform-icon name=${this._typeIcon(objectType)} size="18"></platform-icon>
                                        <span>
                                            <div>${this._hitTitle(hit)}</div>
                                            <div class="picker-meta">${this.t(`access_page.type_${objectType}`)}</div>
                                        </span>
                                    </button>
                                `;
                                })}
                            </div>
                        `}
        `;
    }

    _typeIcon(objectType: string) {
        switch (objectType) {
            case 'wiki_page':
                return TYPE_ICONS.wiki_page;
            case 'document_file':
                return TYPE_ICONS.document_file;
            case 'document_catalog':
                return TYPE_ICONS.document_catalog;
            case 'crm_entity':
                return TYPE_ICONS.crm_entity;
            case 'crm_namespace':
                return TYPE_ICONS.crm_namespace;
            case 'flow':
                return TYPE_ICONS.flow;
            case 'tool':
                return TYPE_ICONS.tool;
            case 'sync_channel':
                return TYPE_ICONS.sync_channel;
            case 'work_queue':
                return TYPE_ICONS.work_queue;
            case 'mailbox_binding':
                return TYPE_ICONS.mailbox_binding;
            case 'platform_namespace':
                return TYPE_ICONS.platform_namespace;
            case 'flow_ui_share':
                return TYPE_ICONS.flow_ui_share;
            case 'flow_branch':
                return TYPE_ICONS.flow_branch;
            default:
                throw new Error(`access page: unknown object_type ${objectType}`);
        }
    }

    _hitTitle(hit: Record<string, unknown>) {
        if (hit.title_status === 'loaded' && typeof hit.title === 'string' && hit.title.length > 0) {
            return hit.title;
        }
        if (hit.title_status === 'unavailable') {
            return this.t('access_page.title_unavailable');
        }
        return this.t('access_page.title_missing');
    }

    _renderDetail() {
        const ui = readExplorerUi(this._ui.value);
        const selected = ui.mode === 'people' ? ui.userId !== '' : ui.objectType !== '' && ui.objectKey !== '';
        if (!selected) {
            return html`
                <div class="empty">
                    <div class="empty-title">${this.t('access_page.pick_title')}</div>
                    <div>${this.t('access_page.pick_description')}</div>
                </div>
            `;
        }
        return html`
            <button
                type="button"
                class="back-btn"
                @click=${() => this._ui.setMobilePane({ mobilePane: 'picker' })}
            >${this.t('access_page.back')}</button>
            ${this._renderDetailHead()}
            ${this._renderSummary()}
            ${this._renderGrantList()}
            ${ui.whyOpen ? this._renderWhyDrawer() : nothing}
        `;
    }

    _renderDetailHead() {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'people') {
            return html`
                <div class="detail-head">
                    <platform-user-chip user-id=${ui.userId} size="md"></platform-user-chip>
                </div>
            `;
        }
        const result = this._byObject.lastResult;
        const record = isPlainRecord(result) ? result : null;
        const title = record ? this._hitTitle(record) : this.t('access_page.title_missing');
        const href = record !== null && typeof record.href === 'string' ? record.href : '';
        return html`
            <div class="detail-head">
                <div>
                    <div class="detail-title">${title}</div>
                    <div class="picker-meta">${this.t(`access_page.type_${ui.objectType}`)}</div>
                    ${record !== null && record.title_status !== 'loaded' ? html`
                        <button
                            type="button"
                            class="id-btn"
                            @click=${() => this._copyObjectId(ui.objectType, ui.objectKey)}
                        >${ui.objectType}:${ui.objectKey}</button>
                        <button type="button" class="chip" @click=${() => this._retryHydrate()}>
                            ${this.t('access_page.retry_title')}
                        </button>
                    ` : nothing}
                </div>
                ${href !== '' ? html`
                    <a class="detail-open" href=${href}>${this.t('access_page.open_in_service')}</a>
                ` : nothing}
            </div>
        `;
    }

    _renderSummary() {
        const ui = readExplorerUi(this._ui.value);
        const payload = ui.mode === 'people' ? this._byUser.lastResult : this._byObject.lastResult;
        if (!isPlainRecord(payload) || !isPlainRecord(payload.summary)) {
            return nothing;
        }
        const summary = payload.summary;
        const explicitCount = summary.explicit_grant_count;
        const groupCount = summary.group_count;
        if (typeof explicitCount !== 'number' || typeof groupCount !== 'number') {
            throw new Error('access page: summary counts required');
        }
        if (!isPlainRecord(summary.counts_by_type)) {
            throw new Error('access page: counts_by_type required');
        }
        const countsByType = summary.counts_by_type;
        return html`
            <div class="summary">
                <button
                    type="button"
                    class="chip"
                    aria-pressed=${ui.sourceFilter === '' && ui.grantTypeFilter === '' ? 'true' : 'false'}
                    @click=${() => this._ui.resetGrantFilters(null)}
                >${this.t('access_page.summary_explicit', { count: explicitCount })}</button>
                ${summary.company_visible ? html`
                    <span class="chip">${this.t('access_page.summary_company_visible')}</span>
                ` : nothing}
                <button
                    type="button"
                    class="chip"
                    aria-pressed=${ui.sourceFilter === 'group' ? 'true' : 'false'}
                    @click=${() => this._ui.setSourceFilter({
                        sourceFilter: ui.sourceFilter === 'group' ? '' : 'group',
                    })}
                >${this.t('access_page.summary_groups', { count: groupCount })}</button>
                ${Object.keys(countsByType).map((typeName) => html`
                    <button
                        type="button"
                        class="chip"
                        aria-pressed=${ui.grantTypeFilter === typeName ? 'true' : 'false'}
                        @click=${() => this._ui.setGrantTypeFilter({
                            grantTypeFilter: ui.grantTypeFilter === typeName ? '' : typeName,
                        })}
                    >${this.t(`access_page.type_${typeName}`)} · ${countsByType[typeName]}</button>
                `)}
            </div>
        `;
    }

    _renderGrantList() {
        if (this._busy()) {
            return html`
                <div class="skeleton-row"></div>
                <div class="skeleton-row"></div>
                <div class="skeleton-row"></div>
                <div class="skeleton-row"></div>
                <div class="skeleton-row"></div>
                <div class="skeleton-row"></div>
            `;
        }
        const ui = readExplorerUi(this._ui.value);
        const payload = ui.mode === 'people' ? this._byUser.lastResult : this._byObject.lastResult;
        const error = ui.mode === 'people' ? this._byUser.error : this._byObject.error;
        if (error) {
            return html`<div class="empty">${this.t('access_page.load_error')}</div>`;
        }
        const rows = this._currentRows();
        if (payload === null || payload === undefined) {
            return nothing;
        }
        if (!isPlainRecord(payload)) {
            throw new Error('access page: grant payload must be an object');
        }
        if (rows.length === 0) {
            return this._renderEmptyGrants(payload);
        }
        return html`
            <div class="grant-list">
                ${rows.map((row: Record<string, unknown>) => this._renderGrantRow(row))}
            </div>
        `;
    }

    _renderEmptyGrants(payload: Record<string, unknown>) {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'people') {
            return html`
                <div class="empty">
                    <div class="empty-title">${this.t('access_page.empty_user_title')}</div>
                    <div>${this.t('access_page.empty_user_description')}</div>
                    ${payload.company_visible ? html`
                        <div class="summary">
                            <span class="chip">${this.t('access_page.summary_company_visible')}</span>
                        </div>
                    ` : nothing}
                </div>
            `;
        }
        if (payload.company_visible) {
            return html`
                <div class="empty">
                    <div class="empty-title">${this.t('access_page.empty_object_company_title')}</div>
                    <div>${this.t('access_page.empty_object_company_description')}</div>
                </div>
            `;
        }
        return html`
            <div class="empty">
                <div class="empty-title">${this.t('access_page.empty_object_title')}</div>
                <div>${this.t('access_page.empty_object_description')}</div>
            </div>
        `;
    }

    _renderGrantRow(row: Record<string, unknown>) {
        const ui = readExplorerUi(this._ui.value);
        const objectType = requireRowString(row, 'object_type');
        const objectKey = requireRowString(row, 'object_key');
        const icon = this._typeIcon(objectType);
        const whyEnabled = this._whyEnabled(row);
        const href = typeof row.href === 'string' ? row.href : '';
        const manageHref = typeof row.manage_href === 'string' ? row.manage_href : '';
        return html`
            <div
                class="grant-row"
                data-why=${whyEnabled ? 'true' : 'false'}
                @click=${whyEnabled ? () => this._openWhy(row) : undefined}
            >
                <platform-icon name=${icon} size="18"></platform-icon>
                <div class="grant-main">
                    <div class="grant-title-row">
                        ${ui.mode === 'objects' && row.subject_kind === 'user'
                            ? html`<platform-user-chip user-id=${row.subject_id} size="sm"></platform-user-chip>`
                            : html`<div class="grant-title">${
                                ui.mode === 'people'
                                    ? this._rowTitle(row)
                                    : this._groupLabel(row.subject_id)
                            }</div>`}
                        <span class="relation-chip">${this.t(`access_page.relation_${row.relation}`)}</span>
                    </div>
                    <div class="grant-sub">
                        ${this.t(`access_page.type_${row.object_type}`)}
                        ${row.namespace ? html` · ${row.namespace}` : nothing}
                        · ${this.t(`access_page.source_${row.grant_source}`)}
                    </div>
                    ${row.title_status !== 'loaded' && ui.mode === 'people' ? html`
                        <button
                            type="button"
                            class="id-btn"
                            @click=${(e: Event) => {
                                e.stopPropagation();
                                this._copyObjectId(row.object_type, row.object_key);
                            }}
                        >${row.object_type}:${row.object_key}</button>
                    ` : nothing}
                </div>
                <div class="grant-actions" @click=${(e: Event) => e.stopPropagation()}>
                    ${href !== '' ? html`
                        <a class="detail-open" href=${href}>${this.t('access_page.action_open')}</a>
                    ` : nothing}
                    ${manageHref !== '' ? html`
                        <a class="detail-open" href=${manageHref}>${this.t('access_page.action_manage')}</a>
                    ` : nothing}
                    ${ui.mode === 'people' ? html`
                        <platform-button
                            variant="ghost"
                            density="dense"
                            @click=${() => this._selectObject(objectType, objectKey)}
                        >${this.t('access_page.action_inspect_object')}</platform-button>
                    ` : row.subject_kind === 'user' ? html`
                        <platform-button
                            variant="ghost"
                            density="dense"
                            @click=${() => this._selectUser(row.subject_id)}
                        >${this.t('access_page.action_inspect_user')}</platform-button>
                    ` : nothing}
                    ${row.can_revoke === true ? html`
                        <platform-button
                            variant="ghost"
                            danger
                            density="dense"
                            @click=${() => this._revoke(row)}
                        >${this.t('access_page.action_revoke')}</platform-button>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _whyObjectTitle() {
        const ui = readExplorerUi(this._ui.value);
        if (ui.mode === 'objects' && isPlainRecord(this._byObject.lastResult)) {
            return this._hitTitle(this._byObject.lastResult);
        }
        const payload = this._byUser.lastResult;
        const items = resultItems(payload);
        if (items === null) {
            return this.t('access_page.title_missing');
        }
        const match = items.find((row) => (
            row.object_type === ui.whyObjectType && row.object_key === ui.whyObjectKey
        ));
        if (!match) {
            return this.t('access_page.title_missing');
        }
        return this._rowTitle(match);
    }

    _renderWhyDrawer() {
        const ui = readExplorerUi(this._ui.value);
        const result = this._why.lastResult;
        const why = isPlainRecord(result) ? result : null;
        return html`
            <aside class="why-drawer">
                <div class="detail-head">
                    <div class="detail-title">${this.t('access_page.why_title')}</div>
                    <platform-button
                        variant="ghost"
                        density="dense"
                        @click=${() => this._ui.closeWhy(null)}
                    >${this.t('access_page.why_close')}</platform-button>
                </div>
                <div class="why-meta">
                    <platform-user-chip user-id=${ui.whyUserId} size="sm"></platform-user-chip>
                    <div class="grant-title">${this._whyObjectTitle()}</div>
                    <platform-button
                        variant="ghost"
                        density="dense"
                        @click=${() => this._copyObjectId(ui.whyObjectType, ui.whyObjectKey)}
                    >${this.t('access_page.why_copy_id')}</platform-button>
                </div>
                ${this._why.busy && why === null
                    ? html`<glass-spinner></glass-spinner>`
                    : this._why.error
                        ? html`<div class="empty">${this.t('access_page.why_error')}</div>`
                        : why
                            ? html`
                                <div class="why-item">
                                    ${why.allowed
                                        ? this.t('access_page.why_allowed')
                                        : this.t('access_page.why_denied')}
                                </div>
                                ${(Array.isArray(why.reasons) ? why.reasons : []).map((reason: string) => html`
                                    <div class="why-item">${this.t(`access_page.why_${reason}`)}</div>
                                `)}
                            `
                            : html`<div class="empty">${this.t('access_page.why_empty')}</div>`}
            </aside>
        `;
    }
}

customElements.define('frontend-access-page', FrontendAccessPage);
