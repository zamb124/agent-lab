/**
 * sync-space-edit-modal — редактирование пространства Sync.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncSpaceEditModal extends PlatformFormModal {
    static modalKind = 'sync.space_edit';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        spaceId: { type: String },
        _name: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            input[type="text"] {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border);
                background: var(--glass-solid);
                color: var(--text-primary);
            }
            label { font-size: var(--text-sm); }
            .toggle { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.spaceId = '';
        this._name = '';
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
            <div class="field">
                <label>${this.t('space_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.markDirty(); }} />
            </div>
            <div class="toggle">
                <input type="checkbox" id="trans-e" .checked=${this._transcribe} @change=${(e) => { this._transcribe = e.target.checked; this.markDirty(); }} />
                <label for="trans-e">${this.t('space_modal.field_transcribe')}</label>
            </div>
            <div class="toggle">
                <input type="checkbox" id="s2c-e" .checked=${this._speechToChat} @change=${(e) => { this._speechToChat = e.target.checked; this.markDirty(); }} />
                <label for="s2c-e">${this.t('space_modal.field_speech_to_chat')}</label>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('space_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit}>${this.t('space_modal.action_save')}</platform-button>
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
