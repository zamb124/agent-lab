import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

function formatDuration(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) {
        return '00:00';
    }
    const total = Math.floor(seconds);
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export class PlatformAudioMessagePlayer extends PlatformElement {
    static properties = {
        src: { type: String },
        fileName: { type: String, attribute: 'file-name' },
        durationMs: { type: Number, attribute: 'duration-ms' },
        waveform: { type: Array },
        transcriptionStatus: { type: String, attribute: 'transcription-status' },
        transcriptionText: { type: String, attribute: 'transcription-text' },
        transcriptionError: { type: String, attribute: 'transcription-error' },
        _isPlaying: { state: true },
        _currentTime: { state: true },
        _resolvedDuration: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .root {
                min-width: 220px;
                max-width: 360px;
                border: none;
                background: transparent;
                padding: 0;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .row {
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .play-btn {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                border: none;
                background: #13a75d;
                color: #fff;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 12px;
                flex-shrink: 0;
            }

            .play-btn:hover {
                filter: brightness(1.05);
            }

            .wave-wrap {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }

            .wave {
                position: relative;
                height: 16px;
                display: grid;
                grid-auto-flow: column;
                grid-auto-columns: minmax(2px, 1fr);
                align-items: end;
                gap: 2px;
            }

            .bar {
                width: 100%;
                border-radius: 999px;
                background: rgba(8, 105, 60, 0.33);
                min-height: 3px;
            }

            .bar.active {
                background: rgba(8, 105, 60, 0.88);
            }

            .time {
                font-size: 12px;
                color: rgba(6, 95, 70, 0.95);
                white-space: nowrap;
            }

            input[type='range'] {
                width: 100%;
                margin: 0;
            }

            .actions {
                display: flex;
                align-items: center;
                justify-content: flex-end;
            }

            .transcribe-btn {
                width: 24px;
                height: 24px;
                border-radius: 8px;
                border: 1px solid rgba(6, 95, 70, 0.38);
                background: rgba(255, 255, 255, 0.56);
                color: rgba(6, 95, 70, 0.95);
                cursor: pointer;
                font-size: 12px;
                font-weight: 700;
                line-height: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0;
            }

            .transcribe-btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .transcription {
                font-size: 12px;
                line-height: 1.35;
                color: rgba(6, 95, 70, 0.95);
                white-space: pre-line;
            }

            .transcription.error {
                color: #b91c1c;
            }
        `,
    ];

    constructor() {
        super();
        this.src = '';
        this.fileName = '';
        this.durationMs = 0;
        this.waveform = null;
        this.transcriptionStatus = 'idle';
        this.transcriptionText = '';
        this.transcriptionError = '';
        this._isPlaying = false;
        this._currentTime = 0;
        this._resolvedDuration = 0;
        this._onAudioTimeUpdate = this._handleAudioTimeUpdate.bind(this);
        this._onAudioLoadedMetadata = this._handleAudioLoadedMetadata.bind(this);
        this._onAudioEnded = this._handleAudioEnded.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._bindAudioListeners();
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unbindAudioListeners();
    }

    firstUpdated() {
        this._bindAudioListeners();
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        if (changedProperties.has('src')) {
            this._isPlaying = false;
            this._currentTime = 0;
            this._resolvedDuration = 0;
            this._bindAudioListeners();
        }
    }

    _audioEl() {
        return this.renderRoot?.querySelector('audio');
    }

    _bindAudioListeners() {
        this._unbindAudioListeners();
        const audio = this._audioEl();
        if (!audio) {
            return;
        }
        audio.addEventListener('timeupdate', this._onAudioTimeUpdate);
        audio.addEventListener('loadedmetadata', this._onAudioLoadedMetadata);
        audio.addEventListener('ended', this._onAudioEnded);
    }

    _unbindAudioListeners() {
        const audio = this._audioEl();
        if (!audio) {
            return;
        }
        audio.removeEventListener('timeupdate', this._onAudioTimeUpdate);
        audio.removeEventListener('loadedmetadata', this._onAudioLoadedMetadata);
        audio.removeEventListener('ended', this._onAudioEnded);
    }

    _handleAudioTimeUpdate() {
        const audio = this._audioEl();
        if (!audio) {
            return;
        }
        this._currentTime = audio.currentTime;
    }

    _handleAudioLoadedMetadata() {
        const audio = this._audioEl();
        if (!audio) {
            return;
        }
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
            this._resolvedDuration = audio.duration;
        }
    }

    _handleAudioEnded() {
        this._isPlaying = false;
        this._currentTime = 0;
    }

    _effectiveDuration() {
        if (this._resolvedDuration > 0) {
            return this._resolvedDuration;
        }
        if (Number.isFinite(this.durationMs) && this.durationMs > 0) {
            return this.durationMs / 1000;
        }
        return 0;
    }

    async _togglePlay() {
        const audio = this._audioEl();
        if (!audio) {
            throw new Error('Audio element not found.');
        }
        if (this._isPlaying) {
            audio.pause();
            this._isPlaying = false;
            return;
        }
        await audio.play();
        this._isPlaying = true;
    }

    _seek(e) {
        const audio = this._audioEl();
        if (!audio) {
            throw new Error('Audio element not found.');
        }
        const value = Number(e.target.value);
        if (!Number.isFinite(value) || value < 0) {
            return;
        }
        audio.currentTime = value;
        this._currentTime = value;
    }

    _requestTranscription() {
        this.dispatchEvent(new CustomEvent('request-transcription', {
            bubbles: true,
            composed: true,
        }));
    }

    _bars() {
        if (Array.isArray(this.waveform) && this.waveform.length > 0) {
            return this.waveform.slice(0, 48).map((v) => {
                if (typeof v !== 'number' || !Number.isFinite(v)) {
                    return 5;
                }
                return Math.max(3, Math.min(16, Math.round(v)));
            });
        }
        return [4, 7, 10, 12, 8, 6, 9, 11, 8, 5, 7, 10, 12, 9, 6, 8, 10, 6, 5, 8, 11, 9, 7, 5];
    }

    render() {
        if (typeof this.src !== 'string' || this.src === '') {
            throw new Error('src обязателен для audio player.');
        }
        const duration = this._effectiveDuration();
        const current = Math.min(this._currentTime, duration || 0);
        const bars = this._bars();
        const activeRatio = duration > 0 ? current / duration : 0;
        const activeBarsCount = Math.floor(activeRatio * bars.length);
        const transcribeLoading = this.transcriptionStatus === 'processing';
        const transcribeDone = this.transcriptionStatus === 'done';
        const transcribeFailed = this.transcriptionStatus === 'failed';

        return html`
            <div class="root">
                <audio preload="metadata" src=${this.src}></audio>
                <div class="row">
                    <button class="play-btn" type="button" @click=${this._togglePlay}>
                        ${this._isPlaying ? 'II' : '▶'}
                    </button>
                    <div class="wave-wrap">
                        <div class="wave" aria-hidden="true">
                            ${bars.map((h, idx) => html`
                                <span class="bar ${idx <= activeBarsCount ? 'active' : ''}" style=${`height:${h}px`}></span>
                            `)}
                        </div>
                        <input
                            type="range"
                            min="0"
                            max=${duration > 0 ? duration : 0}
                            step="0.01"
                            .value=${current}
                            @input=${this._seek}
                        />
                    </div>
                    <span class="time">${formatDuration(current)} / ${formatDuration(duration)}</span>
                    <div class="actions">
                        <button
                            type="button"
                            class="transcribe-btn"
                            title="Расшифровать"
                            ?disabled=${transcribeLoading}
                            @click=${this._requestTranscription}
                        >A</button>
                    </div>
                </div>
                ${transcribeLoading ? html`<div class="transcription">Расшифровка...</div>` : ''}
                ${transcribeDone && this.transcriptionText
                    ? html`<div class="transcription">${this.transcriptionText}</div>`
                    : ''}
                ${transcribeFailed && this.transcriptionError
                    ? html`<div class="transcription error">${this.transcriptionError}</div>`
                    : ''}
            </div>
        `;
    }
}

customElements.define('platform-audio-message-player', PlatformAudioMessagePlayer);
