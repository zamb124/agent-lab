/**
 * <platform-chat-settings-fields> — единая форма полей политики поведения чата
 * (FlowChatSettings). Используется в flows-flow-edit-modal (базовая политика flow)
 * и create-embed-modal (per-embed override поверх effective значений).
 *
 * Props:
 *   .chat          — объект со всеми полями FlowChatSettings (effective значения);
 *   disabled       — read-only режим (например preview наследуемой политики).
 *
 * События:
 *   chat-changed   — detail: { patch } (частичный объект с изменённым полем).
 *
 * i18n: ключи flows:chat_settings.* (бандл /api/i18n/<locale> содержит все
 * namespaces, поэтому компонент работает и внутри frontend SPA).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';

export class PlatformChatSettingsFields extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        chat: { attribute: false },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            :host([disabled]) { opacity: 0.65; pointer-events: none; }
            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                margin-bottom: var(--space-3);
            }
            .chat-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2) var(--space-3);
            }
            @media (max-width: 640px) {
                .chat-grid { grid-template-columns: 1fr; }
            }
        `,
    ];

    constructor() {
        super();
        this.chat = null;
        this.disabled = false;
    }

    _emitPatch(patch) {
        this.emit('chat-changed', { patch });
    }

    _renderBoolean(key) {
        return html`
            <platform-field
                type="boolean"
                mode="edit"
                data-chat-field=${key}
                .label=${this.t(`chat_settings.${key}`)}
                .hint=${this.t(`chat_settings.${key}_hint`)}
                .value=${this.chat[key] === true}
                @change=${(e) => this._emitPatch({ [key]: e.detail.value === true })}
            ></platform-field>
        `;
    }

    render() {
        if (!this.chat || typeof this.chat !== 'object') {
            return null;
        }
        const prompts = Array.isArray(this.chat.suggested_prompts) ? this.chat.suggested_prompts : [];
        return html`
            <div class="field">
                <platform-field
                    type="text"
                    mode="edit"
                    data-chat-field="greeting_message"
                    .label=${this.t('chat_settings.greeting_message')}
                    .hint=${this.t('chat_settings.greeting_message_hint')}
                    .value=${typeof this.chat.greeting_message === 'string' ? this.chat.greeting_message : ''}
                    @change=${(e) => {
                        const text = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._emitPatch({ greeting_message: text.trim().length > 0 ? text : null });
                    }}
                ></platform-field>
            </div>
            <div class="field">
                <platform-field
                    type="array"
                    mode="edit"
                    data-chat-field="suggested_prompts"
                    .label=${this.t('chat_settings.suggested_prompts')}
                    .hint=${this.t('chat_settings.suggested_prompts_hint')}
                    .config=${{ preserve_case: true }}
                    .value=${prompts}
                    @change=${(e) => {
                        const list = Array.isArray(e.detail.value) ? e.detail.value : [];
                        this._emitPatch({ suggested_prompts: list });
                    }}
                ></platform-field>
            </div>
            <div class="chat-grid">
                <platform-field
                    type="enum"
                    mode="edit"
                    data-chat-field="tool_calls_display"
                    .label=${this.t('chat_settings.tool_calls_display')}
                    .hint=${this.t('chat_settings.tool_calls_display_hint')}
                    .config=${{
                        values: [
                            { value: 'hidden', label: this.t('chat_settings.tool_calls_hidden') },
                            { value: 'compact', label: this.t('chat_settings.tool_calls_compact') },
                            { value: 'detailed', label: this.t('chat_settings.tool_calls_detailed') },
                        ],
                    }}
                    .value=${this.chat.tool_calls_display}
                    @change=${(e) => this._emitPatch({ tool_calls_display: e.detail.value })}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    data-chat-field="errors_display"
                    .label=${this.t('chat_settings.errors_display')}
                    .hint=${this.t('chat_settings.errors_display_hint')}
                    .config=${{
                        values: [
                            { value: 'generic', label: this.t('chat_settings.errors_generic') },
                            { value: 'detailed', label: this.t('chat_settings.errors_detailed') },
                        ],
                    }}
                    .value=${this.chat.errors_display}
                    @change=${(e) => this._emitPatch({ errors_display: e.detail.value })}
                ></platform-field>
                ${this._renderBoolean('show_reasoning')}
                ${this._renderBoolean('show_activity')}
                ${this._renderBoolean('show_run_trace')}
                ${this._renderBoolean('show_trace_actions')}
                ${this._renderBoolean('show_browser_previews')}
                ${this._renderBoolean('show_files_panel')}
                ${this._renderBoolean('allow_cancel')}
            </div>
        `;
    }
}

customElements.define('platform-chat-settings-fields', PlatformChatSettingsFields);
