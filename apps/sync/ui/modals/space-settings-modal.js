/**
 * Пространство: создание и редактирование (имя, описание, аватар).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { modalShellStyles } from '@platform/lib/platform-element/styles.js';
import { SyncStore } from '../store/sync.store.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';

export class SpaceSettingsModal extends PlatformElement {
    static properties = {
        _spaceId: { state: true },
        _name: { state: true },
        _description: { state: true },
        _avatarUrl: { state: true },
        _saving: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        formStyles,
        modalShellStyles,
        css`
            .backdrop {
                position: fixed;
                inset: 0;
                z-index: 55;
                background: rgba(0, 0, 0, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
            }

            .modal {
                width: 100%;
                max-width: 480px;
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-5);
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-4);
            }

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
                margin-top: var(--space-5);
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
        `,
    ];

    constructor() {
        super();
        this._spaceId = null;
        this._syncedForSpaceId = null;
        this._name = '';
        this._description = '';
        this._avatarUrl = '';
        this._saving = false;
        this._lastModalOpenTag = null;
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
                }
            }

            const openTag = `${create ? '1' : '0'}:${nextId ?? ''}`;
            if (openTag !== this._lastModalOpenTag) {
                this._lastModalOpenTag = openTag;
                this.requestUpdate();
            }
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _close() {
        SyncStore.closeSpaceSettings();
    }

    async _pickFile(e) {
        const input = e.currentTarget;
        const files = input.files;
        if (!files || files.length === 0) return;
        const file = files[0];
        input.value = '';
        const syncApi = ServiceRegistry.get('syncApi');
        const res = await syncApi.uploadFile(file);
        if (!res?.file?.storage_url) {
            throw new Error('Некорректный ответ загрузки файла (нет storage_url).');
        }
        this._avatarUrl = res.file.storage_url;
    }

    async _submit() {
        const create = SyncStore.state.ui.spaceSettingsCreate;
        const name = this._name.trim();
        if (!name) {
            throw new Error('Название пространства обязательно.');
        }
        this._saving = true;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const url = this._avatarUrl.trim();
            const description = this._description.trim() || null;
            if (create) {
                const created = await syncApi.createSpace(name, description);
                if (url !== '') {
                    await syncApi.updateSpace(created.id, {
                        name,
                        description,
                        avatar_url: url,
                    });
                }
                await SyncStore.loadSpaces(syncApi);
                SyncStore.selectSpace(created.id);
                this._close();
                return;
            }
            const id = this._spaceId;
            if (typeof id !== 'string' || id === '') {
                throw new Error('Пространство не выбрано.');
            }
            await syncApi.updateSpace(id, {
                name,
                description,
                avatar_url: url === '' ? null : url,
            });
            await SyncStore.loadSpaces(syncApi);
            this._close();
        } finally {
            this._saving = false;
        }
    }

    render() {
        const ui = SyncStore.state.ui;
        const isCreate = ui.spaceSettingsCreate;
        const id = this._spaceId;
        if (!isCreate && (typeof id !== 'string' || id === '')) {
            return html``;
        }

        const title = isCreate ? 'Создать пространство' : 'Настройки пространства';
        const primaryLabel = isCreate
            ? (this._saving ? 'Создаём…' : 'Создать')
            : (this._saving ? 'Сохранение…' : 'Сохранить');
        const descLabel = isCreate ? 'Описание (опционально)' : 'Описание';

        const av = this._avatarUrl.trim();
        return html`
            <div class="backdrop" @click=${this._close}>
                <div class="modal" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-title">${title}</div>

                    <div class="field">
                        <label class="label">Название</label>
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
                        <label class="label">Аватар (URL или файл)</label>
                        ${av
                            ? html`<img class="avatar-preview" src=${av} alt="" />`
                            : ''}
                        <input
                            class="input"
                            placeholder="https://..."
                            .value=${this._avatarUrl}
                            @input=${(e) => {
                                this._avatarUrl = e.target.value;
                            }}
                        />
                        <input
                            type="file"
                            class="file-input"
                            id="space-avatar-file"
                            accept="image/*"
                            @change=${(e) => {
                                this._pickFile(e).catch((err) => {
                                    const t = err instanceof Error ? err.message : String(err);
                                    this.error(t);
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
                            Загрузить изображение
                        </button>
                    </div>

                    <div class="actions">
                        <button type="button" class="btn" @click=${this._close}>Отмена</button>
                        <button
                            type="button"
                            class="btn btn-primary"
                            ?disabled=${this._saving}
                            @click=${() => {
                                this._submit().catch((err) => {
                                    const t = err instanceof Error ? err.message : String(err);
                                    this.error(t);
                                    this._saving = false;
                                });
                            }}
                        >
                            ${primaryLabel}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('space-settings-modal', SpaceSettingsModal);
