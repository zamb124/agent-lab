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

export class ChannelSettingsModal extends PlatformElement {
    static properties = {
        open: { type: Boolean },
        channel: { type: Object },
        _members: { state: true },
        _companyMembers: { state: true },
        _search: { state: true },
        _pickOpen: { state: true },
        _selectedForAdd: { state: true },
        _loading: { state: true },
        _adding: { state: true },
        _error: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        formStyles,
        css`
            .backdrop {
                position: fixed;
                inset: 0;
                z-index: 60;
                background: rgba(0, 0, 0, 0.45);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
            }

            .modal {
                width: 100%;
                max-width: 440px;
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
                margin-bottom: var(--space-1);
            }

            .modal-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-4);
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

            .btn {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .btn-primary {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }

            .btn-primary:disabled {
                opacity: 0.45;
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

            .footer-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: auto;
                padding-top: var(--space-3);
            }

            .profile-input {
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

            .profile-input:focus {
                border-color: var(--accent);
            }

            .avatar-preview-ch {
                width: 56px;
                height: 56px;
                border-radius: 50%;
                object-fit: cover;
                border: 1px solid var(--glass-border-subtle);
                margin-bottom: var(--space-2);
            }

            .file-input {
                display: none;
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.channel = null;
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
        if (changed.has('open') && this.open && this.channel?.id) {
            this._loadMembers();
            this._syncEditFromChannel();
        }
        if (changed.has('channel') && this.open && this.channel?.id) {
            this._loadMembers();
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
        if (!res?.file?.storage_url) {
            throw new Error('Некорректный ответ загрузки файла (нет storage_url).');
        }
        this._editAvatarUrl = res.file.storage_url;
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
        const title = typeof ch.name === 'string' && ch.name.trim() !== '' ? ch.name : ch.id;
        const candidates = this._candidatesForAdd();
        const pickCount = this._selectedCount();

        return html`
            <div class="backdrop" @click=${(e) => { if (e.target === e.currentTarget) this._close(); }}>
                <div class="modal" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-title">${title}</div>
                    <div class="modal-meta">${ch.type}${ch.space_id ? ` · space: ${ch.space_id.slice(0, 8)}…` : ''}</div>

                    ${this._error ? html`<div class="error">${this._error}</div>` : ''}

                    <div class="section-label">Название и аватар</div>
                    ${this._editAvatarUrl.trim()
                        ? html`<img class="avatar-preview-ch" src=${this._editAvatarUrl.trim()} alt="" />`
                        : ''}
                    <input
                        type="text"
                        class="profile-input"
                        placeholder="Название канала"
                        .value=${this._editName}
                        @input=${(e) => {
                            this._editName = e.target.value;
                        }}
                    />
                    <input
                        type="text"
                        class="profile-input"
                        placeholder="URL аватара"
                        .value=${this._editAvatarUrl}
                        @input=${(e) => {
                            this._editAvatarUrl = e.target.value;
                        }}
                    />
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
                    <div class="toolbar">
                        <button
                            type="button"
                            class="btn"
                            @click=${() => {
                                const el = this.shadowRoot?.getElementById('ch-profile-avatar-file');
                                if (el) el.click();
                            }}
                        >Загрузить изображение</button>
                        <button
                            type="button"
                            class="btn btn-primary"
                            ?disabled=${this._savingProfile}
                            @click=${() => {
                                this._saveChannelProfile().catch((err) => {
                                    this._error = err instanceof Error ? err.message : String(err);
                                    this._savingProfile = false;
                                });
                            }}
                        >${this._savingProfile ? 'Сохранение…' : 'Сохранить'}</button>
                    </div>

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

                    <div class="footer-actions">
                        <button type="button" class="btn" @click=${this._close}>Закрыть</button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('channel-settings-modal', ChannelSettingsModal);
