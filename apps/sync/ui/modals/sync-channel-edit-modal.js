/**
 * sync-channel-edit-modal — настройки канала: имя, аватар, флаги
 * (notifications mute, transcribe voice, speech-to-chat), список участников
 * + кнопка добавления.
 * Второе действие на превью: удалить загруженный аватар или сменить вариант
 * сгенерированного плейсхолдера (alohe).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveAvatarImageSrc } from '@platform/lib/utils/placeholder-avatar.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import { compressImageFileToJpeg } from '../_helpers/sync-avatar-image-compress.js';
import { syncChannelPlaceholderCollection } from '../_helpers/sync-channel-placeholder-collection.js';
import { resolveChannelTitle } from '../_helpers/sync-id-resolvers.js';

const FILE_DOWNLOAD_BASE = '/sync/api/v1/files/download';

export class SyncChannelEditModal extends PlatformFormModal {
    static modalKind = 'sync.channel_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _name: { state: true },
        _avatarDraftUrl: { state: true },
        /** @type {'unchanged' | 'removed' | 'replaced'} */
        _avatarIntent: { state: true },
        _muted: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
        _members: { state: true },
        /** Смена PNG из коллекции alohe при «обновить» для сгенерированного аватара. */
        _placeholderVariantNonce: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .members-list {
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
                border-radius: var(--radius-md);
                padding: var(--space-2);
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
            }
            .member-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) 0;
            }
            .add-members-icon-btn {
                margin-top: var(--space-2);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                padding: 0;
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.12));
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.06));
                color: var(--text-secondary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);
            }
            .add-members-icon-btn:hover {
                background: var(--glass-hover);
                color: var(--accent);
                border-color: color-mix(in srgb, var(--accent) 35%, transparent);
            }
            .add-members-icon-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .toggle-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) 0;
                border-bottom: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
            }
            .toggle-row:last-of-type {
                border-bottom: none;
                padding-bottom: 0;
            }
            .toggle-label {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                flex: 1;
                min-width: 0;
            }
            .toggle-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                line-height: 1.35;
            }
            .notifications-toggles {
                display: flex;
                flex-direction: column;
                margin-top: var(--space-1);
            }
            .notifications-toggles platform-switch {
                flex-shrink: 0;
                margin-top: 2px;
            }
            .avatar-name-row {
                display: flex;
                flex-direction: row;
                align-items: flex-start;
                gap: var(--space-4);
                flex-wrap: wrap;
            }
            .avatar-name-row__avatar {
                flex-shrink: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .avatar-name-row__name {
                flex: 1;
                min-width: 180px;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .avatar-editor {
                margin-top: 0;
            }
            .avatar-preview-wrap {
                position: relative;
                width: 96px;
                height: 96px;
                border-radius: var(--radius-md);
                overflow: hidden;
                flex-shrink: 0;
                background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.06));
                border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
            }
            .avatar-preview-img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .avatar-overlay-actions {
                position: absolute;
                right: 2px;
                bottom: 2px;
                display: flex;
                flex-direction: row;
                gap: 2px;
                z-index: 1;
            }
            .avatar-overlay-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 20px;
                height: 20px;
                padding: 0;
                border: none;
                border-radius: 4px;
                background: rgba(15, 23, 42, 0.55);
                color: #f8fafc;
                cursor: pointer;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
                transition: background var(--duration-fast), transform var(--duration-fast);
            }
            .avatar-overlay-btn:hover:not(:disabled) {
                background: rgba(15, 23, 42, 0.78);
            }
            .avatar-overlay-btn:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }
            .avatar-overlay-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .avatar-file-input {
                position: absolute;
                width: 0;
                height: 0;
                opacity: 0;
                pointer-events: none;
            }
        `,
    ];

    constructor() {
        super();
        this.channelId = '';
        this._name = '';
        this._avatarDraftUrl = '';
        this._avatarIntent = 'unchanged';
        /** @type {string} */
        this._initialAvatarUrl = '';
        this._muted = false;
        this._transcribe = false;
        this._speechToChat = false;
        this._hydrated = false;
        this._members = [];
        this._placeholderVariantNonce = 0;
        this._channels = this.useResource('sync/channels');
        this._channelUpdate = this.useOp('sync/channel_update');
        this._membersOp = this.useOp('sync/channel_members_list');
        this._notificationsOp = this.useOp('sync/channel_notifications_update');
        this._fileUpload = this.useOp('sync/file_upload');
    }

    async updated(changed) {
        super.updated?.(changed);
        if (changed.has('channelId')) {
            this._hydrated = false;
            this._initialAvatarUrl = '';
            this._avatarDraftUrl = '';
            this._avatarIntent = 'unchanged';
            this._members = [];
            this._placeholderVariantNonce = 0;
        }
        if (!this._hydrated && this.channelId) {
            const item = this._channels.items.find((c) => c.id === this.channelId);
            if (item) {
                this._name = typeof item.name === 'string' ? item.name : '';
                if (typeof item.avatar_url === 'string' && item.avatar_url !== '') {
                    this._initialAvatarUrl = item.avatar_url;
                    this._avatarDraftUrl = item.avatar_url;
                } else {
                    this._initialAvatarUrl = '';
                    this._avatarDraftUrl = '';
                }
                this._avatarIntent = 'unchanged';
                this._muted = item.notifications_muted === true;
                this._transcribe = item.transcribe_voice_messages === true;
                this._speechToChat = item.speech_to_chat_enabled === true;
                this._hydrated = true;
                await this._membersOp.run({ channel_id: this.channelId });
                const result = this._membersOp.lastResult;
                if (result && Array.isArray(result.items)) this._members = result.items;
                else if (Array.isArray(result)) this._members = result;
            }
        }
    }

    /**
     * @param {{ id: string, type: string }} item
     * @returns {{ kind: 'remote' | 'placeholder', src: string }}
     */
    _avatarPreviewResolve(item) {
        const coll = syncChannelPlaceholderCollection(item);
        const hasDraft =
            this._avatarIntent !== 'removed'
            && typeof this._avatarDraftUrl === 'string'
            && this._avatarDraftUrl !== '';
        const avatarUrl = hasDraft ? this._avatarDraftUrl : null;
        const seed = `${item.id}:${this._placeholderVariantNonce}`;
        return resolveAvatarImageSrc({ avatarUrl, seed, collection: coll });
    }

    /**
     * @param {{ id: string, type: string }} item
     * @returns {string}
     */
    _avatarPreviewSrc(item) {
        return this._avatarPreviewResolve(item).src;
    }

    _pickAvatarFile() {
        const input = this.renderRoot.querySelector('#sync-channel-avatar-file');
        if (input instanceof HTMLInputElement) input.click();
    }

    /**
     * @param {Event} e
     */
    async _onAvatarFileChange(e) {
        const target = e.target;
        if (!(target instanceof HTMLInputElement)) return;
        const files = target.files;
        target.value = '';
        if (!files || files.length === 0) return;
        const file = files[0];
        const item = this._channels.items.find((c) => c.id === this.channelId);
        if (!item || item.type === 'direct') return;
        try {
            const compressed = await compressImageFileToJpeg(file);
            const result = await this._fileUpload.run({
                file: compressed,
                purpose: 'channel_avatar',
            });
            if (
                result === null
                || typeof result !== 'object'
                || typeof result.file_id !== 'string'
                || result.file_id === ''
            ) {
                this.toast('sync:channel_settings.err_upload_response', { type: 'error' });
                return;
            }
            const url = `${FILE_DOWNLOAD_BASE}/${encodeURIComponent(result.file_id)}`;
            this._avatarDraftUrl = url;
            this._avatarIntent = 'replaced';
            this.isDirty = true;
        } catch {
            this.toast('sync:channel_settings.err_avatar_compress', { type: 'error' });
        }
    }

    _clearAvatar() {
        const item = this._channels.items.find((c) => c.id === this.channelId);
        if (!item || item.type === 'direct') return;
        this._avatarDraftUrl = '';
        this._avatarIntent = 'removed';
        this._placeholderVariantNonce = 0;
        this.isDirty = true;
    }

    /**
     * Другой PNG из той же коллекции (только превью; на сервере по-прежнему нет своего файла).
     */
    _refreshPlaceholderAvatar(e) {
        e.stopPropagation();
        const item = this._channels.items.find((c) => c.id === this.channelId);
        if (!item || item.type === 'direct') return;
        if (this._avatarPreviewResolve(item).kind !== 'placeholder') return;
        this._placeholderVariantNonce += 1;
    }

    renderHeader() {
        return html`<h3>${this.t('channel_settings.header_edit')}</h3>`;
    }

    renderBody() {
        const item = this._channels.items.find((c) => c.id === this.channelId);
        const showAvatar = Boolean(item && item.type !== 'direct');
        const busyAvatar = this._fileUpload.busy;
        const showRemoveAvatar = Boolean(item && this._avatarPreviewResolve(item).kind === 'remote');
        return html`
            ${showAvatar
                ? html`
                      <div class="form-group avatar-name-row">
                          <div class="avatar-name-row__avatar">
                              <label class="form-label">${this.t('channel_settings.field_avatar')}</label>
                              <div class="avatar-editor">
                                  <div class="avatar-preview-wrap">
                                      <img
                                          class="avatar-preview-img"
                                          src=${this._avatarPreviewSrc(item)}
                                          alt=""
                                      />
                                      <input
                                          id="sync-channel-avatar-file"
                                          class="avatar-file-input"
                                          type="file"
                                          accept="image/*"
                                          @change=${this._onAvatarFileChange}
                                      />
                                      <div class="avatar-overlay-actions">
                                          <button
                                              type="button"
                                              class="avatar-overlay-btn"
                                              ?disabled=${busyAvatar}
                                              title=${this.t('channel_settings.avatar_change')}
                                              aria-label=${this.t('channel_settings.avatar_change')}
                                              @click=${(e) => {
                                                  e.stopPropagation();
                                                  this._pickAvatarFile();
                                              }}
                                          >
                                              <platform-icon name="edit" size="10"></platform-icon>
                                          </button>
                                          ${showRemoveAvatar
                                              ? html`
                                          <button
                                              type="button"
                                              class="avatar-overlay-btn"
                                              ?disabled=${busyAvatar}
                                              title=${this.t('channel_settings.avatar_remove')}
                                              aria-label=${this.t('channel_settings.avatar_remove')}
                                              @click=${(e) => {
                                                  e.stopPropagation();
                                                  this._clearAvatar();
                                              }}
                                          >
                                              <platform-icon name="trash" size="10"></platform-icon>
                                          </button>
                                              `
                                              : html`
                                          <button
                                              type="button"
                                              class="avatar-overlay-btn"
                                              ?disabled=${busyAvatar}
                                              title=${this.t('channel_settings.avatar_refresh_placeholder')}
                                              aria-label=${this.t('channel_settings.avatar_refresh_placeholder')}
                                              @click=${(e) => this._refreshPlaceholderAvatar(e)}
                                          >
                                              <platform-icon name="refresh" size="10"></platform-icon>
                                          </button>
                                              `}
                                      </div>
                                  </div>
                              </div>
                          </div>
                          <div class="avatar-name-row__name">
                              <label class="form-label">${this.t('channel_settings.field_name')}</label>
                              <input
                                  class="form-input"
                                  type="text"
                                  .value=${this._name}
                                  placeholder=${this.t('channel_settings.placeholder_name')}
                                  @input=${(e) => {
                                      this._name = e.target.value;
                                      this.isDirty = true;
                                  }}
                              />
                          </div>
                      </div>
                  `
                : html`
                      <div class="form-group">
                          <label class="form-label">${this.t('channel_settings.field_direct_chat')}</label>
                          <div class="form-hint">${resolveChannelTitle(item)}</div>
                      </div>
                  `}

            <div class="form-group">
                <label class="form-label">${this.t('channel_settings.notifications')}</label>
                <div class="notifications-toggles">
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.mute_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._muted}
                            @change=${(e) => {
                                this._muted = !!e.detail.value;
                                this.isDirty = true;
                            }}
                        ></platform-switch>
                    </div>
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.transcribe_voice_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._transcribe}
                            @change=${(e) => {
                                this._transcribe = !!e.detail.value;
                                this.isDirty = true;
                            }}
                        ></platform-switch>
                    </div>
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.speech_to_chat_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._speechToChat}
                            @change=${(e) => {
                                this._speechToChat = !!e.detail.value;
                                this.isDirty = true;
                            }}
                        ></platform-switch>
                    </div>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">${this.t('channel_settings.section_members')}</label>
                ${this._membersOp.busy
                    ? html`<div class="form-hint">${this.t('channel_settings.loading')}</div>`
                    : html`<div class="members-list">
                          ${this._members.map(
                              (m) => html`
                                  <div class="member-row">
                                      <platform-user-chip user-id=${m.user_id} size="sm"></platform-user-chip>
                                  </div>
                              `,
                          )}
                      </div>`}
                <button
                    type="button"
                    class="add-members-icon-btn"
                    @click=${this._onAddMembers}
                    title=${this.t('channel_settings.toggle_add_members')}
                    aria-label=${this.t('channel_settings.toggle_add_members')}
                >
                    <platform-icon name="plus" size="20"></platform-icon>
                </button>
            </div>
        `;
    }

    renderFooter() {
        const saveBusy =
            this.loading
            || this._channelUpdate.busy
            || this._notificationsOp.busy
            || this._fileUpload.busy;
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" ?disabled=${saveBusy} @click=${() => this.close()}>
                    ${this.t('channel_modal.action_cancel')}
                </platform-button>
                <platform-button variant="primary" ?disabled=${saveBusy} @click=${this._onSubmit}>
                    ${this.t('channel_settings.save')}
                </platform-button>
            </div>
        `;
    }

    _onAddMembers() {
        if (!this.channelId) return;
        this.openModal('sync.channel_members_add', { channelId: this.channelId });
    }

    async handleSubmit() {
        await this._onSubmit();
    }

    async _onSubmit() {
        if (!this.channelId) return;
        const item = this._channels.items.find((c) => c.id === this.channelId);
        if (!item) {
            this.toast('sync:channel_settings.err_no_channel', { type: 'error' });
            return;
        }
        const trimmed = this._name.trim();
        if (item.type !== 'direct' && trimmed === '') {
            this.toast('sync:channel_settings.err_name_required', { type: 'error' });
            return;
        }
        const body = {
            transcribe_voice_messages: this._transcribe,
            speech_to_chat_enabled: this._speechToChat,
        };
        if (item.type !== 'direct') {
            body.name = trimmed;
        }
        if (item.type !== 'direct') {
            if (this._avatarIntent === 'removed') {
                body.avatar_url = null;
            } else if (this._avatarIntent === 'replaced') {
                body.avatar_url = this._avatarDraftUrl;
            }
        }
        this.loading = true;
        try {
            const ch = await this._channelUpdate.run({
                channel_id: this.channelId,
                body,
            });
            if (ch === null) return;
            const n = await this._notificationsOp.run({
                channel_id: this.channelId,
                notifications_muted: this._muted,
            });
            if (n === null) return;
            this.closeAfterSave();
        } finally {
            this.loading = false;
        }
    }
}

customElements.define('sync-channel-edit-modal', SyncChannelEditModal);
registerModalKind(SyncChannelEditModal.modalKind, 'sync-channel-edit-modal');
