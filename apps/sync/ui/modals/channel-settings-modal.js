/**
 * Настройки канала: участники, массовое добавление из компании.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncStore } from '../store/sync.store.js';
import { modalShellStyles } from '@platform/lib/platform-element/styles.js';

export class ChannelSettingsModal extends PlatformElement {
    static properties = {
        open: { type: Boolean },
        channel: { type: Object },
        createMode: { type: Boolean },
        _members: { state: true },
        _companyMembers: { state: true },
        _search: { state: true },
        _pickOpen: { state: true },
        _selectedForAdd: { state: true },
        _loading: { state: true },
        _adding: { state: true },
        _error: { state: true },
        _editName: { state: true },
        _editAvatarUrl: { state: true },
        _savingProfile: { state: true },
        _savingMute: { state: true },
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
                background: rgba(0, 0, 0, 0.45);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
            }

            .modal {
                width: 100%;
                max-width: 480px;
                max-height: min(85vh, 640px);
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-5);
                display: flex;
                flex-direction: column;
                min-height: 0;
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-4);
            }

            .modal-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: calc(-1 * var(--space-3));
                margin-bottom: var(--space-4);
            }

            .field {
                margin-bottom: var(--space-3);
            }

            .field-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
                display: block;
            }

            .field-input {
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

            .field-input:focus {
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

            .section-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }

            .member-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
            }

            .member-row-main {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1;
            }

            .member-row:last-child {
                border-bottom: none;
            }

            .user-avatar {
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
            }

            .user-avatar-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .user-avatar-initials {
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                font-weight: var(--font-semibold);
                color: #fff;
                letter-spacing: 0.02em;
            }

            .member-name {
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }

            .member-sub {
                color: var(--text-tertiary);
                font-size: 10px;
                margin-top: 2px;
            }

            .role-pill {
                font-size: 10px;
                padding: 2px 6px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

            .scroll-list {
                max-height: 160px;
                overflow-y: auto;
                margin-bottom: var(--space-3);
            }

            .toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
            }

            .toolbar .btn {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .toolbar .btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .toolbar .btn-primary {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .toolbar .btn-primary:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: var(--space-5);
            }

            .actions .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .actions .btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .actions .btn-primary {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-medium);
            }

            .actions .btn-primary:hover:not(:disabled) {
                background: var(--accent);
                color: white;
            }

            .actions .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .search {
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
                font-family: inherit;
                outline: none;
                box-sizing: border-box;
                margin-bottom: var(--space-2);
            }

            .search:focus {
                border-color: var(--accent);
            }

            .pick-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-xs);
            }

            .pick-row-text {
                min-width: 0;
                flex: 1;
            }

            .pick-row:hover {
                background: var(--glass-solid-subtle);
            }

            .pick-row input {
                margin-top: 2px;
            }

            .pick-scroll {
                max-height: 220px;
                overflow-y: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-3);
            }

            .error {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-radius: var(--radius-lg);
                padding: var(--space-2) var(--space-3);
                color: rgb(239, 68, 68);
                font-size: var(--text-xs);
                margin-bottom: var(--space-3);
            }

            .members-block {
                margin-top: var(--space-2);
            }

            .file-input {
                display: none;
            }

            .upload-img-btn {
                margin-top: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .upload-img-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.channel = null;
        this.createMode = false;
        this._members = [];
        this._companyMembers = { list: [], loading: false };
        this._search = '';
        this._pickOpen = false;
        this._selectedForAdd = {};
        this._loading = false;
        this._adding = false;
        this._error = null;
        this._editName = '';
        this._editAvatarUrl = '';
        this._savingProfile = false;
        this._savingMute = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsub = SyncStore.subscribe((state) => {
            this._companyMembers = state.companyMembers;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsub?.();
    }

    updated(changed) {
        const ch = this.channel;
        const hasChannel = Boolean(
            ch && (this.createMode || (typeof ch.id === 'string' && ch.id !== '')),
        );
        const canEdit = this.open && hasChannel;
        if (changed.has('open') && canEdit) {
            if (!this.createMode && ch?.id) {
                this._loadMembers();
            }
            this._syncEditFromChannel();
        }
        if (changed.has('channel') && canEdit) {
            if (!this.createMode && ch?.id) {
                this._loadMembers();
            }
            this._syncEditFromChannel();
        }
        if (changed.has('createMode') && this.open && ch && this.createMode) {
            this._syncEditFromChannel();
        }
    }

    _syncEditFromChannel() {
        const ch = this.channel;
        if (!ch) {
            return;
        }
        this._editName = typeof ch.name === 'string' ? ch.name : '';
        this._editAvatarUrl = typeof ch.avatar_url === 'string' ? ch.avatar_url : '';
    }

    async _loadMembers() {
        const channelId = this.channel?.id;
        if (typeof channelId !== 'string' || channelId === '') {
            return;
        }
        this._loading = true;
        this._error = null;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const rows = await syncApi.getChannelMembers(channelId);
            if (!Array.isArray(rows)) {
                throw new Error('Ожидался массив участников канала.');
            }
            this._members = rows;
        } catch (e) {
            this._error = e instanceof Error ? e.message : String(e);
        } finally {
            this._loading = false;
        }
    }

    _close() {
        this._pickOpen = false;
        this._selectedForAdd = {};
        this._search = '';
        this._error = null;
        this._savingProfile = false;
        this.dispatchEvent(new CustomEvent('close', { bubbles: true, composed: true }));
    }

    async _pickAvatarFile(e) {
        const input = e.currentTarget;
        const files = input.files;
        if (!files || files.length === 0) return;
        const file = files[0];
        input.value = '';
        const syncApi = ServiceRegistry.get('syncApi');
        const res = await syncApi.uploadFile(file);
        if (typeof res?.file_id !== 'string' || res.file_id === '' || typeof res?.url !== 'string' || res.url === '') {
            throw new Error('Некорректный ответ загрузки файла (нет file_id или url).');
        }
        this._editAvatarUrl = res.url;
    }

    async _createChannel() {
        const ch = this.channel;
        if (!ch) {
            throw new Error('Канал не выбран.');
        }
        const spaceId = ch.space_id;
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error('Сначала выбери пространство слева.');
        }
        const name = this._editName.trim();
        if (!name) {
            throw new Error('Имя канала обязательно.');
        }
        this._savingProfile = true;
        this._error = null;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const created = await syncApi.createChannel(spaceId, name);
            const url = this._editAvatarUrl.trim();
            if (url !== '') {
                await syncApi.updateChannel(created.id, {
                    name,
                    avatar_url: url,
                });
            }
            await SyncStore.loadChannels(syncApi);
            SyncStore.sanitizeChatSelectionAfterLoad();
            await SyncStore.selectChannelAndLoadMessages(syncApi, spaceId, created.id);
            this._close();
        } finally {
            this._savingProfile = false;
        }
    }

    async _toggleMute(e) {
        const ch = this.channel;
        if (!ch?.id) {
            return;
        }
        const target = e.target;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        const next = Boolean(target.checked);
        this._savingMute = true;
        this._error = null;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const updated = await syncApi.patchChannelNotificationSettings(ch.id, {
                notifications_muted: next,
            });
            SyncStore.mergeChannel(updated);
            this.channel = updated;
        } catch (err) {
            this._error = err instanceof Error ? err.message : String(err);
            target.checked = !next;
        } finally {
            this._savingMute = false;
        }
    }

    async _saveChannelProfile() {
        const ch = this.channel;
        if (!ch?.id) {
            throw new Error('Канал не выбран.');
        }
        const name = this._editName.trim();
        if (!name) {
            throw new Error('Имя канала обязательно.');
        }
        this._savingProfile = true;
        this._error = null;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const url = this._editAvatarUrl.trim();
            await syncApi.updateChannel(ch.id, {
                name,
                avatar_url: url === '' ? null : url,
            });
            await SyncStore.loadChannels(syncApi);
            this._close();
        } finally {
            this._savingProfile = false;
        }
    }

    _companyMember(userId) {
        const list = this._companyMembers.list;
        if (!Array.isArray(list)) return null;
        return list.find(x => x.user_id === userId) ?? null;
    }

    _displayName(userId) {
        const m = this._companyMember(userId);
        if (m && typeof m.name === 'string' && m.name.trim() !== '') {
            return m.name;
        }
        return userId;
    }

    _hueFromUserId(userId) {
        let h = 0;
        for (let i = 0; i < userId.length; i++) {
            h = (h * 31 + userId.charCodeAt(i)) >>> 0;
        }
        return h % 360;
    }

    _renderUserAvatar(userId, labelFallback) {
        const m = this._companyMember(userId);
        const url = m?.avatar_url;
        const label = typeof labelFallback === 'string' && labelFallback.trim() !== ''
            ? labelFallback
            : userId;
        if (typeof url === 'string' && url.trim() !== '') {
            return html`<img class="user-avatar-img" src=${url} alt="" />`;
        }
        const initial = (label.trim().slice(0, 1) || '?').toUpperCase();
        const hue = this._hueFromUserId(userId);
        return html`
            <span class="user-avatar-initials" style=${`background:hsl(${hue} 48% 42%)`}>${initial}</span>
        `;
    }

    _memberIds() {
        return new Set(this._members.map(r => r.user_id));
    }

    _candidatesForAdd() {
        const inChannel = this._memberIds();
        const list = this._companyMembers.list;
        if (!Array.isArray(list)) return [];
        const q = this._search.trim().toLowerCase();
        return list.filter((m) => {
            if (inChannel.has(m.user_id)) return false;
            if (!q) return true;
            const name = typeof m.name === 'string' ? m.name.toLowerCase() : '';
            const id = typeof m.user_id === 'string' ? m.user_id.toLowerCase() : '';
            return name.includes(q) || id.includes(q);
        });
    }

    _togglePick(uid) {
        const next = { ...this._selectedForAdd };
        if (next[uid]) {
            delete next[uid];
        } else {
            next[uid] = true;
        }
        this._selectedForAdd = next;
    }

    _selectedCount() {
        return Object.keys(this._selectedForAdd).length;
    }

    async _submitAdds() {
        const channelId = this.channel?.id;
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        const ids = Object.keys(this._selectedForAdd);
        if (ids.length === 0) return;
        this._adding = true;
        this._error = null;
        const syncApi = ServiceRegistry.get('syncApi');
        for (const userId of ids) {
            await syncApi.addChannelMember(channelId, userId, 'member');
        }
        await SyncStore.loadChannels(syncApi);
        this._selectedForAdd = {};
        this._pickOpen = false;
        this._search = '';
        await this._loadMembers();
        this._adding = false;
    }

    render() {
        if (!this.open || !this.channel) return html``;

        const ch = this.channel;
        const createMode = this.createMode;
        const title = createMode ? 'Создать канал' : 'Настройки канала';
        const candidates = this._candidatesForAdd();
        const pickCount = this._selectedCount();
        const primaryLabel = createMode
            ? (this._savingProfile ? 'Создаём…' : 'Создать')
            : (this._savingProfile ? 'Сохранение…' : 'Сохранить');

        const metaLine = createMode
            ? (typeof ch.space_id === 'string' && ch.space_id !== ''
                ? `Пространство: ${ch.space_id.slice(0, 8)}…`
                : 'Выбери пространство в списке слева.')
            : `${typeof ch.name === 'string' && ch.name.trim() !== '' ? ch.name : ch.id} · ${ch.type}${ch.space_id ? ` · пространство ${ch.space_id.slice(0, 8)}…` : ''}`;

        const av = this._editAvatarUrl.trim();

        return html`
            <div class="backdrop" @click=${(e) => { if (e.target === e.currentTarget) this._close(); }}>
                <div class="modal" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-title">${title}</div>
                    <div class="modal-meta">${metaLine}</div>

                    ${this._error ? html`<div class="error">${this._error}</div>` : ''}

                    ${!createMode && typeof ch.id === 'string' && ch.id !== ''
                        ? html`
                            <div class="field">
                                <label class="field-label">Уведомления</label>
                                <label
                                    style="display:flex;align-items:center;gap:var(--space-2);font-size:var(--text-sm);cursor:pointer;color:var(--text-primary);"
                                >
                                    <input
                                        type="checkbox"
                                        .checked=${Boolean(ch.notifications_muted)}
                                        @change=${(e) => this._toggleMute(e)}
                                        ?disabled=${this._savingMute}
                                    />
                                    Не беспокоить (без уведомлений о новых сообщениях)
                                </label>
                            </div>
                        `
                        : ''}

                    <div class="field">
                        <label class="field-label">Название</label>
                        <input
                            type="text"
                            class="field-input"
                            placeholder="Название канала"
                            .value=${this._editName}
                            @input=${(e) => {
                            this._editName = e.target.value;
                        }}
                        />
                    </div>

                    <div class="field">
                        <label class="field-label">Аватар</label>
                        ${av
        ? html`<img class="avatar-preview" src=${av} alt="" />`
        : ''}
                        <input
                            type="file"
                            class="file-input"
                            id="ch-profile-avatar-file"
                            accept="image/*"
                            @change=${(e) => {
            this._pickAvatarFile(e).catch((err) => {
                this._error = err instanceof Error ? err.message : String(err);
            });
        }}
                        />
                        <button
                            type="button"
                            class="upload-img-btn"
                            @click=${() => {
            const el = this.shadowRoot?.getElementById('ch-profile-avatar-file');
            if (el) el.click();
        }}
                        >Загрузить изображение</button>
                    </div>

                    ${createMode ? '' : html`
                    <div class="members-block">
                    <div class="section-label">Участники</div>
                    ${this._loading
                        ? html`<div class="modal-meta">Загрузка…</div>`
                        : html`
                            <div class="scroll-list">
                                ${this._members.map((r) => html`
                                    <div class="member-row">
                                        <div class="member-row-main">
                                            <div class="user-avatar">
                                                ${this._renderUserAvatar(r.user_id, this._displayName(r.user_id))}
                                            </div>
                                            <div>
                                                <div class="member-name">${this._displayName(r.user_id)}</div>
                                                <div class="member-sub">${r.user_id}</div>
                                            </div>
                                        </div>
                                        <span class="role-pill">${r.role}</span>
                                    </div>
                                `)}
                            </div>
                        `}

                    <div class="toolbar">
                        <button
                            type="button"
                            class="btn btn-primary"
                            ?disabled=${this._adding}
                            @click=${() => { this._pickOpen = !this._pickOpen; }}
                        >${this._pickOpen ? 'Скрыть добавление' : 'Добавить участников'}</button>
                    </div>

                    ${this._pickOpen ? html`
                        <input
                            type="search"
                            class="search"
                            placeholder="Поиск по имени или id…"
                            .value=${this._search}
                            @input=${(e) => { this._search = e.target.value; }}
                        />
                        <div class="pick-scroll">
                            ${candidates.length === 0
                                ? html`<div class="modal-meta" style="padding:var(--space-3)">Нет пользователей для добавления.</div>`
                                : candidates.map((m) => html`
                                    <label class="pick-row">
                                        <input
                                            type="checkbox"
                                            .checked=${Boolean(this._selectedForAdd[m.user_id])}
                                            @change=${() => this._togglePick(m.user_id)}
                                        />
                                        <div class="user-avatar">
                                            ${this._renderUserAvatar(m.user_id, m.name ?? m.user_id)}
                                        </div>
                                        <span class="pick-row-text">
                                            <div class="member-name">${m.name ?? m.user_id}</div>
                                            <div class="member-sub">${m.user_id}</div>
                                        </span>
                                    </label>
                                `)}
                        </div>
                        <div class="toolbar">
                            <button
                                type="button"
                                class="btn btn-primary"
                                ?disabled=${pickCount === 0 || this._adding}
                                @click=${() => {
            this._submitAdds().catch((err) => {
                const text = err instanceof Error ? err.message : String(err);
                this._error = text;
                this._adding = false;
            });
        }}
                            >Добавить выбранных (${pickCount})</button>
                        </div>
                    ` : ''}
                    </div>
                    `}

                    <div class="actions">
                        <button type="button" class="btn" @click=${this._close}>Отмена</button>
                        <button
                            type="button"
                            class="btn btn-primary"
                            ?disabled=${this._savingProfile}
                            @click=${() => {
            const run = createMode
                ? this._createChannel()
                : this._saveChannelProfile();
            run.catch((err) => {
                this._error = err instanceof Error ? err.message : String(err);
                this._savingProfile = false;
            });
        }}
                        >${primaryLabel}</button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('channel-settings-modal', ChannelSettingsModal);
