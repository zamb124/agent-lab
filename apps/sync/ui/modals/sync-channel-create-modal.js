/**
 * sync-channel-create-modal — создание канала Sync.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveSpaceId } from '../_helpers/sync-id-resolvers.js';
import '@platform/lib/components/platform-button.js';

export class SyncChannelCreateModal extends PlatformFormModal {
    static modalKind = 'sync.channel_create';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        spaceId: { type: String },
        adhocCall: { type: Boolean },
        _name: { state: true },
        _type: { state: true },
        _selectedSpaceId: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            input, select { padding: var(--space-2); border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-solid); color: var(--text-primary); }
            label { font-size: var(--text-sm); }
        `,
    ];

    constructor() {
        super();
        this.spaceId = '';
        this.adhocCall = false;
        this._name = '';
        this._type = 'topic';
        this._selectedSpaceId = '';
        this._channels = this.useResource('sync/channels');
        this._spaces = this.useResource('sync/spaces', { autoload: true });
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('spaceId') && this.spaceId && !this._selectedSpaceId) {
            this._selectedSpaceId = this.spaceId;
        }
    }

    renderHeader() {
        return html`<h3>${this.t('channel_modal.title_create')}</h3>`;
    }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('channel_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.markDirty(); }} />
            </div>
            <div class="field">
                <label>${this.t('channel_modal.field_type')}</label>
                <select .value=${this._type} @change=${(e) => { this._type = e.target.value; this.markDirty(); }}>
                    <option value="topic">${this.t('channel_modal.type_topic')}</option>
                    <option value="group">${this.t('channel_modal.type_group')}</option>
                </select>
            </div>
            ${this._type === 'topic' && this._spaces.items.length > 0 ? html`
                <div class="field">
                    <label>${this.t('channel_modal.field_space')}</label>
                    <select .value=${this._selectedSpaceId} @change=${(e) => { this._selectedSpaceId = e.target.value; this.markDirty(); }}>
                        <option value="">${this.t('channel_modal.field_space_none')}</option>
                        ${this._spaces.items.map((s) => html`
                            <option value=${resolveSpaceId(s)}>${s.name}</option>
                        `)}
                    </select>
                </div>
            ` : ''}
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('channel_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._name.trim().length === 0}>
                ${this.t('channel_modal.action_create')}
            </platform-button>
        `;
    }

    _onSubmit() {
        const name = this._name.trim();
        if (name.length === 0) return;
        const body = { name, type: this._type };
        if (this._type === 'topic' && this._selectedSpaceId) body.space_id = this._selectedSpaceId;
        this._channels.create(body);
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-create-modal', SyncChannelCreateModal);
registerModalKind(SyncChannelCreateModal.modalKind, 'sync-channel-create-modal');
