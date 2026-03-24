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

const LS_CAMERA_KEY = 'humanitec.sync.call.camera_enabled';

function _readCameraPref() {
    try {
        const v = localStorage.getItem(LS_CAMERA_KEY);
        if (v === null) return true;
        return v === 'true';
    } catch {
        return true;
    }
}

function _writeCameraPref(on) {
    try {
        localStorage.setItem(LS_CAMERA_KEY, String(on));
    } catch {
        /* ignore */
    }
}

class CallOverlay extends LitElement {
    static properties = {
        callId:      { type: String, attribute: 'call-id' },
        channelId:   { type: String, attribute: 'channel-id' },
        mode:        { type: String },
        callType:    { type: String, attribute: 'call-type' },
        livekitUrl:  { type: String, attribute: 'livekit-url' },
        livekitToken: { type: String, attribute: 'livekit-token' },
        identity:    { type: String },
        names:       { type: Object },
        _status:      { state: true },
        _error:       { state: true },
        _participants: { state: true },
        _duration:    { state: true },
        _micMuted:    { state: true },
        _camOff:      { state: true },
        _tiles:       { state: true },
        _fullscreenTileKey: { state: true },
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

        .participant-tile.screen video {
            object-fit: contain;
            background: #000;
        }

        .participant-tile:fullscreen,
        .participant-tile:-webkit-full-screen {
            width: 100%;
            height: 100%;
            max-width: none;
            max-height: none;
            aspect-ratio: auto;
            border-radius: 0;
        }

        .participant-tile:fullscreen video,
        .participant-tile:-webkit-full-screen video {
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #000;
        }

        .tile-fs-btn {
            position: absolute;
            top: 8px;
            right: 8px;
            width: 36px;
            height: 36px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0,0,0,0.55);
            color: #fff;
            z-index: 2;
            transition: background 0.15s;
        }

        .tile-fs-btn:hover {
            background: rgba(0,0,0,0.75);
        }

        .tile-fs-btn.active {
            background: rgba(99,102,241,0.85);
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
        this._error = null;
        this._participants = [];
        this._tiles = [];
        this._duration = 0;
        this._micMuted = false;
        this._camOff = false;
        this._room = null;
        this._connecting = false;
        this._localStream = null;
        this._peerConnections = new Map();
        this._durationInterval = null;
        /** После hangup / Disconnect токен ещё в атрибутах — без флага updated() снова вызовет _connectSFU(). */
        this._sfuSessionFinished = false;
        this._fullscreenTileKey = null;
        this._onFullscreenChange = this._onFullscreenChange.bind(this);
    }

    _onFullscreenChange() {
        const el = document.fullscreenElement ?? document.webkitFullscreenElement;
        if (!el || !this.shadowRoot?.contains(el)) {
            this._fullscreenTileKey = null;
        } else {
            this._fullscreenTileKey = el.getAttribute('data-tile-key');
        }
        this.requestUpdate();
    }

    _exitTileFullscreenIfOurs() {
        const el = document.fullscreenElement ?? document.webkitFullscreenElement;
        if (el && this.shadowRoot?.contains(el)) {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
        }
    }

    _onTileFullscreenClick(e) {
        e.stopPropagation();
        const tile = e.currentTarget.closest('.participant-tile');
        if (!tile || !tile.querySelector('video')) return;
        const doc = document;
        const current = doc.fullscreenElement ?? doc.webkitFullscreenElement;
        if (current === tile) {
            if (doc.exitFullscreen) doc.exitFullscreen();
            else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
            return;
        }
        if (tile.requestFullscreen) {
            tile.requestFullscreen();
        } else if (tile.webkitRequestFullscreen) {
            tile.webkitRequestFullscreen();
        }
    }

    _tileFullscreenButton(tileKey, hasVideo) {
        if (!hasVideo) return html``;
        const active = this._fullscreenTileKey === tileKey;
        return html`
            <button
                type="button"
                class="tile-fs-btn ${active ? 'active' : ''}"
                title="${active ? 'Выйти из полного экрана' : 'На весь экран'}"
                @click=${this._onTileFullscreenClick}
            >
                ${active
                    ? html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`
                    : html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>`
                }
            </button>
        `;
    }

    async connectedCallback() {
        super.connectedCallback();
        document.addEventListener('fullscreenchange', this._onFullscreenChange);
        document.addEventListener('webkitfullscreenchange', this._onFullscreenChange);
        this._durationInterval = setInterval(() => this._duration++, 1000);
        if (this.mode !== 'sfu' && this.mode) {
            try {
                await this._connectP2P();
            } catch (err) {
                this._error = err.message;
                this._status = 'error';
            }
        }
    }


    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('fullscreenchange', this._onFullscreenChange);
        document.removeEventListener('webkitfullscreenchange', this._onFullscreenChange);
        this._sfuSessionFinished = true;
        clearInterval(this._durationInterval);
        this._cleanup();
    }

    _orderedVideoPubs(participant, isLocal) {
        const Track = this._lk.Track;
        const pubs = Array.from(participant.videoTrackPublications.values()).filter(
            (p) => p.track && (isLocal || p.isSubscribed)
        );
        pubs.sort((a, b) => {
            const sa = a.source === Track.Source.ScreenShare ? 0 : 1;
            const sb = b.source === Track.Source.ScreenShare ? 0 : 1;
            return sa - sb;
        });
        return pubs;
    }

    async _connectSFU() {
        if (!this.livekitToken || !this.livekitUrl) {
            throw new Error('livekitToken и livekitUrl обязательны для SFU подключения.');
        }
        // Предотвращаем двойной вызов (race condition в updated())
        if (this._connecting) return;
        this._connecting = true;

        this._lk = await import('@livekit/client');
        const { Room, RoomEvent } = this._lk;
        this._room = new Room();

        this._room.on(RoomEvent.ParticipantConnected, () => this._syncParticipants());
        this._room.on(RoomEvent.ParticipantDisconnected, () => this._syncParticipants());
        this._room.on(RoomEvent.TrackSubscribed, () => this._syncParticipants());
        this._room.on(RoomEvent.LocalTrackPublished, () => this._syncParticipants());
        this._room.on(RoomEvent.LocalTrackUnpublished, () => this._syncParticipants());
        this._room.on(RoomEvent.Disconnected, () => {
            this._sfuSessionFinished = true;
            if (this._status === 'ended') return;
            this._status = 'ended';
            // Только UI: hangup на сервер уже ушёл при клике «Завершить» или пришёл call.ended по WS.
            this.dispatchEvent(new CustomEvent('call-ended', { bubbles: true, composed: true }));
        });

        await this._room.connect(this.livekitUrl, this.livekitToken);
        await this._room.localParticipant.enableCameraAndMicrophone();
        const camOn = _readCameraPref();
        await this._room.localParticipant.setCameraEnabled(camOn);
        this._camOff = !camOn;
        this._status = 'active';
        this._connecting = false;
        this._syncParticipants();
    }

    async _connectP2P() {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error(
                'WebRTC недоступен: страница должна открываться через HTTPS или localhost. ' +
                'Текущий адрес: ' + window.location.origin
            );
        }

        const turnRes = await fetch('/sync/api/v1/calls/turn-credentials', { credentials: 'include' });
        if (!turnRes.ok) {
            throw new Error(`Не удалось получить TURN credentials: ${turnRes.status}`);
        }
        const turnData = await turnRes.json();
        const iceServers = [{ urls: turnData.uris, username: turnData.username, credential: turnData.credential }];

        this._localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: true,
        });
        const camOn = _readCameraPref();
        this._localStream.getVideoTracks().forEach((t) => {
            t.enabled = camOn;
        });
        this._camOff = !camOn;

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
        if (!this._room || !this._lk) return;
        const Track = this._lk.Track;
        const tiles = [];
        const local = this._room.localParticipant;
        const localPubs = this._orderedVideoPubs(local, true);
        if (localPubs.length === 0) {
            tiles.push({
                key: 'local-ph',
                identity: local.identity,
                isLocal: true,
                track: null,
                isScreen: false,
            });
        } else {
            for (const pub of localPubs) {
                tiles.push({
                    key: `local-${pub.source}`,
                    identity: local.identity,
                    isLocal: true,
                    track: pub.track,
                    isScreen: pub.source === Track.Source.ScreenShare,
                });
            }
        }
        for (const remote of this._room.remoteParticipants.values()) {
            const pubs = this._orderedVideoPubs(remote, false);
            if (pubs.length === 0) {
                tiles.push({
                    key: `remote-${remote.identity}-ph`,
                    identity: remote.identity,
                    isLocal: false,
                    track: null,
                    isScreen: false,
                });
            } else {
                for (const pub of pubs) {
                    tiles.push({
                        key: `remote-${remote.identity}-${pub.source}`,
                        identity: remote.identity,
                        isLocal: false,
                        track: pub.track,
                        isScreen: pub.source === Track.Source.ScreenShare,
                    });
                }
            }
        }
        this._tiles = tiles;
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
            _writeCameraPref(!this._camOff);
        } else if (this._localStream) {
            this._localStream.getVideoTracks().forEach((t) => {
                t.enabled = !this._camOff;
            });
            _writeCameraPref(!this._camOff);
        }
    }

    _canScreenShare() {
        return typeof navigator.mediaDevices?.getDisplayMedia === 'function';
    }

    async _toggleScreenShare() {
        if (!this._room) return;
        try {
            const next = !this._room.localParticipant.isScreenShareEnabled;
            await this._room.localParticipant.setScreenShareEnabled(next);
            this.requestUpdate();
        } catch (e) {
            const name = e && typeof e === 'object' && 'name' in e ? e.name : '';
            if (name === 'NotAllowedError' || name === 'AbortError') return;
            this._error = e instanceof Error ? e.message : String(e);
        }
    }

    async _copyLink() {
        if (!this.callId) return;
        const res = await fetch('/sync/api/v1/calls/links', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                channel_id: this.channelId,
                call_type: 'video',
                call_id: this.callId,
            }),
        });
        if (!res.ok) return;
        const { join_url } = await res.json();
        await navigator.clipboard.writeText(join_url).catch(() => {});
        const btn = this.shadowRoot.querySelector('[title="Скопировать ссылку на звонок"]');
        if (btn) {
            const orig = btn.innerHTML;
            btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
            setTimeout(() => { btn.innerHTML = orig; }, 2000);
        }
    }

    async _hangup() {
        this._sfuSessionFinished = true;
        this._status = 'ended';
        this._cleanup();
        this.dispatchEvent(new CustomEvent('call-ended', { bubbles: true, composed: true }));
        if (this.callId) {
            this.dispatchEvent(new CustomEvent('call-hangup-request', {
                bubbles: true, composed: true,
                detail: { callId: this.callId },
            }));
        }
    }

    _cleanup() {
        this._exitTileFullscreenIfOurs();
        this._fullscreenTileKey = null;
        this._connecting = false;
        if (this._room) { this._room.disconnect(); this._room = null; }
        if (this._localStream) {
            this._localStream.getTracks().forEach(t => t.stop());
            this._localStream = null;
        }
        window.removeEventListener('call-signal', this._onCallSignal);
        this._lk = null;
        this._tiles = [];
    }

    _sfuParticipantCount() {
        if (!this._room) return 0;
        return 1 + this._room.remoteParticipants.size;
    }

    _formatDuration(sec) {
        const m = Math.floor(sec / 60).toString().padStart(2, '0');
        const s = (sec % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    render() {
        if (this._status === 'error') {
            return html`
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:20px;padding:32px;">
                    <div style="font-size:48px;">⚠️</div>
                    <div style="color:#f87171;font-size:16px;font-weight:600;text-align:center;">Ошибка звонка</div>
                    <div style="color:rgba(255,255,255,0.6);font-size:13px;text-align:center;max-width:400px;">${this._error}</div>
                    <button class="ctrl-btn hangup" @click=${this._hangup}>Закрыть</button>
                </div>
            `;
        }
        if (this._status === 'ended') {
            return html`<div style="display:flex;align-items:center;justify-content:center;height:100%;color:rgba(255,255,255,0.5);font-size:18px;">Звонок завершён</div>`;
        }

        const gridItems = this._room ? this._tiles : this._participants;
        const gridCount = gridItems.length;
        const gridClass = gridCount === 1 ? 'one' : gridCount === 2 ? 'two' : 'many';
        const participantCount = this._room ? this._sfuParticipantCount() : this._participants.length;
        const screenOn = this._room?.localParticipant?.isScreenShareEnabled === true;

        return html`
            <div class="header">
                <span>
                    ${this._status === 'active' ? html`<span class="status-dot"></span>` : ''}
                    ${this._status === 'connecting' ? 'Подключение…' : this._formatDuration(this._duration)}
                </span>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="opacity:0.5">${participantCount} уч.</span>
                    ${this.callId ? html`
                        <button class="ctrl-btn" style="width:36px;height:36px;font-size:14px;" @click=${this._copyLink} title="Скопировать ссылку на звонок">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                                <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
                            </svg>
                        </button>
                    ` : ''}
                </div>
            </div>

            <div class="video-grid ${gridClass}">
                ${gridItems.map((p, i) => this._renderTile(p, i))}
            </div>

            <div class="controls">
                <button class="ctrl-btn ${this._micMuted ? '' : 'active'}" @click=${this._toggleMic} title="${this._micMuted ? 'Включить' : 'Выключить'} микрофон">
                    ${this._micMuted
                        ? html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 005.12 2.12M15 9.34V4a3 3 0 00-5.94-.6"/><path d="M17 16.95A7 7 0 015 12v-2m14 0v2a7 7 0 01-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`
                        : html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`
                    }
                </button>
                <button class="ctrl-btn ${this._camOff ? '' : 'active'}" @click=${this._toggleCam} title="${this._camOff ? 'Включить' : 'Выключить'} камеру">
                    ${this._camOff
                        ? html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 16v1a2 2 0 01-2 2H3a2 2 0 01-2-2V7a2 2 0 012-2h2m5.66 0H14a2 2 0 012 2v3.34l1 1L23 7v10"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
                        : html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>`
                    }
                </button>
                ${this._room && this._canScreenShare() ? html`
                    <button class="ctrl-btn ${screenOn ? 'active' : ''}" @click=${this._toggleScreenShare} title="${screenOn ? 'Остановить экран' : 'Показать экран'}">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                            <line x1="8" y1="21" x2="16" y2="21"/>
                            <line x1="12" y1="17" x2="12" y2="21"/>
                        </svg>
                    </button>
                ` : ''}
                <button class="ctrl-btn hangup" @click=${this._hangup} title="Завершить звонок">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C9.6 21 3 14.4 3 6c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1L6.6 10.8z"/>
                    </svg>
                </button>
            </div>
        `;
    }

    _resolveDisplayName(identity) {
        if (!identity) return '?';
        // Гость: "guest:{uuid}:{name}"
        if (identity.startsWith('guest:')) {
            const parts = identity.split(':');
            return parts.slice(2).join(':') || 'Гость';
        }
        // Зарегистрированный: смотрим в переданную карту имён
        return this.names?.[identity] || identity;
    }

    _renderTile(item, index) {
        if (this._room) {
            const label = item.isLocal ? 'Вы' : this._resolveDisplayName(item.identity);
            const displayLabel = item.isScreen ? `${label} — экран` : label;
            const hasVideo = item.track != null;
            const tileClass = item.isScreen ? 'participant-tile screen' : 'participant-tile';
            const tileKey = item.key;
            return html`
                <div class="${tileClass}" data-idx=${index} data-tile-key=${tileKey}>
                    ${this._tileFullscreenButton(tileKey, hasVideo)}
                    ${hasVideo
                        ? html`<video autoplay playsinline ?muted=${item.isLocal}></video>`
                        : html`<div class="avatar-placeholder">${displayLabel?.[0]?.toUpperCase() ?? '?'}</div>`
                    }
                    <span class="participant-name">${displayLabel}</span>
                </div>
            `;
        }
        const participant = item;
        const label = participant.isLocal ? 'Вы' : this._resolveDisplayName(participant.identity);
        const stream = participant.stream;
        const hasVideo = stream?.getVideoTracks().some((t) => t.readyState === 'live' && t.enabled);
        const tileKey = `p2p-${index}`;
        return html`
            <div class="participant-tile" data-idx=${index} data-tile-key=${tileKey}>
                ${this._tileFullscreenButton(tileKey, hasVideo)}
                ${hasVideo
                    ? html`<video autoplay playsinline muted></video>`
                    : html`<div class="avatar-placeholder">${label?.[0]?.toUpperCase() ?? '?'}</div>`
                }
                <span class="participant-name">${label}</span>
            </div>
        `;
    }

    updated(changedProps) {
        // SFU: один раз при появлении токена. После hangup токен не сбрасываем — без _sfuSessionFinished был бы reconnect.
        if (
            (this.mode === 'sfu' || !this.mode)
            && !this._sfuSessionFinished
            && !this._room
            && !this._connecting
            && this.livekitToken
            && this._status !== 'error'
        ) {
            this._connectSFU().catch(err => {
                this._connecting = false;
                this._sfuSessionFinished = true;
                this._error = err.message;
                this._status = 'error';
            });
        }
        if (!this._room) {
            const domTiles = this.shadowRoot.querySelectorAll('.participant-tile');
            const p = this._participants[0];
            if (p?.stream) {
                const videoEl = domTiles[0]?.querySelector('video');
                if (videoEl && videoEl.srcObject !== p.stream) {
                    videoEl.srcObject = p.stream;
                }
            }
            return;
        }

        const domTiles = this.shadowRoot.querySelectorAll('.participant-tile');
        this._tiles.forEach((tile, i) => {
            const videoEl = domTiles[i]?.querySelector('video');
            if (!videoEl) return;
            if (!tile.track) {
                if (videoEl._lkTrack) {
                    videoEl._lkTrack.detach(videoEl);
                    videoEl._lkTrack = null;
                }
                return;
            }
            if (videoEl._lkTrack && videoEl._lkTrack !== tile.track) {
                videoEl._lkTrack.detach(videoEl);
            }
            if (videoEl._lkTrack !== tile.track) {
                tile.track.attach(videoEl);
                videoEl._lkTrack = tile.track;
            }
        });

        this._room.remoteParticipants.forEach((p) => {
            const audioPub = Array.from(p.audioTrackPublications.values()).find(
                (t) => t.isSubscribed && t.track
            );
            const tr = audioPub?.track;
            if (tr && !tr._lkAttached) {
                tr.attach();
                tr._lkAttached = true;
            }
        });
    }
}

customElements.define('call-overlay', CallOverlay);
