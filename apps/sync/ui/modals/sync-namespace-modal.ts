/**
 * sync-namespace-modal — редактирование sync-настроек namespace.
 *
 * `modalKind = 'sync.namespace_settings'`. Открывается из header
 * `sync-chat-list` (gear) для company workspace `default`. Пишет ТОЛЬКО
 * `sync_settings` через PUT `/sync/api/v1/namespaces/{name}` (фабрика
 * `sync/namespace_update`).
 *
 * Создание/удаление namespace выполняется в CRM / frontend console.
 */

import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-empty-state.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function switchValue(event: Event): boolean {
    if (!(event instanceof CustomEvent) || !isPlainRecord(event.detail) || typeof event.detail.value !== 'boolean') {
        throw new Error('sync-namespace-modal: switch value must be boolean');
    }
    return event.detail.value;
}

export class SyncNamespaceModal extends PlatformFormModal {
    static modalKind = 'sync.namespace_settings';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        name: { type: String },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _hydrated: { state: true },
    };
    declare name: string;
    declare _transcribe: unknown;
    declare _speechToChat: unknown;
    declare _hydrated: unknown;

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) 0;
            }
            .row + .row { border-top: 1px solid var(--glass-border-subtle); }
            .row .label { font-size: var(--text-sm); color: var(--text-primary); font-weight: var(--font-medium); }
            .row .desc { font-size: var(--text-xs); color: var(--text-secondary); margin-top: 2px; }
            .name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                margin-bottom: var(--space-3);
            }
            .empty {
                padding: var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
            }
        `,
    ];
    private _namespaces: ResourceController;
    private _update: OpController;

    constructor() {
        super();
        this.name = '';
        this._transcribe = false;
        this._speechToChat = false;
        this._hydrated = false;
        this._namespaces = this.useResource('sync/namespaces', { autoload: true });
        this._update = this.useOp('sync/namespace_update');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this._hydrated) return;
        const item = this._namespaces.byId[this.name];
        if (!item) return;
        const settings = item.sync_settings;
        if (isPlainRecord(settings)) {
            this._transcribe = settings.transcribe_voice_messages === true;
            this._speechToChat = settings.speech_to_chat_enabled === true;
        }
        this._hydrated = true;
    }

    _onTranscribeToggle(event: Event) {
        this._transcribe = switchValue(event);
        this.isDirty = true;
    }

    _onSpeechToChatToggle(event: Event) {
        this._speechToChat = switchValue(event);
        this.isDirty = true;
    }

    async _onSave() {
        if (typeof this.name !== 'string' || this.name === '') return;
        await this._update.run({
            name: this.name,
            sync_settings: {
                transcribe_voice_messages: this._transcribe,
                speech_to_chat_enabled: this._speechToChat,
            },
        });
        if (this._update.error) return;
        this._namespaces.load();
        this.closeAfterSave();
    }

    override renderHeader() {
        return html`<h3>${this.t('namespace_settings.title')}</h3>`;
    }

    override renderBody() {
        if (typeof this.name !== 'string' || this.name === '') {
            return html`<platform-empty-state icon="layers" title=${this.t('namespace_settings.no_namespace')}></platform-empty-state>`;
        }
        const item = this._namespaces.byId[this.name];
        if (!item && this._namespaces.loading) {
            return html`<platform-empty-state loading></platform-empty-state>`;
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
        `;
    }

    override renderFooter() {
        const hasName = typeof this.name === 'string' && this.name !== '';
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>
                    ${this.t('namespace_settings.cancel')}
                </platform-button>
                <platform-button
                    variant="primary"
                    @click=${this._onSave}
                    ?disabled=${!hasName || this._update.busy}
                >
                    ${this._update.busy ? this.t('namespace_settings.saving') : this.t('namespace_settings.save')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('sync-namespace-modal', SyncNamespaceModal);
registerModalKind(SyncNamespaceModal.modalKind, 'sync-namespace-modal');
