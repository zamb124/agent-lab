/**
 * platform-voice-dictation — единый UI voice→text на всю платформу.
 * VoiceMediaSession STT-only: PCM → WS /voice/api/ws/session/{id} → VAD → transcript final.
 * Событие `transcribed` detail: { text, provider }.
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import { hasGetUserMediaApi } from '../utils/voice-recording.js';
import { VoiceMediaSession } from '../voice/voice-media-session.js';
import { resolveVoiceHttpOrigin } from '../voice/voice-http-origin.js';
import './platform-icon.js';

export class PlatformVoiceDictation extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        disabled: { type: Boolean, reflect: true },
        language: { type: String },
        companyId: { type: String, attribute: 'company-id' },
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
        this.companyId = '';
        this.density = 'compact';
        this._phase = 'idle';
        this._heardFinalText = false;
        /** @type {VoiceMediaSession | null} */
        this._media = null;
        this._companyIdSel = this.select((s) => s.auth.activeCompanyId);
        this._onTranscriptBound = (event) => this._onMediaTranscript(event);
        this._onErrorBound = (event) => this._onMediaError(event);
    }

    disconnectedCallback() {
        this._teardownMedia();
        this._phase = 'idle';
        super.disconnectedCallback();
    }

    /**
     * @returns {string}
     */
    _resolveCompanyId() {
        if (typeof this.companyId === 'string' && this.companyId.trim() !== '') {
            return this.companyId.trim();
        }
        const fromAuth = this._companyIdSel.value;
        if (typeof fromAuth === 'string' && fromAuth.trim() !== '') {
            return fromAuth.trim();
        }
        throw new Error('platform-voice-dictation: company_id required');
    }

    /**
     * @returns {Record<string, string>}
     */
    _sessionQuery() {
        if (typeof this.language !== 'string' || this.language.trim() === '') {
            return {};
        }
        return { language: this.language.trim() };
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

    /**
     * @param {Event} event
     */
    _onMediaTranscript(event) {
        if (!(event instanceof Event)) {
            throw new Error('platform-voice-dictation: transcript event required');
        }
        const detail = 'detail' in event ? event.detail : null;
        if (!detail || typeof detail !== 'object') {
            throw new Error('platform-voice-dictation: transcript detail required');
        }
        if (detail.final !== true) {
            return;
        }
        const text = typeof detail.text === 'string' ? detail.text.trim() : '';
        if (text.length === 0) {
            return;
        }
        this._heardFinalText = true;
        this.emit('transcribed', { text, provider: 'voice' });
    }

    _onMediaError() {
        this._teardownMedia();
        this._phase = 'idle';
        this.toast('toast.voice_dictation.failed', { type: 'error' });
    }

    _teardownMedia() {
        if (this._media === null) {
            return;
        }
        this._media.removeEventListener('transcript', this._onTranscriptBound);
        this._media.removeEventListener('error', this._onErrorBound);
        this._media.close();
        this._media = null;
    }

    async _startSession() {
        if (typeof window === 'undefined' || !window.isSecureContext) {
            this.toast('toast.voice_dictation.unavailable_https', { type: 'warning' });
            return;
        }
        if (!hasGetUserMediaApi()) {
            this.toast('toast.voice_dictation.unavailable_recorder', { type: 'warning' });
            return;
        }
        const companyId = this._resolveCompanyId();
        const media = new VoiceMediaSession({
            baseUrl: resolveVoiceHttpOrigin(),
            sessionId: crypto.randomUUID(),
            companyId,
            query: this._sessionQuery(),
            autoRecord: true,
        });
        this._heardFinalText = false;
        this._media = media;
        media.addEventListener('transcript', this._onTranscriptBound);
        this._phase = 'recording';
        try {
            await media.connect();
        } catch (err) {
            this._teardownMedia();
            this._phase = 'idle';
            this.toast('toast.voice_dictation.failed', { type: 'error' });
            throw err;
        }
        media.addEventListener('error', this._onErrorBound);
    }

    async _stopSession() {
        this._phase = 'processing';
        const media = this._media;
        if (media !== null && media.isConnected === true) {
            await media.awaitRecordingFinalized(8000);
        }
        this._teardownMedia();
        if (!this._heardFinalText) {
            this.toast('toast.voice_dictation.empty', { type: 'warning' });
        }
        this._phase = 'idle';
    }

    async _onToggle() {
        if (this.disabled || this._phase === 'processing') {
            return;
        }
        if (this._phase === 'recording') {
            await this._stopSession();
            return;
        }
        if (this._phase !== 'idle') {
            return;
        }
        await this._startSession();
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
