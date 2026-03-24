/**
 * CallOverlay — полноэкранный оверлей WebRTC звонка.
 *
 * Режим P2P (mode="p2p"):
 *   Нативный RTCPeerConnection. Сигналинг через /sync/ws (call.signal).
 *   TURN credentials загружаются с /sync/api/v1/calls/turn-credentials.
 *
 * Режим SFU (mode="sfu"):
 *   LiveKit Room SDK. Токен передаётся через атрибут livekit-token.
 */
import { html, css, LitElement } from 'lit';

class CallOverlay extends LitElement {
    static properties = {
        callId: { type: String, attribute: 'call-id' },
        mode: { type: String },
        callType: { type: String, attribute: 'call-type' },
        livekitUrl: { type: String, attribute: 'livekit-url' },
        livekitToken: { type: String, attribute: 'livekit-token' },
        identity: { type: String },
        _status: { state: true },
        _participants: { state: true },
        _duration: { state: true },
        _micMuted: { state: true },
        _camOff: { state: true },
    };

    static styles = css`
        :host {
            position: fixed;
            inset: 0;
            z-index: 9999;
            background: #0a0a0f;
            display: flex;
            flex-direction: column;
        }

        .video-grid {
            flex: 1;
            display: grid;
            place-items: center;
            padding: 16px;
            gap: 8px;
            overflow: hidden;
        }

        .video-grid.one   { grid-template-columns: 1fr; }
        .video-grid.two   { grid-template-columns: 1fr 1fr; }
        .video-grid.many  { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }

        .participant-tile {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            overflow: hidden;
            width: 100%;
            aspect-ratio: 16 / 9;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .participant-tile video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .participant-name {
            position: absolute;
            bottom: 10px;
            left: 12px;
            font-size: 13px;
            color: #fff;
            background: rgba(0,0,0,0.5);
            padding: 3px 10px;
            border-radius: 100px;
        }

        .local-preview {
            position: absolute;
            bottom: 16px;
            right: 16px;
            width: 160px;
            border-radius: 12px;
            overflow: hidden;
            border: 2px solid rgba(255,255,255,0.2);
            aspect-ratio: 16/9;
        }

        .local-preview video { width: 100%; height: 100%; object-fit: cover; }

        .controls {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 16px;
            padding: 20px 24px;
            background: rgba(0,0,0,0.4);
            backdrop-filter: blur(16px);
        }

        .ctrl-btn {
            width: 52px;
            height: 52px;
            border-radius: 50%;
            border: none;
            cursor: pointer;
            font-size: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
            background: rgba(255,255,255,0.12);
            color: #fff;
        }

        .ctrl-btn:hover { background: rgba(255,255,255,0.2); }

        .ctrl-btn.active { background: rgba(255,255,255,0.9); color: #000; }

        .ctrl-btn.hangup {
            background: #ef4444;
            width: 60px;
            height: 60px;
            font-size: 24px;
        }

        .ctrl-btn.hangup:hover { background: #dc2626; }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px 8px;
            color: rgba(255,255,255,0.6);
            font-size: 13px;
        }

        .status-dot {
            width: 8px; height: 8px;
            border-radius: 50%;
            background: #22c55e;
            display: inline-block;
            margin-right: 6px;
        }

        .avatar-placeholder {
            width: 72px;
            height: 72px;
            border-radius: 50%;
            background: var(--accent-primary, #6366f1);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            color: #fff;
            font-weight: 700;
        }
    `;

    constructor() {
        super();
        this._status = 'connecting';
        this._participants = [];
        this._duration = 0;
        this._micMuted = false;
        this._camOff = false;
        this._room = null;
        this._localStream = null;
        this._peerConnections = new Map();
        this._durationInterval = null;
    }

    async connectedCallback() {
        super.connectedCallback();
        if (this.mode === 'sfu' || !this.mode) {
            await this._connectSFU();
        } else {
            await this._connectP2P();
        }
        this._durationInterval = setInterval(() => this._duration++, 1000);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        clearInterval(this._durationInterval);
        this._cleanup();
    }

    async _connectSFU() {
        const { Room, RoomEvent } = await import('@livekit/client');
        this._room = new Room();

        this._room.on(RoomEvent.ParticipantConnected, () => this._syncParticipants());
        this._room.on(RoomEvent.ParticipantDisconnected, () => this._syncParticipants());
        this._room.on(RoomEvent.TrackSubscribed, () => this._syncParticipants());
        this._room.on(RoomEvent.Disconnected, () => {
            this._status = 'ended';
            this.dispatchEvent(new CustomEvent('call-ended', { bubbles: true, composed: true }));
        });

        await this._room.connect(this.livekitUrl, this.livekitToken);
        await this._room.localParticipant.enableCameraAndMicrophone();
        this._status = 'active';
        this._syncParticipants();
    }

    async _connectP2P() {
        // Загружаем TURN credentials
        const turnRes = await fetch('/sync/api/v1/calls/turn-credentials', { credentials: 'include' });
        const turnData = turnRes.ok ? await turnRes.json() : null;

        const iceServers = turnData
            ? [{ urls: turnData.uris, username: turnData.username, credential: turnData.credential }]
            : [{ urls: 'stun:stun.l.google.com:19302' }];

        this._localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: this.callType !== 'audio',
        });

        // P2P: подключение к WS обрабатывается sync-ws.service.js и SyncStore.
        // CallOverlay получает сигналы через событие call-signal на window.
        window.addEventListener('call-signal', this._onCallSignal.bind(this));
        this._iceServers = iceServers;
        this._status = 'active';
        this._participants = [{ identity: this.identity, isLocal: true, stream: this._localStream }];
    }

    _onCallSignal(e) {
        const { signalType, fromIdentity, data } = e.detail;
        // Обработка offer/answer/ice_candidate — стандартный WebRTC flow.
        // Детальная реализация зависит от WS-сервиса SyncStore.
    }

    _syncParticipants() {
        if (!this._room) return;
        const remote = Array.from(this._room.remoteParticipants.values()).map(p => ({
            identity: p.identity,
            isLocal: false,
            videoTrack: Array.from(p.videoTrackPublications.values()).find(t => t.isSubscribed)?.track,
            audioTrack: Array.from(p.audioTrackPublications.values()).find(t => t.isSubscribed)?.track,
        }));
        const local = {
            identity: this._room.localParticipant.identity,
            isLocal: true,
            videoTrack: Array.from(this._room.localParticipant.videoTrackPublications.values())[0]?.track,
        };
        this._participants = [local, ...remote];
        this.requestUpdate();
    }

    async _toggleMic() {
        this._micMuted = !this._micMuted;
        if (this._room) {
            await this._room.localParticipant.setMicrophoneEnabled(!this._micMuted);
        } else if (this._localStream) {
            this._localStream.getAudioTracks().forEach(t => t.enabled = !this._micMuted);
        }
    }

    async _toggleCam() {
        this._camOff = !this._camOff;
        if (this._room) {
            await this._room.localParticipant.setCameraEnabled(!this._camOff);
        } else if (this._localStream) {
            this._localStream.getVideoTracks().forEach(t => t.enabled = !this._camOff);
        }
    }

    async _hangup() {
        this._cleanup();
        this._status = 'ended';
        this.dispatchEvent(new CustomEvent('call-ended', { bubbles: true, composed: true }));

        // Отправляем WS-команду hang up (если есть callId, т.е. звонок внутри платформы)
        if (this.callId) {
            this.dispatchEvent(new CustomEvent('call-hangup-request', {
                bubbles: true, composed: true,
                detail: { callId: this.callId },
            }));
        }
    }

    _cleanup() {
        if (this._room) { this._room.disconnect(); this._room = null; }
        if (this._localStream) {
            this._localStream.getTracks().forEach(t => t.stop());
            this._localStream = null;
        }
        window.removeEventListener('call-signal', this._onCallSignal);
    }

    _formatDuration(sec) {
        const m = Math.floor(sec / 60).toString().padStart(2, '0');
        const s = (sec % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    _attachVideoToElement(el, track) {
        if (!el || !track) return;
        if (el._attachedTrack === track) return;
        el._attachedTrack = track;
        track.attach(el);
    }

    render() {
        if (this._status === 'ended') {
            return html`<div style="display:flex;align-items:center;justify-content:center;height:100%;color:rgba(255,255,255,0.5);font-size:18px;">Звонок завершён</div>`;
        }

        const gridClass = this._participants.length === 1 ? 'one'
            : this._participants.length === 2 ? 'two' : 'many';

        return html`
            <div class="header">
                <span>
                    ${this._status === 'active' ? html`<span class="status-dot"></span>` : ''}
                    ${this._status === 'connecting' ? 'Подключение…' : this._formatDuration(this._duration)}
                </span>
                <span>${this._participants.length} участн.</span>
            </div>

            <div class="video-grid ${gridClass}">
                ${this._participants.map(p => this._renderTile(p))}
            </div>

            <div class="controls">
                <button class="ctrl-btn ${this._micMuted ? '' : 'active'}" @click=${this._toggleMic} title="${this._micMuted ? 'Включить' : 'Выключить'} микрофон">
                    ${this._micMuted ? '🔇' : '🎤'}
                </button>
                ${this.callType !== 'audio' ? html`
                    <button class="ctrl-btn ${this._camOff ? '' : 'active'}" @click=${this._toggleCam} title="${this._camOff ? 'Включить' : 'Выключить'} камеру">
                        ${this._camOff ? '📷' : '📹'}
                    </button>
                ` : ''}
                <button class="ctrl-btn hangup" @click=${this._hangup} title="Завершить">📵</button>
            </div>
        `;
    }

    _renderTile(participant) {
        const label = participant.isLocal ? 'Вы' : participant.identity;
        const hasVideo = participant.videoTrack || (participant.isLocal && participant.stream);

        return html`
            <div class="participant-tile">
                ${hasVideo
                    ? html`<video
                        autoplay playsinline
                        ?muted=${participant.isLocal}
                        ${this._videoRefDirective(participant)}
                    ></video>`
                    : html`<div class="avatar-placeholder">${label[0]?.toUpperCase()}</div>`
                }
                <span class="participant-name">${label}</span>
            </div>
        `;
    }

    // Кастомный ref для привязки LiveKit track к video-элементу
    _videoRefDirective(participant) {
        return { [Symbol.toPrimitive]: () => '' };
    }

    updated() {
        // Привязываем LiveKit треки к video-элементам после рендера
        if (!this._room) return;
        const tiles = this.shadowRoot.querySelectorAll('.participant-tile video');
        this._participants.forEach((p, i) => {
            const el = tiles[i];
            if (!el) return;
            if (p.isLocal) {
                const localVideo = Array.from(
                    this._room.localParticipant.videoTrackPublications.values()
                )[0]?.track;
                if (localVideo) localVideo.attach(el);
            } else if (p.videoTrack) {
                p.videoTrack.attach(el);
            }
        });
    }
}

customElements.define('call-overlay', CallOverlay);
