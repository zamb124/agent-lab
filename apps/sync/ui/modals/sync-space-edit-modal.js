/**
 * sync-space-edit-modal — редактирование пространства Sync.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class SyncSpaceEditModal extends PlatformFormModal {
    static modalKind = 'sync.space_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        spaceId: { type: String },
        _name: { state: true },
        _namespace: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .ns-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.spaceId = '';
        this._name = '';
        this._namespace = '';
        this._transcribe = false;
        this._speechToChat = false;
        this._hydrated = false;
        this._spaces = this.useResource('sync/spaces');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.spaceId) {
            const item = this._spaces.byId[this.spaceId];
            if (item) {
                this._name = typeof item.name === 'string' ? item.name : '';
                this._namespace = typeof item.namespace === 'string' ? item.namespace : '';
                this._transcribe = Boolean(item.transcribe_voice_messages);
                this._speechToChat = Boolean(item.speech_to_chat_enabled);
                this._hydrated = true;
            }
        }
    }

    renderHeader() {
        return html`<h3>${this.t('space_modal.title_edit')}</h3>`;
    }

    renderBody() {
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('space_modal.field_name')}</label>
                <input
                    class="form-input"
                    type="text"
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.t('space_modal.field_namespace')}</label>
                <input
                    class="form-input readonly"
                    type="text"
                    .value=${this._namespace}
                    readonly
                    disabled
                />
                <div class="ns-hint">${this.t('space_modal.namespace_immutable_hint')}</div>
            </div>
            <div
                class=${this._transcribe ? 'form-item selected' : 'form-item'}
                @click=${() => { this._transcribe = !this._transcribe; this.isDirty = true; }}
            >
                <div class="form-checkbox">
                    ${this._transcribe ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                </div>
                <div class="form-item-content">
                    <div class="form-item-title">${this.t('space_modal.field_transcribe')}</div>
                </div>
            </div>
            <div
                class=${this._speechToChat ? 'form-item selected' : 'form-item'}
                @click=${() => { this._speechToChat = !this._speechToChat; this.isDirty = true; }}
            >
                <div class="form-checkbox">
                    ${this._speechToChat ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                </div>
                <div class="form-item-content">
                    <div class="form-item-title">${this.t('space_modal.field_speech_to_chat')}</div>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('space_modal.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit}>${this.t('space_modal.action_save')}</platform-button>
            </div>
        `;
    }

    _onSubmit() {
        if (!this.spaceId) return;
        this._spaces.update({
            space_id: this.spaceId,
            name: this._name.trim(),
            transcribe_voice_messages: this._transcribe,
            speech_to_chat_enabled: this._speechToChat,
        });
        this.closeAfterSave();
    }
}

customElements.define('sync-space-edit-modal', SyncSpaceEditModal);
registerModalKind(SyncSpaceEditModal.modalKind, 'sync-space-edit-modal');
