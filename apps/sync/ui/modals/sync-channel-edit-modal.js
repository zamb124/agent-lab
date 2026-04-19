/**
 * sync-channel-edit-modal — редактирование канала.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncChannelEditModal extends PlatformFormModal {
    static modalKind = 'sync.channel_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        channelId: { type: String },
        _name: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            input { padding: var(--space-2); border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-solid); color: var(--text-primary); }
            label { font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this.channelId = '';
        this._name = '';
        this._hydrated = false;
        this._channels = this.useResource('sync/channels');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.channelId) {
            const item = this._channels.byId[this.channelId];
            if (item) {
                this._name = typeof item.name === 'string' ? item.name : '';
                this._hydrated = true;
            }
        }
    }

    renderHeader() { return html`<h3>${this.t('channel_modal.title_edit')}</h3>`; }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('channel_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.markDirty(); }} />
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('channel_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit}>${this.t('channel_modal.action_save')}</platform-button>
        `;
    }

    _onSubmit() {
        if (!this.channelId) return;
        this._channels.update({ id: this.channelId, name: this._name.trim() });
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-edit-modal', SyncChannelEditModal);
registerModalKind(SyncChannelEditModal.modalKind, 'sync-channel-edit-modal');
