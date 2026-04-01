/**
 * Пространство: создание и редактирование (имя, описание, аватар).
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import '@platform/lib/components/platform-switch.js';
import { SyncStore } from '../store/sync.store.js';

export class SpaceSettingsModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _spaceId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _avatarUrl: { state: true },
        _namespace: { state: true },
        _autoExportTranscriptToCrm: { state: true },
        _autoExportSummaryToCrm: { state: true },
        _crmNamespaces: { state: true },
        _crmNamespacesLoading: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        formStyles,
        css`
            .field {
                margin-bottom: var(--space-3);
            }

            .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
                display: block;
            }

            .input {
                width: 100%;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                outline: none;
                box-sizing: border-box;
                transition: border-color var(--duration-fast);
            }

            .input:focus {
                border-color: var(--accent);
            }

            .avatar-preview {
                width: 64px;
                height: 64px;
                border-radius: 50%;
                object-fit: cover;
                border: 1px solid var(--glass-border-subtle);
                display: block;
                margin-bottom: var(--space-2);
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                justify-content: flex-end;
                gap: var(--space-2);
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .btn-primary {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-medium);
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--accent);
                color: white;
            }

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .file-input {
                display: none;
            }

            .switch-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }

            .switch-row:last-child {
                margin-bottom: 0;
            }

            .switch-label {
                font-size: var(--text-sm);
                color: var(--text-primary);
                line-height: var(--leading-normal);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this._spaceId = null;
        this._syncedForSpaceId = null;
        this._name = '';
        this._description = '';
        this._avatarUrl = '';
        this._namespace = '';
        this._autoExportTranscriptToCrm = false;
        this._autoExportSummaryToCrm = false;
        this._crmNamespaces = [];
        this._crmNamespacesLoading = false;
        this._saving = false;
        this._lastModalOpenTag = null;
        this.open = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe((state) => {
            const create = state.ui.spaceSettingsCreate;
            const nextId = state.ui.spaceSettingsSpaceId;
            if (create) {
                if (this._syncedForSpaceId !== '__create__') {
                    this._syncedForSpaceId = '__create__';
                    this._spaceId = null;
                    this._name = '';
                    this._description = '';
                    this._avatarUrl = '';
                    this._namespace = '';
                    this._autoExportTranscriptToCrm = false;
                    this._autoExportSummaryToCrm = false;
                }
            } else if (nextId === null) {
                this._syncedForSpaceId = null;
                this._spaceId = null;
            } else if (nextId === this._syncedForSpaceId) {
                this._spaceId = nextId;
            } else {
                const sp = state.spaces.list.find((x) => x.id === nextId);
                if (!sp) {
                    SyncStore.closeSpaceSettings();
                } else {
                    this._syncedForSpaceId = nextId;
                    this._spaceId = nextId;
                    this._name = typeof sp.name === 'string' ? sp.name : '';
                    this._description = typeof sp.description === 'string' ? sp.description : '';
                    this._avatarUrl = typeof sp.avatar_url === 'string' ? sp.avatar_url : '';
                    this._namespace = typeof sp.namespace === 'string' ? sp.namespace : '';
                    this._autoExportTranscriptToCrm = sp.auto_export_transcript_to_crm === true;
                    this._autoExportSummaryToCrm = sp.auto_export_summary_to_crm === true;
                }
            }

            const openTag = `${create ? '1' : '0'}:${nextId ?? ''}`;
            if (openTag !== this._lastModalOpenTag) {
                this._lastModalOpenTag = openTag;
                this.requestUpdate();
            }

            const show = create || (typeof nextId === 'string' && nextId !== '');
            if (this.open !== show) {
                this.open = show;
            }
        });
        const ui0 = SyncStore.state.ui;
        const show0 = ui0.spaceSettingsCreate
            || (typeof ui0.spaceSettingsSpaceId === 'string' && ui0.spaceSettingsSpaceId !== '');
        if (this.open !== show0) {
            this.open = show0;
        }
        this._loadCrmNamespaces().catch((err) => {
            const text = err instanceof Error ? err.message : String(err);
            this.error(text);
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    close() {
        SyncStore.closeSpaceSettings();
        super.close();
    }

    render() {
        const ui = SyncStore.state.ui;
        const isCreate = ui.spaceSettingsCreate;
        const id = this._spaceId;
        if (!isCreate && (typeof id !== 'string' || id === '')) {
            return html``;
        }
        return super.render();
    }

    _onCancel() {
        this.close();
    }

    async _pickFile(e) {
        const input = e.currentTarget;
        const files = input.files;
        if (!files || files.length === 0) return;
        const file = files[0];
        input.value = '';
        const syncApi = this.services.get('syncApi');
        const res = await syncApi.uploadFile(file);
        if (typeof res?.file_id !== 'string' || res.file_id === '' || typeof res?.url !== 'string' || res.url === '') {
            throw new Error(this._tp('space_settings.err_upload'));
        }
        this._avatarUrl = res.url;
    }

    async _submit() {
        const create = SyncStore.state.ui.spaceSettingsCreate;
        const name = this._name.trim();
        if (!name) {
            throw new Error(this._tp('space_settings.err_name_required'));
        }
        this._saving = true;
        try {
            const syncApi = this.services.get('syncApi');
            const url = this._avatarUrl.trim();
            const description = this._description.trim() || null;
            const namespace = this._namespace.trim();
            const autoExportTranscriptToCrm = this._autoExportTranscriptToCrm;
            const autoExportSummaryToCrm = this._autoExportSummaryToCrm;
            if ((autoExportTranscriptToCrm || autoExportSummaryToCrm) && namespace === '') {
                throw new Error(this._tp('space_settings.err_export_namespace'));
            }
            if (create) {
                const created = await syncApi.createSpace(name, description);
                if (
                    url !== ''
                    || namespace !== ''
                    || autoExportTranscriptToCrm
                    || autoExportSummaryToCrm
                ) {
                    await syncApi.updateSpace(created.id, {
                        name,
                        description,
                        avatar_url: url,
                        namespace: namespace === '' ? null : namespace,
                        auto_export_transcript_to_crm: autoExportTranscriptToCrm,
                        auto_export_summary_to_crm: autoExportSummaryToCrm,
                    });
                }
                await SyncStore.loadSpaces(syncApi);
                SyncStore.selectSpace(created.id);
                this.close();
                return;
            }
            const id = this._spaceId;
            if (typeof id !== 'string' || id === '') {
                throw new Error(this._tp('space_settings.err_not_selected'));
            }
            await syncApi.updateSpace(id, {
                name,
                description,
                avatar_url: url === '' ? null : url,
                namespace: namespace === '' ? null : namespace,
                auto_export_transcript_to_crm: autoExportTranscriptToCrm,
                auto_export_summary_to_crm: autoExportSummaryToCrm,
            });
            await SyncStore.loadSpaces(syncApi);
            this.close();
        } finally {
            this._saving = false;
        }
    }

    renderHeader() {
        const ui = SyncStore.state.ui;
        return ui.spaceSettingsCreate
            ? this._tp('space_settings.header_create')
            : this._tp('space_settings.header_edit');
    }

    renderBody() {
        const ui = SyncStore.state.ui;
        const isCreate = ui.spaceSettingsCreate;
        const id = this._spaceId;
        if (!isCreate && (typeof id !== 'string' || id === '')) {
            return html``;
        }
        const descLabel = isCreate
            ? this._tp('space_settings.desc_optional')
            : this._tp('space_settings.desc');
        const av = this._avatarUrl.trim();
        return html`
            <div class="field">
                <label class="label">${this._tp('space_settings.field_name')}</label>
                <input
                    class="input"
                    .value=${this._name}
                    @input=${(e) => {
                        this._name = e.target.value;
                    }}
                />
            </div>

            <div class="field">
                <label class="label">${descLabel}</label>
                <input
                    class="input"
                    .value=${this._description}
                    @input=${(e) => {
                        this._description = e.target.value;
                    }}
                />
            </div>

            <div class="field">
                <label class="label">${this._tp('space_settings.field_avatar')}</label>
                ${av ? html`<img class="avatar-preview" src=${av} alt="" />` : ''}
                <input
                    type="file"
                    class="file-input"
                    id="space-avatar-file"
                    accept="image/*"
                    @change=${(e) => {
                        this._pickFile(e).catch((err) => {
                            const errMsg = err instanceof Error ? err.message : String(err);
                            this.error(errMsg);
                        });
                    }}
                />
                <button
                    type="button"
                    class="btn"
                    style="margin-top:var(--space-2)"
                    @click=${() => {
                        const el = this.shadowRoot?.getElementById('space-avatar-file');
                        if (el) el.click();
                    }}
                >
                    ${this._tp('space_settings.upload_image')}
                </button>
            </div>

            <div class="field">
                <label class="label">${this._tp('space_settings.namespace_label')}</label>
                <input
                    class="input"
                    list="space-settings-namespace-options"
                    .value=${this._namespace}
                    @input=${(e) => {
                        this._namespace = e.target.value;
                    }}
                />
                <datalist id="space-settings-namespace-options">
                    ${this._crmNamespaces.map((ns) => html`
                        <option value=${ns.name}>${ns.name}</option>
                    `)}
                </datalist>
                ${this._crmNamespacesLoading ? html`
                    <div class="label" style="margin-top:8px;">${this._tp('space_settings.namespace_loading')}</div>
                ` : ''}
            </div>

            <div class="field">
                <div class="switch-row">
                    <span class="switch-label">${this._tp('space_settings.auto_export_transcript')}</span>
                    <platform-switch
                        .checked=${this._autoExportTranscriptToCrm}
                        @change=${(e) => {
                            this._autoExportTranscriptToCrm = e.detail.value === true;
                        }}
                    ></platform-switch>
                </div>
                <div class="switch-row">
                    <span class="switch-label">${this._tp('space_settings.auto_export_summary')}</span>
                    <platform-switch
                        .checked=${this._autoExportSummaryToCrm}
                        @change=${(e) => {
                            this._autoExportSummaryToCrm = e.detail.value === true;
                        }}
                    ></platform-switch>
                </div>
            </div>
        `;
    }

    async _loadCrmNamespaces() {
        this._crmNamespacesLoading = true;
        try {
            const syncApi = this.services.get('syncApi');
            const rows = await syncApi.getCrmNamespaces();
            this._crmNamespaces = rows;
        } finally {
            this._crmNamespacesLoading = false;
        }
    }

    renderFooter() {
        const ui = SyncStore.state.ui;
        const isCreate = ui.spaceSettingsCreate;
        const id = this._spaceId;
        if (!isCreate && (typeof id !== 'string' || id === '')) {
            return html``;
        }
        const primaryLabel = isCreate
            ? (this._saving ? this._tp('space_settings.creating') : this._tp('space_settings.create'))
            : (this._saving ? this._tp('space_settings.saving') : this._tp('space_settings.save'));
        return html`
            <div class="actions">
                <button type="button" class="btn" @click=${this._onCancel}>${this._tp('chat_view.cancel')}</button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this._saving}
                    @click=${() => {
                        this._submit().catch((err) => {
                            const errMsg = err instanceof Error ? err.message : String(err);
                            this.error(errMsg);
                            this._saving = false;
                        });
                    }}
                >
                    ${primaryLabel}
                </button>
            </div>
        `;
    }
}

customElements.define('space-settings-modal', SpaceSettingsModal);
