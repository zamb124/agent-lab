import { LitElement, html, css, nothing } from '../lit-shim.js';
import {
    readTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '../voice/tts-output-pref.js';
import '../components/platform-icon.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { resolveFileIconKey } from '../utils/file-icons.js';

function _label(labels, key, fallback) {
    const source = labels && typeof labels === 'object' ? labels : {};
    const value = source[key];
    return typeof value === 'string' && value.trim() !== '' ? value : fallback;
}

function _icon(name) {
    if (name === 'attach') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>`;
    }
    if (name === 'send') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M12 5v12M6 11l6-6 6 6"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>`;
    }
    if (name === 'stop') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
        </svg>`;
    }
    if (name === 'mic') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M12 14a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v4a3 3 0 0 0 3 3z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linejoin="round"
            />
            <path
                d="M8 11v1a4 4 0 0 0 8 0v-1M12 18v3M9 21h6"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
            />
        </svg>`;
    }
    if (name === 'mic-off') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M12 14c1.66 0 3-1.34 3-3V6a3 3 0 1 0-6 0v5c0 1.66 1.34 3 3 3Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linejoin="round"
            />
            <path d="M19 11a7 7 0 1 1-14 0" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <path d="M4 4l16 16" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>`;
    }
    if (name === 'volume-up') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"
                fill="currentColor"
            />
        </svg>`;
    }
    if (name === 'volume-off') {
        return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
                d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73 9.27 8l-5-5zM12 4l-1.41 1.41L12 8.18V4z"
                fill="currentColor"
            />
        </svg>`;
    }
    return html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M6 12h12" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
    </svg>`;
}

export class FlowsChatInput extends LitElement {
    static properties = {
        disabled: { type: Boolean },
        loading: { type: Boolean },
        streaming: { type: Boolean },
        cancelBusy: { type: Boolean, attribute: 'cancel-busy' },
        placeholder: { type: String },
        accept: { type: String },
        maxLength: { type: Number, attribute: 'max-length' },
        maxFileSize: { type: Number, attribute: 'max-file-size' },
        showVoice: { type: Boolean, attribute: 'show-voice' },
        voiceDuplex: { type: Boolean, attribute: 'voice-duplex' },
        speechDictation: { type: Boolean, attribute: 'speech-dictation' },
        voiceActive: { type: Boolean, attribute: 'voice-active' },
        voiceStatus: { type: String, attribute: 'voice-status' },
        ttsOutputEnabled: { type: Boolean, attribute: 'tts-output-enabled' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        showDisclaimer: { type: Boolean, attribute: 'show-disclaimer' },
        labels: { type: Object },
        _value: { state: true },
        _selectedFiles: { state: true },
        _listening: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            color: var(--flows-chat-input-text, var(--text-primary, rgba(255, 255, 255, 0.92)));
            font-family: var(--flows-chat-input-font-family, inherit);
        }
        .files-preview {
            display: flex;
            flex-wrap: wrap;
            gap: var(--flows-chat-input-file-gap, 8px);
            margin: 0 0 var(--flows-chat-input-file-margin, 10px);
        }
        .file-item {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
            max-width: 100%;
            padding: var(--flows-chat-input-file-padding, 6px 10px);
            border: 1px solid var(--flows-chat-input-border, var(--border-subtle, rgba(255, 255, 255, 0.14)));
            border-radius: var(--flows-chat-input-file-radius, 999px);
            background: var(--flows-chat-input-chip-bg, var(--glass-solid-subtle, rgba(255, 255, 255, 0.1)));
            font-size: var(--flows-chat-input-file-font-size, 12px);
            box-sizing: border-box;
        }
        .file-icon {
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55)));
        }
        .file-info {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .file-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: var(--flows-chat-input-text, var(--text-primary, rgba(255, 255, 255, 0.92)));
            font-weight: 500;
        }
        .file-size {
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55)));
            font-size: 11px;
        }
        .file-remove {
            flex-shrink: 0;
            width: 24px;
            height: 24px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            border: none;
            border-radius: 50%;
            cursor: pointer;
            background: transparent;
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55)));
            font: inherit;
            font-size: 16px;
            line-height: 1;
        }
        .file-remove:hover {
            color: var(--flows-chat-input-danger, var(--error, #ef4444));
            background: var(--flows-chat-input-danger-bg, var(--error-bg, rgba(239, 68, 68, 0.12)));
        }
        .input-container {
            display: flex;
            align-items: flex-end;
            gap: var(--flows-chat-input-gap, 12px);
            min-height: var(--flows-chat-input-min-height, 52px);
            max-width: var(--flows-chat-input-max-width, 900px);
            margin: var(--flows-chat-input-margin, 0 auto);
            padding: var(--flows-chat-input-padding, 12px);
            box-sizing: border-box;
            border: 1px solid var(--flows-chat-input-border, var(--glass-border-medium, rgba(255, 255, 255, 0.14)));
            border-radius: var(--flows-chat-input-radius, 20px);
            background: var(--flows-chat-input-bg, var(--glass-solid-medium, rgba(255, 255, 255, 0.07)));
            box-shadow: var(--flows-chat-input-shadow, var(--glass-shadow-subtle, none));
            backdrop-filter: var(--flows-chat-input-backdrop-filter, none);
            -webkit-backdrop-filter: var(--flows-chat-input-backdrop-filter, none);
        }
        .input-container:focus-within {
            border-color: var(--flows-chat-input-focus-border, var(--flows-chat-input-accent, var(--accent, #99a6f9)));
            box-shadow: var(--flows-chat-input-focus-shadow, var(--flows-chat-input-shadow, none));
        }
        input[type='file'] {
            display: none;
        }
        .circle-btn {
            flex-shrink: 0;
            width: var(--flows-chat-input-button-size, 40px);
            height: var(--flows-chat-input-button-size, 40px);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            border: none;
            border-radius: var(--flows-chat-input-button-radius, 12px);
            cursor: pointer;
            background: var(--flows-chat-input-button-bg, transparent);
            color: var(--flows-chat-input-button-color, var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55))));
            transition: transform 120ms ease, background 120ms ease, color 120ms ease, opacity 120ms ease;
        }
        .circle-btn:hover:not(:disabled) {
            background: var(--flows-chat-input-button-hover-bg, var(--glass-solid-strong, rgba(255, 255, 255, 0.14)));
            color: var(--flows-chat-input-button-hover-color, var(--flows-chat-input-text, rgba(255, 255, 255, 0.92)));
        }
        .circle-btn:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }
        .circle-btn.active {
            color: var(--flows-chat-input-active-color, var(--flows-chat-input-accent, var(--accent, #99a6f9)));
            background: var(--flows-chat-input-active-bg, rgba(153, 166, 249, 0.18));
        }
        .grow {
            flex: 1;
            min-width: 0;
            display: flex;
            align-items: center;
        }
        textarea {
            width: 100%;
            min-height: var(--flows-chat-input-textarea-min-height, 40px);
            max-height: var(--flows-chat-input-textarea-max-height, 180px);
            resize: none;
            border: none;
            outline: none;
            background: transparent;
            color: var(--flows-chat-input-text, var(--text-primary, rgba(255, 255, 255, 0.92)));
            padding: var(--flows-chat-input-textarea-padding, 8px 4px);
            font-family: inherit;
            font-size: var(--flows-chat-input-textarea-font-size, 15px);
            line-height: 1.4;
            box-sizing: border-box;
        }
        textarea::placeholder {
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.45)));
        }
        textarea:disabled {
            opacity: 0.55;
            cursor: not-allowed;
        }
        .locale {
            flex-shrink: 0;
            max-width: 140px;
        }
        .locale select {
            max-width: 100%;
            border: none;
            background: transparent;
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55)));
            font: inherit;
            font-size: 13px;
            cursor: pointer;
            padding: 6px 4px;
        }
        .locale select:focus {
            outline: none;
            color: var(--flows-chat-input-text, var(--text-primary, rgba(255, 255, 255, 0.92)));
        }
        .send-btn {
            width: var(--flows-chat-input-send-size, 44px);
            height: var(--flows-chat-input-send-size, 44px);
            border-radius: var(--flows-chat-input-send-radius, 14px);
            background: var(--flows-chat-input-send-bg, var(--accent-gradient, #99a6f9));
            color: var(--flows-chat-input-send-color, white);
            box-shadow: var(--flows-chat-input-send-shadow, 0 4px 12px rgba(153, 166, 249, 0.3));
        }
        .send-btn:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: var(--flows-chat-input-send-hover-shadow, var(--flows-chat-input-send-shadow, none));
        }
        .send-btn:disabled {
            transform: none;
            box-shadow: none;
        }
        .send-btn.muted {
            background: var(--flows-chat-input-button-bg, var(--glass-solid-strong, rgba(255, 255, 255, 0.12)));
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.55)));
        }
        .stop-btn {
            background: var(--flows-chat-input-danger, var(--error, #ef4444));
            color: var(--flows-chat-input-danger-color, #fff);
            box-shadow: var(--flows-chat-input-stop-shadow, 0 4px 12px rgba(239, 68, 68, 0.3));
        }
        .disclaimer {
            margin-top: 10px;
            text-align: center;
            font-size: 11px;
            line-height: 1.35;
            color: var(--flows-chat-input-muted, var(--text-tertiary, rgba(255, 255, 255, 0.42)));
        }
        svg {
            display: block;
        }
    `;

    constructor() {
        super();
        this.disabled = false;
        this.loading = false;
        this.streaming = false;
        this.cancelBusy = false;
        this.placeholder = '';
        this.accept = '';
        this.maxLength = 10000;
        this.maxFileSize = 10 * 1024 * 1024;
        this.showVoice = false;
        this.voiceDuplex = false;
        this.speechDictation = false;
        this.voiceActive = false;
        this.voiceStatus = 'idle';
        this.ttsOutputEnabled = true;
        this.showLocaleControl = false;
        this.interfaceLocale = 'auto';
        this.showDisclaimer = false;
        this.labels = {};
        this._value = '';
        this._selectedFiles = [];
        this._listening = false;
        this._rec = null;
        this._onTtsPref = () => {
            this.ttsOutputEnabled = readTtsOutputEnabled();
            this.requestUpdate();
        };
        this._onTtsStorage = (e) => {
            if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                this.ttsOutputEnabled = readTtsOutputEnabled();
                this.requestUpdate();
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPref);
            window.addEventListener('storage', this._onTtsStorage);
            this.ttsOutputEnabled = readTtsOutputEnabled();
        }
    }

    disconnectedCallback() {
        if (this._rec) {
            this._rec.stop();
            this._rec = null;
        }
        if (typeof window !== 'undefined') {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPref);
            window.removeEventListener('storage', this._onTtsStorage);
        }
        super.disconnectedCallback();
    }

    get textareaEl() {
        return this.shadowRoot?.querySelector('textarea');
    }

    get fileInputEl() {
        return this.shadowRoot?.querySelector('input[type=file]');
    }

    _l(key, fallback) {
        return _label(this.labels, key, fallback);
    }

    _dispatch(name, detail = null) {
        this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
    }

    _onInput(e) {
        this._value = e.target.value;
        this._adjustHeight();
    }

    _onKeyDown(e) {
        if (e.isComposing) {
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._send();
        }
    }

    _adjustHeight() {
        const el = this.textareaEl;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }

    _validateFile(file) {
        if (file.size <= this.maxFileSize) {
            return true;
        }
        this._dispatch('toast', {
            key: 'err_file_too_large',
            message: this._l('err_file_too_large', 'File is too large'),
            vars: {
                name: file.name,
                max: formatFileSize(this.maxFileSize),
            },
        });
        return false;
    }

    _onFilesSelected(e) {
        const files = e.target.files ? Array.from(e.target.files) : [];
        if (files.length === 0) {
            return;
        }
        const next = [];
        for (const file of files) {
            if (this._validateFile(file)) {
                next.push(file);
            }
        }
        if (next.length > 0) {
            this._selectedFiles = [...this._selectedFiles, ...next];
        }
        if (this.fileInputEl) {
            this.fileInputEl.value = '';
        }
    }

    _removeFile(index) {
        if (index < 0 || index >= this._selectedFiles.length) {
            return;
        }
        this._selectedFiles = this._selectedFiles.filter((_, i) => i !== index);
    }

    _openFilePicker() {
        this.fileInputEl?.click();
    }

    _send() {
        const message = this._value.trim();
        if ((message.length === 0 && this._selectedFiles.length === 0) || this.disabled || this.loading) {
            return;
        }
        this._dispatch('send', {
            message,
            files: this._selectedFiles,
        });
        this.clear();
    }

    _stop() {
        if (this.cancelBusy || !this.loading) {
            return;
        }
        this._dispatch('stop');
    }

    _onTtsOutputClick() {
        this._dispatch('tts-output-toggle', { enabled: !this.ttsOutputEnabled });
    }

    _speechLang() {
        const raw = String(this.interfaceLocale || '').toLowerCase();
        if (raw === 'en') return 'en-US';
        if (raw === 'ru') return 'ru-RU';
        const docLang = typeof document !== 'undefined' ? document.documentElement.lang || 'ru-RU' : 'ru-RU';
        return docLang.startsWith('en') ? 'en-US' : 'ru-RU';
    }

    _onVoiceClick() {
        if (this.voiceDuplex || !this.speechDictation) {
            this._dispatch('voice-toggle');
            return;
        }
        this._toggleSpeechDictation();
    }

    _toggleSpeechDictation() {
        const SR = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
        if (!SR) {
            this._dispatch('toast', {
                key: 'voice_not_supported',
                message: this._l('voice_not_supported', 'Voice not supported'),
            });
            return;
        }
        if (this._listening && this._rec) {
            this._rec.stop();
            this._listening = false;
            this._rec = null;
            return;
        }
        const rec = new SR();
        rec.lang = this._speechLang();
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.onresult = (ev) => {
            const text = ev.results?.[0]?.[0]?.transcript;
            if (typeof text === 'string' && text.trim() !== '') {
                const current = this._value.trim();
                this._value = current !== '' ? `${current} ${text.trim()}` : text.trim();
                this._listening = false;
                this._rec = null;
                this.requestUpdate();
                this._send();
                return;
            }
            this._listening = false;
            this._rec = null;
        };
        rec.onerror = () => {
            this._listening = false;
            this._rec = null;
        };
        rec.onend = () => {
            this._listening = false;
            this._rec = null;
        };
        this._rec = rec;
        this._listening = true;
        rec.start();
    }

    _onLocaleSelect(e) {
        const value = e.target.value;
        if (value !== 'auto' && value !== 'ru' && value !== 'en') {
            return;
        }
        this.interfaceLocale = value;
        this._dispatch('locale-change', { locale: value });
    }

    _voiceStatusHintVisible() {
        const status = typeof this.voiceStatus === 'string' ? this.voiceStatus : 'idle';
        return this.voiceActive || (status !== 'idle' && status !== 'closed');
    }

    _voiceLabel() {
        const base = this.voiceActive
            ? this._l('voice_off', 'Disable voice')
            : this._l('voice_on', 'Enable voice');
        if (!this._voiceStatusHintVisible()) {
            return base;
        }
        const status = typeof this.voiceStatus === 'string' ? this.voiceStatus : 'idle';
        const statusLabel = this._l(`voice_status_${status}`, this._l('voice_status_idle', 'Voice mode: idle'));
        return `${base}. ${statusLabel}`;
    }

    _voiceIconName() {
        if (this.speechDictation && !this.voiceDuplex) {
            return 'mic';
        }
        if (this.voiceDuplex && !this.voiceActive && (this.voiceStatus === 'idle' || this.voiceStatus === 'closed')) {
            return 'mic-off';
        }
        return this.voiceActive || this._listening || this.voiceStatus === 'listening' || this.voiceStatus === 'speaking'
            ? 'mic'
            : 'mic-off';
    }

    focus() {
        this.textareaEl?.focus();
    }

    clear() {
        this._value = '';
        this._selectedFiles = [];
        if (this.textareaEl) {
            this.textareaEl.style.height = 'auto';
        }
        if (this.fileInputEl) {
            this.fileInputEl.value = '';
        }
        this.requestUpdate();
    }

    setDraft(text) {
        if (typeof text !== 'string') {
            throw new TypeError('flows-chat-input.setDraft expects a string');
        }
        this._value = text;
        this.requestUpdate();
        void this.updateComplete.then(() => {
            this._adjustHeight();
            this.focus();
            const textarea = this.textareaEl;
            if (textarea) {
                const len = text.length;
                textarea.setSelectionRange(len, len);
            }
        });
    }

    _renderFiles() {
        if (this._selectedFiles.length === 0) {
            return nothing;
        }
        return html`
            <div class="files-preview" role="list" aria-label=${this._l('attach', 'Attachments')}>
                ${this._selectedFiles.map((file, index) => html`
                    <div class="file-item" role="listitem">
                        <platform-icon class="file-icon" file-icon name=${resolveFileIconKey(file.name, file.type)} size="20"></platform-icon>
                        <span class="file-info">
                            <span class="file-name" title=${file.name}>${file.name}</span>
                            <span class="file-size">${formatFileSize(file.size)}</span>
                        </span>
                        <button
                            type="button"
                            class="file-remove"
                            @click=${() => this._removeFile(index)}
                            title=${this._l('title_remove_file', 'Remove file')}
                            aria-label=${this._l('title_remove_file', 'Remove file')}
                        >x</button>
                    </div>
                `)}
            </div>
        `;
    }

    render() {
        const canSend =
            (this._value.trim().length > 0 || this._selectedFiles.length > 0)
            && !this.disabled
            && !this.loading;
        const showVoiceButton = this.showVoice || this.voiceDuplex || this.speechDictation;
        const ttsLabel = this.ttsOutputEnabled
            ? this._l('tts_output_disable', 'Disable spoken responses')
            : this._l('tts_output_enable', 'Enable spoken responses');
        return html`
            ${this._renderFiles()}
            <div class="input-container">
                <input
                    type="file"
                    multiple
                    accept=${this.accept}
                    @change=${this._onFilesSelected}
                />
                <button
                    type="button"
                    class="circle-btn attach-btn"
                    title=${this._l('title_attach', this._l('attach', 'Attachments'))}
                    aria-label=${this._l('title_attach', this._l('attach', 'Attachments'))}
                    ?disabled=${this.disabled || this.loading}
                    @click=${this._openFilePicker}
                >${_icon('attach')}</button>
                <div class="grow">
                    <textarea
                        data-canon="composer"
                        rows="1"
                        .value=${this._value}
                        placeholder=${this.placeholder}
                        maxlength=${this.maxLength}
                        ?disabled=${this.disabled || this.loading}
                        @input=${this._onInput}
                        @keydown=${this._onKeyDown}
                    ></textarea>
                </div>
                ${this.showLocaleControl
                    ? html`
                          <div class="locale">
                              <select .value=${this.interfaceLocale || 'auto'} @change=${this._onLocaleSelect}>
                                  <option value="auto">${this._l('locale_auto', 'Auto')}</option>
                                  <option value="ru">${this._l('locale_ru', 'Russian')}</option>
                                  <option value="en">${this._l('locale_en', 'English')}</option>
                              </select>
                          </div>
                      `
                    : nothing}
                ${showVoiceButton
                    ? html`
                          <button
                              type="button"
                              class="circle-btn ${this.ttsOutputEnabled ? 'active' : ''}"
                              title=${ttsLabel}
                              aria-label=${ttsLabel}
                              aria-pressed=${this.ttsOutputEnabled ? 'true' : 'false'}
                              ?disabled=${this.disabled}
                              @click=${this._onTtsOutputClick}
                          >${_icon(this.ttsOutputEnabled ? 'volume-up' : 'volume-off')}</button>
                          <button
                              type="button"
                              class="circle-btn ${this.voiceActive || this._listening ? 'active' : ''}"
                              title=${this._voiceLabel()}
                              aria-label=${this._voiceLabel()}
                              aria-pressed=${this.voiceDuplex && this.voiceActive ? 'true' : 'false'}
                              ?disabled=${this.disabled || this.loading}
                              @click=${this._onVoiceClick}
                          >${_icon(this._voiceIconName())}</button>
                      `
                    : nothing}
                ${this.loading
                    ? html`
                          <button
                              type="button"
                              class="circle-btn send-btn stop-btn"
                              title=${this.cancelBusy ? this._l('title_stop_pending', 'Stopping response...') : this._l('title_stop', 'Stop response')}
                              aria-label=${this.cancelBusy ? this._l('title_stop_pending', 'Stopping response...') : this._l('title_stop', 'Stop response')}
                              ?disabled=${this.cancelBusy}
                              @click=${this._stop}
                          >${_icon('stop')}</button>
                      `
                    : html`
                          <button
                              type="button"
                              class="circle-btn send-btn ${canSend ? '' : 'muted'}"
                              title=${this._l('send', 'Send')}
                              aria-label=${this._l('send', 'Send')}
                              ?disabled=${!canSend}
                              @click=${this._send}
                          >${_icon('send')}</button>
                      `}
            </div>
            ${this.showDisclaimer
                ? html`<div class="disclaimer">${this._l('ai_disclaimer', 'AI-generated content may be inaccurate.')}</div>`
                : nothing}
        `;
    }
}

customElements.define('flows-chat-input', FlowsChatInput);
