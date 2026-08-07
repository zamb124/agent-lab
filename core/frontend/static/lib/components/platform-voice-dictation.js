/**
 * platform-voice-dictation — единый UI voice→text на всю платформу.
 * MediaRecorder → platform/voice_dictation → POST /voice/api/v1/transcribe.
 * Событие `transcribed` detail: { text, provider }.
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import {
    getUserMediaCompat,
    hasGetUserMediaApi,
    pickVoiceMimeType,
} from '../utils/voice-recording.js';
import './platform-icon.js';

const OP_NAME = 'platform/voice_dictation';

/**
 * @param {string} mimeType
 * @returns {string}
 */
function fileNameForMime(mimeType) {
    if (typeof mimeType !== 'string' || mimeType.length === 0) {
        return 'voice-input.webm';
    }
    if (mimeType.includes('mp4')) {
        return 'voice-input.m4a';
    }
    if (mimeType.includes('ogg')) {
        return 'voice-input.ogg';
    }
    return 'voice-input.webm';
}

export class PlatformVoiceDictation extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        disabled: { type: Boolean, reflect: true },
        language: { type: String },
        density: { type: String, reflect: true },
        _phase: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                flex: 0 0 auto;
                align-items: center;
            }

            button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 999px);
                background: transparent;
                color: var(--text-secondary, #6b7280);
                cursor: pointer;
                transition: var(--motion-transition-interactive, background 0.15s ease, color 0.15s ease);
            }

            :host([density='dense']) button {
                width: 28px;
                height: 28px;
            }

            button:hover:not(:disabled) {
                background: var(--bg-hover, rgba(0, 0, 0, 0.06));
                color: var(--text-primary, #111827);
            }

            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            button.recording {
                background: var(--accent-secondary, #ef4444);
                color: #ffffff;
            }

            button.processing {
                opacity: 0.55;
                cursor: progress;
            }
        `,
    ];

    constructor() {
        super();
        this.disabled = false;
        this.language = '';
        this.density = 'compact';
        this._phase = 'idle';
        /** @type {MediaRecorder | null} */
        this._mediaRecorder = null;
        /** @type {Blob[]} */
        this._audioChunks = [];
        this._voice = this.useOp(OP_NAME);
        this.useEvent(this._voice.op.events.SUCCEEDED, (event) => {
            this._phase = 'idle';
            this._mediaRecorder = null;
            this._audioChunks = [];
            const result = event && event.payload && event.payload.result;
            if (!result || typeof result !== 'object') {
                this.toast('toast.voice_dictation.empty', { type: 'warning' });
                return;
            }
            const text = typeof result.text === 'string' ? result.text.trim() : '';
            if (text.length === 0) {
                this.toast('toast.voice_dictation.empty', { type: 'warning' });
                return;
            }
            const provider = typeof result.provider === 'string' ? result.provider : '';
            this.emit('transcribed', { text, provider });
        });
        this.useEvent(this._voice.op.events.FAILED, () => {
            this._phase = 'idle';
            this._mediaRecorder = null;
            this._audioChunks = [];
        });
    }

    disconnectedCallback() {
        if (this._mediaRecorder !== null && this._mediaRecorder.state === 'recording') {
            this._mediaRecorder.stop();
        }
        this._mediaRecorder = null;
        this._audioChunks = [];
        super.disconnectedCallback();
    }

    /**
     * @returns {string}
     */
    _tooltip() {
        if (this._phase === 'recording') {
            return this.t('voice_dictation.stop');
        }
        if (this._phase === 'processing') {
            return this.t('voice_dictation.processing');
        }
        return this.t('voice_dictation.start');
    }

    async _onToggle() {
        if (this.disabled || this._phase === 'processing') {
            return;
        }
        if (this._phase === 'recording') {
            if (this._mediaRecorder !== null && this._mediaRecorder.state === 'recording') {
                this._mediaRecorder.stop();
            }
            return;
        }
        if (this._phase !== 'idle') {
            return;
        }
        if (typeof window === 'undefined' || !window.isSecureContext) {
            this.toast('toast.voice_dictation.unavailable_https', { type: 'warning' });
            return;
        }
        if (!hasGetUserMediaApi() || typeof MediaRecorder === 'undefined') {
            this.toast('toast.voice_dictation.unavailable_recorder', { type: 'warning' });
            return;
        }

        const stream = await getUserMediaCompat({ audio: true });
        const mimeType = pickVoiceMimeType();
        this._mediaRecorder = mimeType
            ? new MediaRecorder(stream, { mimeType })
            : new MediaRecorder(stream);
        this._audioChunks = [];
        const resolvedMime = this._mediaRecorder.mimeType || mimeType || 'audio/webm';
        this._mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                this._audioChunks.push(e.data);
            }
        };
        this._mediaRecorder.onstop = () => {
            stream.getTracks().forEach((track) => track.stop());
            this._phase = 'processing';
            const blob = new Blob(this._audioChunks, { type: resolvedMime });
            const payload = {
                audio: blob,
                file_name: fileNameForMime(resolvedMime),
            };
            if (typeof this.language === 'string' && this.language.length > 0) {
                payload.language = this.language;
            }
            this._voice.run(payload);
        };
        this._mediaRecorder.start();
        this._phase = 'recording';
    }

    render() {
        const phaseClass = this._phase === 'idle' ? '' : this._phase;
        const iconName = this._phase === 'recording' ? 'square' : 'mic';
        return html`
            <button
                type="button"
                class=${phaseClass}
                title=${this._tooltip()}
                aria-label=${this._tooltip()}
                ?disabled=${this.disabled || this._phase === 'processing'}
                @click=${() => this._onToggle()}
            >
                <platform-icon name=${iconName} size="16"></platform-icon>
            </button>
        `;
    }
}

customElements.define('platform-voice-dictation', PlatformVoiceDictation);
