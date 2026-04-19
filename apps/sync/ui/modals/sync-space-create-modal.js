/**
 * sync-space-create-modal — создание пространства Sync.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class SyncSpaceCreateModal extends PlatformFormModal {
    static modalKind = 'sync.space_create';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            input[type="text"], textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border);
                background: var(--glass-solid);
                color: var(--text-primary);
                font-family: inherit;
            }
            label { font-size: var(--text-sm); }
            .toggle { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this._name = '';
        this._transcribe = false;
        this._speechToChat = false;
        this._spaces = this.useResource('sync/spaces');
    }

    renderHeader() {
        return html`<h3>${this.t('space_modal.title_create')}</h3>`;
    }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('space_modal.field_name')}</label>
                <input type="text" .value=${this._name} @input=${(e) => { this._name = e.target.value; this.markDirty(); }} />
            </div>
            <div class="toggle">
                <input type="checkbox" id="trans" .checked=${this._transcribe} @change=${(e) => { this._transcribe = e.target.checked; this.markDirty(); }} />
                <label for="trans">${this.t('space_modal.field_transcribe')}</label>
            </div>
            <div class="toggle">
                <input type="checkbox" id="s2c" .checked=${this._speechToChat} @change=${(e) => { this._speechToChat = e.target.checked; this.markDirty(); }} />
                <label for="s2c">${this.t('space_modal.field_speech_to_chat')}</label>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('space_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${this._name.trim().length === 0}>
                ${this.t('space_modal.action_create')}
            </platform-button>
        `;
    }

    _onSubmit() {
        const name = this._name.trim();
        if (name.length === 0) return;
        this._spaces.create({
            name,
            transcribe_voice_messages: this._transcribe,
            speech_to_chat_enabled: this._speechToChat,
        });
        this.closeAfterSave();
    }
}

customElements.define('sync-space-create-modal', SyncSpaceCreateModal);
registerModalKind(SyncSpaceCreateModal.modalKind, 'sync-space-create-modal');
