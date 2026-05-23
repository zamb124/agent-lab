import { LitElement, html, css } from '../lit-shim.js';
import { toggleTtsOutputEnabled } from '../voice/tts-output-pref.js';
import '../flows-chat/flows-chat-input.js';

export class EmbedChatInput extends LitElement {
    static properties = {
        loading: { type: Boolean },
        cancelBusy: { type: Boolean, attribute: 'cancel-busy' },
        placeholder: { type: String },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        voiceDuplex: { type: Boolean, attribute: 'voice-duplex' },
        voiceActive: { type: Boolean, attribute: 'voice-active' },
        voiceStatus: { type: String, attribute: 'voice-status' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        labels: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            border-top: 1px solid var(--embed-chat-border, rgba(255, 255, 255, 0.12));
            padding: 12px 0 0;
            background: transparent;
        }
        flows-chat-input {
            --flows-chat-input-max-width: none;
            --flows-chat-input-margin: 0;
            --flows-chat-input-min-height: 52px;
            --flows-chat-input-padding: 6px 8px 6px 10px;
            --flows-chat-input-gap: 6px;
            --flows-chat-input-radius: 25px;
            --flows-chat-input-bg: var(--embed-chat-composer-bg, rgba(255, 255, 255, 0.07));
            --flows-chat-input-border: var(--embed-chat-border, rgba(255, 255, 255, 0.14));
            --flows-chat-input-text: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            --flows-chat-input-muted: var(--embed-chat-muted, rgba(255, 255, 255, 0.45));
            --flows-chat-input-accent: var(--embed-chat-accent, #99a6f9);
            --flows-chat-input-button-size: 40px;
            --flows-chat-input-button-radius: 50%;
            --flows-chat-input-button-bg: var(--embed-chat-surface, rgba(255, 255, 255, 0.1));
            --flows-chat-input-button-hover-bg: var(--embed-chat-surface-hover, rgba(255, 255, 255, 0.14));
            --flows-chat-input-button-color: var(--embed-chat-text, rgba(255, 255, 255, 0.88));
            --flows-chat-input-button-hover-color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            --flows-chat-input-active-bg: var(--embed-chat-accent-muted, rgba(153, 166, 249, 0.35));
            --flows-chat-input-active-color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            --flows-chat-input-send-size: 40px;
            --flows-chat-input-send-radius: 50%;
            --flows-chat-input-send-bg: var(--embed-chat-accent, #99a6f9);
            --flows-chat-input-send-color: var(--embed-chat-on-accent, #0f0f12);
            --flows-chat-input-send-shadow: none;
            --flows-chat-input-send-hover-shadow: none;
            --flows-chat-input-chip-bg: var(--embed-chat-surface, rgba(255, 255, 255, 0.1));
            --flows-chat-input-file-radius: 999px;
            --flows-chat-input-file-padding: 4px 8px;
            --flows-chat-input-danger: rgba(229, 57, 53, 0.9);
            --flows-chat-input-danger-bg: var(--embed-chat-input-bg, rgba(0, 0, 0, 0.2));
            --flows-chat-input-textarea-max-height: 140px;
            --flows-chat-input-textarea-font-size: 15px;
            --flows-chat-input-textarea-padding: 8px 4px;
        }
    `;

    constructor() {
        super();
        this.loading = false;
        this.cancelBusy = false;
        this.placeholder = '';
        this.enableVoice = true;
        this.voiceDuplex = false;
        this.voiceActive = false;
        this.voiceStatus = 'idle';
        this.showLocaleControl = false;
        this.interfaceLocale = 'auto';
        this.labels = {};
    }

    _inputEl() {
        const input = this.shadowRoot?.querySelector('flows-chat-input');
        if (
            !input
            || typeof input.setDraft !== 'function'
            || typeof input.clear !== 'function'
            || typeof input.focus !== 'function'
        ) {
            throw new Error('embed-chat-input: flows-chat-input missing');
        }
        return input;
    }

    setDraft(text) {
        if (typeof text !== 'string') {
            throw new TypeError('embed-chat-input.setDraft expects a string');
        }
        this._inputEl().setDraft(text);
    }

    clear() {
        this._inputEl().clear();
    }

    focus() {
        this._inputEl().focus();
    }

    _forwardSend(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('embed-send', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _forwardStop(e) {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('embed-stop', { bubbles: true, composed: true }));
    }

    _forwardVoiceToggle(e) {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('voice-toggle', { bubbles: true, composed: true }));
    }

    _toggleTtsOutput(e) {
        e.stopPropagation();
        toggleTtsOutputEnabled();
    }

    _forwardLocaleChange(e) {
        e.stopPropagation();
        this.interfaceLocale = e.detail?.locale || 'auto';
        this.dispatchEvent(
            new CustomEvent('embed-locale-change', {
                detail: { locale: this.interfaceLocale },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _forwardToast(e) {
        e.stopPropagation();
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        this.dispatchEvent(
            new CustomEvent('embed-toast', {
                detail: { message: typeof detail.message === 'string' ? detail.message : '' },
                bubbles: true,
                composed: true,
            }),
        );
    }

    render() {
        return html`
            <flows-chat-input
                .loading=${this.loading}
                .cancelBusy=${this.cancelBusy}
                .placeholder=${this.placeholder}
                .labels=${this.labels || {}}
                .showVoice=${this.enableVoice || this.voiceDuplex}
                .voiceDuplex=${this.voiceDuplex}
                .speechDictation=${this.enableVoice && !this.voiceDuplex}
                .voiceActive=${this.voiceActive}
                .voiceStatus=${this.voiceStatus || 'idle'}
                .showLocaleControl=${this.showLocaleControl}
                .interfaceLocale=${this.interfaceLocale || 'auto'}
                .showDisclaimer=${true}
                @send=${this._forwardSend}
                @stop=${this._forwardStop}
                @voice-toggle=${this._forwardVoiceToggle}
                @tts-output-toggle=${this._toggleTtsOutput}
                @locale-change=${this._forwardLocaleChange}
                @toast=${this._forwardToast}
            ></flows-chat-input>
        `;
    }
}

customElements.define('embed-chat-input', EmbedChatInput);
