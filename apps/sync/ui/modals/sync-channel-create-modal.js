/**
 * sync-channel-create-modal — создание канала Sync.
 *
 * Платформенный namespace выбирается ГЛОБАЛЬНО в sidebar; модалка получает
 * `namespace` через prop из активного namespace (`sync-sidebar` /
 * `sync-channel-picker`) и не дублирует выбор. Если namespace не выбран и
 * тип = topic — создание заблокировано с подсказкой.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncChannelCreateModal extends PlatformFormModal {
    static modalKind = 'sync.channel_create';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        namespace: { type: String },
        adhocCall: { type: Boolean },
        _name: { state: true },
        _type: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
    ];

    constructor() {
        super();
        this.namespace = '';
        this.adhocCall = false;
        this._name = '';
        this._type = 'topic';
        this._channels = this.useResource('sync/channels');
    }

    _isSubmittable() {
        if (this._name.trim().length === 0) return false;
        if (this._type === 'topic' && (typeof this.namespace !== 'string' || this.namespace === '')) return false;
        return true;
    }

    renderHeader() {
        return html`<h3>${this.t('channel_modal.title_create')}</h3>`;
    }

    renderBody() {
        const topicWithoutNs = this._type === 'topic'
            && (typeof this.namespace !== 'string' || this.namespace === '');
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('channel_modal.field_name')}</label>
                <input
                    class="form-input"
                    type="text"
                    .value=${this._name}
                    placeholder=${this.t('channel_settings.placeholder_name')}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.t('channel_modal.field_type')}</label>
                <select
                    class="form-select"
                    .value=${this._type}
                    @change=${(e) => { this._type = e.target.value; this.isDirty = true; }}
                >
                    <option value="topic">${this.t('channel_modal.type_topic')}</option>
                    <option value="group">${this.t('channel_modal.type_group')}</option>
                </select>
            </div>
            ${topicWithoutNs ? html`
                <div class="form-group">
                    <div class="form-hint">${this.t('channel_settings.err_pick_namespace')}</div>
                </div>
            ` : ''}
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('channel_modal.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${!this._isSubmittable()}>
                    ${this.t('channel_modal.action_create')}
                </platform-button>
            </div>
        `;
    }

    _onSubmit() {
        if (!this._isSubmittable()) return;
        const name = this._name.trim();
        const body = { name, type: this._type };
        if (this._type === 'topic') body.namespace = this.namespace;
        this._channels.create(body);
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-create-modal', SyncChannelCreateModal);
registerModalKind(SyncChannelCreateModal.modalKind, 'sync-channel-create-modal');
