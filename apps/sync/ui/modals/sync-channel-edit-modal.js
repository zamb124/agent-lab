/**
 * sync-channel-edit-modal — настройки канала: имя, аватар, флаги
 * (notifications mute, transcribe voice, speech-to-chat), список участников
 * + кнопка добавления.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';

export class SyncChannelEditModal extends PlatformFormModal {
    static modalKind = 'sync.channel_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _name: { state: true },
        _avatarUrl: { state: true },
        _muted: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
        _members: { state: true },
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
            .add-btn {
                margin-top: var(--space-2);
                width: 100%;
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
        `,
    ];

    constructor() {
        super();
        this.channelId = '';
        this._name = '';
        this._avatarUrl = '';
        this._muted = false;
        this._transcribe = false;
        this._speechToChat = false;
        this._hydrated = false;
        this._members = [];
        this._channels = this.useResource('sync/channels');
        this._channelUpdate = this.useOp('sync/channel_update');
        this._membersOp = this.useOp('sync/channel_members_list');
        this._notificationsOp = this.useOp('sync/channel_notifications_update');
    }

    async updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.channelId) {
            const item = this._channels.items.find((c) => c.id === this.channelId);
            if (item) {
                if (typeof item.name === 'string') this._name = item.name;
                if (typeof item.avatar_url === 'string') this._avatarUrl = item.avatar_url;
                this._muted = item.notifications_muted === true;
                this._transcribe = item.transcribe_voice_enabled === true;
                this._speechToChat = item.speech_to_chat_enabled === true;
                this._hydrated = true;
                await this._membersOp.run({ channel_id: this.channelId });
                const result = this._membersOp.lastResult;
                if (result && Array.isArray(result.items)) this._members = result.items;
                else if (Array.isArray(result)) this._members = result;
            }
        }
    }

    renderHeader() {
        return html`<h3>${this.t('channel_settings.header_edit')}</h3>`;
    }

    renderBody() {
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('channel_settings.field_name')}</label>
                <input
                    class="form-input"
                    type="text"
                    .value=${this._name}
                    placeholder=${this.t('channel_settings.placeholder_name')}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>

            <div class="form-group">
                <label class="form-label">${this.t('channel_settings.notifications')}</label>
                <div class="notifications-toggles">
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.mute_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._muted}
                            @change=${(e) => { this._muted = !!e.detail.value; this.isDirty = true; }}
                        ></platform-switch>
                    </div>
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.transcribe_voice_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._transcribe}
                            @change=${(e) => { this._transcribe = !!e.detail.value; this.isDirty = true; }}
                        ></platform-switch>
                    </div>
                    <div class="toggle-row">
                        <div class="toggle-label">
                            <span class="toggle-title">${this.t('channel_settings.speech_to_chat_label')}</span>
                        </div>
                        <platform-switch
                            .checked=${this._speechToChat}
                            @change=${(e) => { this._speechToChat = !!e.detail.value; this.isDirty = true; }}
                        ></platform-switch>
                    </div>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">${this.t('channel_settings.section_members')}</label>
                ${this._membersOp.busy
                    ? html`<div class="form-hint">${this.t('channel_settings.loading')}</div>`
                    : html`<div class="members-list">
                        ${this._members.map((m) => html`
                            <div class="member-row">
                                <platform-user-chip user-id=${m.user_id} size="sm"></platform-user-chip>
                            </div>
                        `)}
                    </div>`}
                <platform-button class="add-btn" variant="secondary" @click=${this._onAddMembers}>
                    ${this.t('channel_settings.toggle_add_members')}
                </platform-button>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('channel_modal.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit}>${this.t('channel_settings.save')}</platform-button>
            </div>
        `;
    }

    _onAddMembers() {
        if (!this.channelId) return;
        this.openModal('sync.channel_members_add', { channelId: this.channelId });
    }

    _onSubmit() {
        if (!this.channelId) return;
        this._channelUpdate.run({
            channel_id: this.channelId,
            body: {
                name: this._name.trim(),
                transcribe_voice_messages: this._transcribe,
                speech_to_chat_enabled: this._speechToChat,
            },
        });
        this._notificationsOp.run({
            channel_id: this.channelId,
            notifications_muted: this._muted,
        });
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-edit-modal', SyncChannelEditModal);
registerModalKind(SyncChannelEditModal.modalKind, 'sync-channel-edit-modal');
