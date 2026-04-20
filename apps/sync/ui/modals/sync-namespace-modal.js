/**
 * sync-namespace-modal — редактирование sync-настроек namespace.
 *
 * `modalKind = 'sync.namespace_settings'`. Открывается из `sync-sidebar`
 * иконкой карандаша при выбранном namespace. Пишет ТОЛЬКО `sync_settings`
 * через PUT `/sync/api/v1/namespaces/{name}` (фабрика `sync/namespace_update`).
 *
 * Создание/удаление namespace выполняется в CRM (см. `crm.namespace`-modal).
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/glass-spinner.js';

export class SyncNamespaceModal extends PlatformFormModal {
    static modalKind = 'sync.namespace_settings';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        name: { type: String },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) 0;
            }
            .row + .row { border-top: 1px solid var(--glass-border); }
            .row .label { font-size: var(--text-sm); color: var(--text-primary); }
            .row .desc { font-size: var(--text-xs); color: var(--text-secondary); margin-top: 2px; }
            .name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius-md);
                background: var(--glass-hover);
                color: var(--text-primary);
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                font-size: var(--text-sm);
                margin-bottom: var(--space-3);
            }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.name = '';
        this._transcribe = false;
        this._speechToChat = false;
        this._hydrated = false;
        this._namespaces = this.useResource('sync/namespaces', { autoload: true });
        this._update = this.useOp('sync/namespace_update');
    }

    updated(changed) {
        super.updated?.(changed);
        if (this._hydrated) return;
        const item = this._namespaces.byId[this.name];
        if (!item) return;
        const settings = item.sync_settings;
        if (settings && typeof settings === 'object') {
            this._transcribe = Boolean(settings.transcribe_voice_messages);
            this._speechToChat = Boolean(settings.speech_to_chat_enabled);
        }
        this._hydrated = true;
    }

    _onTranscribeToggle(event) {
        this._transcribe = Boolean(event.detail && event.detail.checked);
        this.isDirty = true;
    }

    _onSpeechToChatToggle(event) {
        this._speechToChat = Boolean(event.detail && event.detail.checked);
        this.isDirty = true;
    }

    async _onSave() {
        if (typeof this.name !== 'string' || this.name === '') return;
        await this._update.run({
            name: this.name,
            body: {
                sync_settings: {
                    transcribe_voice_messages: this._transcribe,
                    speech_to_chat_enabled: this._speechToChat,
                },
            },
        });
        if (this._update.error) return;
        this._namespaces.load();
        this.closeAfterSave();
    }

    renderHeader() {
        return html`<h3>${this.t('namespace_settings.title')}</h3>`;
    }

    render() {
        if (typeof this.name !== 'string' || this.name === '') {
            return html`<div class="empty">${this.t('namespace_settings.no_namespace')}</div>`;
        }
        const item = this._namespaces.byId[this.name];
        if (!item && this._namespaces.loading) {
            return html`<glass-spinner></glass-spinner>`;
        }
        return html`
            <div class="name">
                <platform-icon name="folder" size="14"></platform-icon>
                <span>${this.name}</span>
            </div>
            <div class="row">
                <div>
                    <div class="label">${this.t('namespace_settings.transcribe_voice_messages_label')}</div>
                    <div class="desc">${this.t('namespace_settings.transcribe_voice_messages_desc')}</div>
                </div>
                <platform-switch
                    ?checked=${this._transcribe}
                    @change=${this._onTranscribeToggle}
                ></platform-switch>
            </div>
            <div class="row">
                <div>
                    <div class="label">${this.t('namespace_settings.speech_to_chat_label')}</div>
                    <div class="desc">${this.t('namespace_settings.speech_to_chat_desc')}</div>
                </div>
                <platform-switch
                    ?checked=${this._speechToChat}
                    @change=${this._onSpeechToChatToggle}
                ></platform-switch>
            </div>
            <div class="footer-actions" style="margin-top: var(--space-4);">
                <button class="btn" @click=${() => this.close()}>${this.t('namespace_settings.cancel')}</button>
                <button class="btn primary" @click=${this._onSave} ?disabled=${this._update.busy}>
                    ${this._update.busy ? this.t('namespace_settings.saving') : this.t('namespace_settings.save')}
                </button>
            </div>
            ${nothing}
        `;
    }
}

customElements.define('sync-namespace-modal', SyncNamespaceModal);
registerModalKind(SyncNamespaceModal.modalKind, 'sync-namespace-modal');
