/**
 * sync-call-overlay-modal — полноэкранный оверлей звонка с LiveKit SFU.
 *
 * Источники state:
 *   - useOp('sync/call_token')        — JWT для подключения к LiveKit
 *   - useOp('sync/call_turn')         — TURN credentials (legacy P2P, опц.)
 *   - useOp('sync/call_recordings_list') — определяет активную запись
 *   - select(s.syncCallUi)            — recordingStatus, overlayMinimized
 *   - useEvent('sync/call/signaled')  — input signaling (фильтр по target)
 *   - useEvent('sync/call/ended')     — auto-close overlay
 *
 * Действия:
 *   - hangup → useOp('sync/calls_hangup')
 *   - recording start/stop → useOp('sync/calls_recording_start'|'stop')
 *   - admin transfer → useOp('sync/calls_admin_transfer')
 *   - signal → useOp('sync/calls_signal')
 *   - minimize → dispatch('sync/call_ui/overlay_minimized')
 *   - expand   → dispatch('sync/call_ui/overlay_expanded')
 *   - close    → dispatch('sync/call_ui/overlay_closed')
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class SyncCallOverlayModal extends PlatformModal {
    static modalKind = 'sync.call_overlay';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformModal.properties,
        callId: { type: String },
        callType: { type: String },
        channelId: { type: String },
        _connecting: { state: true },
        _participants: { state: true },
        _cameraEnabled: { state: true },
        _micEnabled: { state: true },
        _screenSharing: { state: true },
    };

    static styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .stage {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                gap: var(--space-2);
                padding: var(--space-3);
                min-height: 60vh;
            }
            .tile {
                background: black;
                border-radius: var(--radius-md);
                aspect-ratio: 16 / 9;
                position: relative;
                overflow: hidden;
            }
            .tile video { width: 100%; height: 100%; object-fit: cover; }
            .tile-name {
                position: absolute;
                left: var(--space-2);
                bottom: var(--space-2);
                padding: 2px 8px;
                background: rgba(0,0,0,0.6);
                color: white;
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
            }
            .controls {
                display: flex;
                gap: var(--space-2);
                justify-content: center;
                padding: var(--space-3);
                border-top: 1px solid var(--glass-border);
            }
            .btn-end { background: var(--color-danger, #ef4444); color: white; }
            .btn-rec.recording { background: var(--color-danger, #ef4444); color: white; }
        `,
    ];

    constructor() {
        super();
        this.callId = '';
        this.callType = 'video';
        this.channelId = '';
        this._connecting = true;
        this._participants = [];
        this._cameraEnabled = true;
        this._micEnabled = true;
        this._screenSharing = false;
        this._room = null;
        this._tokenOp = this.useOp('sync/call_token');
        this._hangupOp = this.useOp('sync/calls_hangup');
        this._recordingStartOp = this.useOp('sync/calls_recording_start');
        this._recordingStopOp = this.useOp('sync/calls_recording_stop');
        this._signalOp = this.useOp('sync/calls_signal');
        this._callUiSel = this.select((s) => s.syncCallUi);
        this.useEvent('sync/call/ended', (event) => this._onCallEnded(event));
        this.useEvent('sync/call/signaled', (event) => this._onSignaled(event));
    }

    async firstUpdated() {
        await this._connectLiveKit();
    }

    disconnectedCallback() {
        this._disconnectLiveKit();
        super.disconnectedCallback();
    }

    async _connectLiveKit() {
        if (!this.callId) return;
        await this._tokenOp.run({ call_id: this.callId });
        const tokenResult = this._tokenOp.lastResult;
        if (!tokenResult || !tokenResult.token || !tokenResult.livekit_url) {
            this._connecting = false;
            return;
        }
        const livekit = await import('@livekit/client');
        const room = new livekit.Room({
            adaptiveStream: true,
            dynacast: true,
        });
        this._room = room;
        room.on(livekit.RoomEvent.ParticipantConnected, () => this._refreshParticipants());
        room.on(livekit.RoomEvent.ParticipantDisconnected, () => this._refreshParticipants());
        room.on(livekit.RoomEvent.TrackSubscribed, () => this._refreshParticipants());
        room.on(livekit.RoomEvent.TrackUnsubscribed, () => this._refreshParticipants());
        room.on(livekit.RoomEvent.Disconnected, () => this._onLiveKitDisconnected());

        await room.connect(tokenResult.livekit_url, tokenResult.token);
        await room.localParticipant.enableCameraAndMicrophone();
        this._connecting = false;
        this._refreshParticipants();
    }

    _disconnectLiveKit() {
        if (this._room) {
            try {
                this._room.disconnect();
            } catch (err) {
                this.toast('call_overlay_modal.toast_disconnect_failed', {
                    type: 'error',
                    vars: { error: String(err && err.message ? err.message : err) },
                });
            }
            this._room = null;
        }
    }

    _onLiveKitDisconnected() {
        this.dispatch('sync/call_ui/overlay_closed', null);
        this.close();
    }

    _refreshParticipants() {
        if (!this._room) return;
        const participants = [...this._room.remoteParticipants.values(), this._room.localParticipant];
        this._participants = participants.map((p) => ({
            sid: p.sid,
            identity: p.identity,
            name: (typeof p.name === 'string' && p.name !== '') ? p.name : p.identity,
            isLocal: p === this._room.localParticipant,
            videoTrack: this._extractVideoTrack(p),
        }));
    }

    _extractVideoTrack(participant) {
        const tracks = participant.videoTrackPublications;
        if (!tracks) return null;
        for (const pub of tracks.values()) {
            if (pub.track) return pub.track;
        }
        return null;
    }

    async _toggleMic() {
        if (!this._room) return;
        this._micEnabled = !this._micEnabled;
        await this._room.localParticipant.setMicrophoneEnabled(this._micEnabled);
    }

    async _toggleCamera() {
        if (!this._room) return;
        this._cameraEnabled = !this._cameraEnabled;
        await this._room.localParticipant.setCameraEnabled(this._cameraEnabled);
    }

    async _toggleScreenShare() {
        if (!this._room) return;
        this._screenSharing = !this._screenSharing;
        await this._room.localParticipant.setScreenShareEnabled(this._screenSharing);
        this._refreshParticipants();
    }

    _onMinimize() {
        this.dispatch('sync/call_ui/overlay_minimized', null);
        this.close();
    }

    async _onHangup() {
        if (!this.callId) return;
        await this._hangupOp.run({ call_id: this.callId });
        this._disconnectLiveKit();
        this.dispatch('sync/call_ui/overlay_closed', null);
        this.close();
    }

    _onCallEnded(event) {
        const p = event && event.payload;
        if (!p || p.call_id !== this.callId) return;
        this._disconnectLiveKit();
        this.dispatch('sync/call_ui/overlay_closed', null);
        this.close();
    }

    async _onSignaled(event) {
        const p = event && event.payload;
        if (!p || p.call_id !== this.callId) return;
        // P2P-фрейм. В SFU-режиме (по умолчанию для всех звонков сейчас) это no-op.
    }

    _resolveRecordingStatus() {
        const state = this._callUiSel.value;
        if (state && typeof state.recordingStatus === 'string' && state.recordingStatus !== '') {
            return state.recordingStatus;
        }
        return 'idle';
    }

    async _toggleRecording() {
        if (!this.callId) return;
        const status = this._resolveRecordingStatus();
        if (status === 'recording') {
            await this._recordingStopOp.run({ call_id: this.callId });
        } else if (status === 'idle') {
            await this._recordingStartOp.run({ call_id: this.callId });
        }
    }

    _renderTile(participant) {
        return html`
            <div class="tile" data-sid=${participant.sid}>
                ${participant.videoTrack ? html`
                    <video
                        autoplay
                        playsinline
                        muted=${participant.isLocal}
                        .srcObject=${participant.videoTrack.mediaStream}
                    ></video>
                ` : html`<div style="display:flex;align-items:center;justify-content:center;height:100%;color:rgba(255,255,255,0.5);"><platform-icon name="user" size="48"></platform-icon></div>`}
                <span class="tile-name">${participant.name}${participant.isLocal ? ` (${this.t('call_overlay.you')})` : ''}</span>
            </div>
        `;
    }

    renderHeader() {
        return html`
            <h3 style="display: flex; align-items: center; gap: var(--space-2);">
                ${this.t('call_overlay.title')}
                <span style="margin-left: auto; display: flex; gap: var(--space-1);">
                    <platform-button variant="ghost" @click=${this._onMinimize} title=${this.t('call_overlay.action_minimize')}>
                        <platform-icon name="minus" size="16"></platform-icon>
                    </platform-button>
                </span>
            </h3>
        `;
    }

    renderBody() {
        const recordingStatus = this._resolveRecordingStatus();
        return html`
            ${this._connecting ? html`<div style="padding: var(--space-4); text-align: center;">${this.t('call_overlay.connecting')}</div>` : ''}
            <div class="stage">
                ${this._participants.map((p) => this._renderTile(p))}
            </div>
            <div class="controls">
                <platform-button @click=${this._toggleMic} title=${this.t('call_overlay.action_mic')}>
                    <platform-icon name=${this._micEnabled ? 'mic' : 'mic-off'} size="18"></platform-icon>
                </platform-button>
                <platform-button @click=${this._toggleCamera} title=${this.t('call_overlay.action_camera')}>
                    <platform-icon name=${this._cameraEnabled ? 'video' : 'video-off'} size="18"></platform-icon>
                </platform-button>
                <platform-button @click=${this._toggleScreenShare} title=${this.t('call_overlay.action_screen')}>
                    <platform-icon name="monitor" size="18"></platform-icon>
                </platform-button>
                <platform-button class=${recordingStatus === 'recording' ? 'btn-rec recording' : 'btn-rec'}
                                 @click=${this._toggleRecording}
                                 title=${this.t('call_overlay.action_record')}>
                    <platform-icon name="circle" size="18"></platform-icon>
                </platform-button>
                <platform-button class="btn-end" @click=${this._onHangup}>
                    ${this.t('call_overlay.action_end')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('sync-call-overlay-modal', SyncCallOverlayModal);
registerModalKind(SyncCallOverlayModal.modalKind, 'sync-call-overlay-modal');
