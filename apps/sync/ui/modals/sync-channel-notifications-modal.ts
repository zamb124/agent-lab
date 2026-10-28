/**
 * sync-channel-notifications-modal — настройки уведомлений канала (mute).
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class SyncChannelNotificationsModal extends PlatformFormModal {
    static modalKind = 'sync.channel_notifications';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _muted: { state: true },
        _hydrated: { state: true },
    };
    declare channelId: string;
    declare _muted: unknown;
    declare _hydrated: unknown;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];
    private _channels: ControllerFor<'sync/channels'>;
    private _notify: OpController;

    constructor() {
        super();
        this.channelId = '';
        this._muted = false;
        this._hydrated = false;
        this._channels = this.useResource('sync/channels');
        this._notify = this.useOp('sync/channel_notifications_update');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (!this._hydrated && this.channelId) {
            const item = this._channels.byId[this.channelId];
            if (item) {
                this._muted = Boolean(item.notifications_muted);
                this._hydrated = true;
            }
        }
    }

    override renderHeader() { return html`<h3>${this.t('channel_notifications.title')}</h3>`; }

    override renderBody() {
        return html`
            <div
                class=${this._muted ? 'form-item selected' : 'form-item'}
                @click=${() => { this._muted = !this._muted; this.isDirty = true; }}
            >
                <div class="form-checkbox">
                    ${this._muted ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                </div>
                <div class="form-item-content">
                    <div class="form-item-title">${this.t('channel_notifications.field_muted')}</div>
                </div>
            </div>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('channel_notifications.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit}>${this.t('channel_notifications.action_save')}</platform-button>
            </div>
        `;
    }

    override async _onSubmit(e?: SubmitEvent): Promise<void> {
        if (!this.channelId) return;
        this._notify.run({ channel_id: this.channelId, notifications_muted: this._muted });
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-notifications-modal', SyncChannelNotificationsModal);
registerModalKind(SyncChannelNotificationsModal.modalKind, 'sync-channel-notifications-modal');
