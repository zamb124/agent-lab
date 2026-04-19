/**
 * sync-channel-notifications-modal — настройки уведомлений канала (mute).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncChannelNotificationsModal extends PlatformFormModal {
    static modalKind = 'sync.channel_notifications';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _muted: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .toggle { display: flex; align-items: center; gap: var(--space-2); margin: var(--space-3) 0; }
        `,
    ];

    constructor() {
        super();
        this.channelId = '';
        this._muted = false;
        this._hydrated = false;
        this._channels = this.useResource('sync/channels');
        this._notify = this.useOp('sync/channel_notifications_update');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.channelId) {
            const item = this._channels.byId[this.channelId];
            if (item) {
                this._muted = Boolean(item.notifications_muted);
                this._hydrated = true;
            }
        }
    }

    renderHeader() { return html`<h3>${this.t('channel_notifications.title')}</h3>`; }

    renderBody() {
        return html`
            <div class="toggle">
                <input type="checkbox" id="mute" .checked=${this._muted} @change=${(e) => { this._muted = e.target.checked; this.markDirty(); }} />
                <label for="mute">${this.t('channel_notifications.field_muted')}</label>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('channel_notifications.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit}>${this.t('channel_notifications.action_save')}</platform-button>
        `;
    }

    _onSubmit() {
        if (!this.channelId) return;
        this._notify.run({ channel_id: this.channelId, notifications_muted: this._muted });
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-notifications-modal', SyncChannelNotificationsModal);
registerModalKind(SyncChannelNotificationsModal.modalKind, 'sync-channel-notifications-modal');
