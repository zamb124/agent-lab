/**
 * Адаптер приложения для каноничного композера чата flows.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/flows-chat/flows-chat-input.js';
import {
    readTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '@platform/lib/voice/tts-output-pref.js';

export class ChatInput extends PlatformElement {
    static i18nNamespace = 'flows';
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: var(--space-4) var(--space-6);
            }
            flows-chat-input {
                --flows-chat-input-max-width: 900px;
                --flows-chat-input-margin: 0 auto;
                --flows-chat-input-padding: var(--space-3);
                --flows-chat-input-radius: var(--radius-2xl);
                --flows-chat-input-bg: var(--glass-solid-medium);
                --flows-chat-input-border: var(--glass-border-medium);
                --flows-chat-input-text: var(--text-primary);
                --flows-chat-input-muted: var(--text-tertiary);
                --flows-chat-input-accent: var(--accent);
                --flows-chat-input-shadow: var(--glass-shadow-subtle), var(--glass-inner-glow-subtle);
                --flows-chat-input-focus-shadow: var(--glass-shadow-medium), var(--glass-inner-glow-medium), var(--hover-glow);
                --flows-chat-input-backdrop-filter: blur(var(--glass-blur-subtle));
                --flows-chat-input-button-radius: var(--radius-lg);
                --flows-chat-input-button-bg: transparent;
                --flows-chat-input-button-hover-bg: var(--glass-solid-strong);
                --flows-chat-input-send-radius: var(--radius-xl);
                --flows-chat-input-send-bg: var(--accent-gradient);
                --flows-chat-input-send-color: white;
                --flows-chat-input-send-shadow: 0 4px 12px rgba(153, 166, 249, 0.3);
                --flows-chat-input-send-hover-shadow: 0 6px 20px rgba(153, 166, 249, 0.4);
                --flows-chat-input-chip-bg: var(--glass-solid-subtle);
                --flows-chat-input-file-radius: var(--radius-md);
                --flows-chat-input-file-padding: var(--space-2) var(--space-3);
                --flows-chat-input-danger: var(--error, #ef4444);
                --flows-chat-input-danger-bg: var(--error-bg);
            }
            @media (max-width: 768px) {
                :host {
                    padding: var(--space-5) var(--space-4);
                    padding-bottom: var(--space-6);
                    background: var(--glass-solid-strong);
                    border-top-left-radius: 20px;
                    border-top-right-radius: 20px;
                    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.15);
                }
                flows-chat-input {
                    --flows-chat-input-max-width: none;
                    --flows-chat-input-margin: 0;
                    --flows-chat-input-padding: 0;
                    --flows-chat-input-bg: transparent;
                    --flows-chat-input-border: transparent;
                    --flows-chat-input-shadow: none;
                    --flows-chat-input-focus-shadow: none;
                    --flows-chat-input-backdrop-filter: none;
                    --flows-chat-input-radius: 0;
                    --flows-chat-input-textarea-min-height: 44px;
                }
            }
        `,
    ];

    static properties = {
        disabled: { type: Boolean },
        loading: { type: Boolean },
        streaming: { type: Boolean },
        placeholder: { type: String },
        accept: { type: String },
        maxLength: { type: Number },
        maxFileSize: { type: Number },
        showVoice: { type: Boolean, attribute: 'show-voice' },
        voiceActive: { type: Boolean, attribute: 'voice-active' },
        voiceStatus: { type: String, attribute: 'voice-status' },
        ttsOutputEnabled: { type: Boolean, attribute: 'tts-output-enabled' },
        cancelBusy: { type: Boolean, attribute: 'cancel-busy' },
    };

    constructor() {
        super();
        this.disabled = false;
        this.loading = false;
        this.streaming = false;
        this.placeholder = 'Send a message';
        this.accept = '';
        this.maxLength = 10000;
        this.maxFileSize = 10 * 1024 * 1024;
        this.showVoice = false;
        this.voiceActive = false;
        this.voiceStatus = 'idle';
        this.ttsOutputEnabled = true;
        this.cancelBusy = false;
        this._onTtsPrefChatInput = () => {
            this.ttsOutputEnabled = readTtsOutputEnabled();
            this.requestUpdate();
        };
        this._onTtsStorageChatInput = (e) => {
            if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                this.ttsOutputEnabled = readTtsOutputEnabled();
                this.requestUpdate();
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefChatInput);
            window.addEventListener('storage', this._onTtsStorageChatInput);
            this.ttsOutputEnabled = readTtsOutputEnabled();
        }
    }

    disconnectedCallback() {
        if (typeof window !== 'undefined') {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefChatInput);
            window.removeEventListener('storage', this._onTtsStorageChatInput);
        }
        super.disconnectedCallback();
    }

    _inputEl() {
        const input = this.shadowRoot?.querySelector('flows-chat-input');
        if (
            !input
            || typeof input.setDraft !== 'function'
            || typeof input.clear !== 'function'
            || typeof input.focus !== 'function'
        ) {
            throw new Error('chat-input: flows-chat-input missing');
        }
        return input;
    }

    _labels() {
        return {
            title_attach: this.t('chat_input.title_attach'),
            title_remove_file: this.t('chat_input.title_remove_file'),
            title_stop: this.t('chat_input.title_stop'),
            title_stop_pending: this.t('chat_input.title_stop_pending'),
            send: this.t('chat_input.title_send'),
            err_file_too_large: this.t('chat_input.err_file_too_large'),
            voice_on: this.t('platform_chat.btn_voice_on'),
            voice_off: this.t('platform_chat.btn_voice_off'),
            voice_status_idle: this.t('platform_chat.voice_status_idle'),
            voice_status_listening: this.t('platform_chat.voice_status_listening'),
            voice_status_speaking: this.t('platform_chat.voice_status_speaking'),
            voice_status_error: this.t('platform_chat.voice_status_error'),
            voice_status_closed: this.t('platform_chat.voice_status_closed'),
            tts_output_enable: this.t('platform_chat.tts_output_enable'),
            tts_output_disable: this.t('platform_chat.tts_output_disable'),
        };
    }

    focus() {
        this._inputEl().focus();
    }

    clear() {
        this._inputEl().clear();
    }

    setDraft(text) {
        if (typeof text !== 'string') {
            throw new TypeError('chat-input.setDraft expects a string');
        }
        this._inputEl().setDraft(text);
    }

    _onSend(e) {
        e.stopPropagation();
        this.emit('send', e.detail);
    }

    _onStop(e) {
        e.stopPropagation();
        this.emit('stop');
    }

    _onVoiceToggle(e) {
        e.stopPropagation();
        this.emit('voice-toggle');
    }

    _onTtsOutputToggle(e) {
        e.stopPropagation();
        this.emit('tts-output-toggle');
    }

    _onToast(e) {
        e.stopPropagation();
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        if (detail.key === 'err_file_too_large') {
            this.toast('chat_input.err_file_too_large', {
                type: 'error',
                vars: detail.vars && typeof detail.vars === 'object' ? detail.vars : {},
            });
        }
    }

    render() {
        return html`
            <flows-chat-input
                .disabled=${this.disabled}
                .loading=${this.loading || this.streaming}
                .cancelBusy=${this.cancelBusy}
                .placeholder=${this.placeholder}
                .accept=${this.accept}
                .maxLength=${this.maxLength}
                .maxFileSize=${this.maxFileSize}
                .showVoice=${this.showVoice}
                .voiceActive=${this.voiceActive}
                .voiceStatus=${this.voiceStatus}
                .ttsOutputEnabled=${this.ttsOutputEnabled}
                .labels=${this._labels()}
                @send=${this._onSend}
                @stop=${this._onStop}
                @voice-toggle=${this._onVoiceToggle}
                @tts-output-toggle=${this._onTtsOutputToggle}
                @toast=${this._onToast}
            ></flows-chat-input>
        `;
    }
}

customElements.define('chat-input', ChatInput);
