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
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';

const LS_CAMERA_KEY = 'humanitec.sync.call.camera_enabled';
const LS_AUDIO_NS_KEY = 'humanitec.sync.call.audio_noise_suppression';
const LS_AUDIO_EC_KEY = 'humanitec.sync.call.audio_echo_cancellation';
const LS_AUDIO_AGC_KEY = 'humanitec.sync.call.audio_auto_gain';

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

function _readBoolLs(key, defaultValue) {
    try {
        const v = localStorage.getItem(key);
        if (v === null) return defaultValue;
        return v === 'true';
    } catch {
        return defaultValue;
    }
}

function _writeBoolLs(key, value) {
    try {
        localStorage.setItem(key, String(value));
    } catch {
        /* ignore */
    }
}

function _readAudioCapturePrefs() {
    return {
        noiseSuppression: _readBoolLs(LS_AUDIO_NS_KEY, true),
        echoCancellation: _readBoolLs(LS_AUDIO_EC_KEY, true),
        autoGainControl: _readBoolLs(LS_AUDIO_AGC_KEY, true),
    };
}

function _hasStoredAudioPrefs() {
    try {
        return (
            localStorage.getItem(LS_AUDIO_NS_KEY) !== null
            || localStorage.getItem(LS_AUDIO_EC_KEY) !== null
            || localStorage.getItem(LS_AUDIO_AGC_KEY) !== null
        );
    } catch {
        return false;
    }
}

class CallOverlay extends PlatformElement {
    static properties = {
        callId:      { type: String, attribute: 'call-id' },
        channelId:   { type: String, attribute: 'channel-id' },
        mode:        { type: String },
        callType:    { type: String, attribute: 'call-type' },
        currentUserId: { type: String, attribute: 'current-user-id' },
        meetingAdminUserId: { type: String, attribute: 'meeting-admin-user-id' },
        recordingStartedByUserId: { type: String, attribute: 'recording-started-by-user-id' },
        livekitUrl:  { type: String, attribute: 'livekit-url' },
        livekitToken: { type: String, attribute: 'livekit-token' },
        identity:    { type: String },
        names:       { type: Object },
        minimized:   { type: Boolean, reflect: true },
        _status:      { state: true },
        _error:       { state: true },
        _participants: { state: true },
        _duration:    { state: true },
        _micMuted:    { state: true },
        _camOff:      { state: true },
        _tiles:       { state: true },
        _fullscreenTileKey: { state: true },
        _devicesMenuOpen: { state: true },
        _moreMenuOpen: { state: true },
        _audioQualitySubOpen: { state: true },
        _deviceLists: { state: true },
        _audioOutputSupported: { state: true },
        _audioPrefs: { state: true },
        _mediaSettingsError: { state: true },
        /** Краткая галочка после успешного копирования ссылки (2 с), без правки innerHTML — переживает requestUpdate. */
        _copyLinkFeedback: { state: true },
        _recordingStatus: { state: true },
        _recordingError: { state: true },
        _participantMenuIdentity: { state: true },
        _chatPanelOpen: { state: true },
        _chatInput: { state: true },
        _chatSending: { state: true },
        _chatError: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
        :host {
            position: fixed;
            inset: 0;
            z-index: var(--platform-modal-layer-z, var(--z-max, 9999));
            background: #0a0a0f;
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
            padding-top: env(safe-area-inset-top, 0px);
            padding-right: env(safe-area-inset-right, 0px);
            padding-bottom: env(safe-area-inset-bottom, 0px);
            padding-left: env(safe-area-inset-left, 0px);
            pointer-events: auto;
            touch-action: manipulation;
        }

        /*
         * pointer-events на :host не отключает hit-target у потомков в shadow (video, кнопки).
         * Без * { pointer-events: none } свёрнутый оверлей перекрывает весь экран невидимой сеткой.
         */
        :host([minimized]:not([data-overlay-critical])) {
            position: fixed !important;
            left: -9999px !important;
            top: 0 !important;
            width: 4px !important;
            height: 4px !important;
            max-width: 4px !important;
            max-height: 4px !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            padding: 0 !important;
            clip-path: inset(50%) !important;
        }

        :host([minimized]:not([data-overlay-critical])) * {
            pointer-events: none !important;
        }

        .video-grid {
            position: relative;
            z-index: 0;
            flex: 1;
            min-height: 0;
            display: grid;
            align-content: start;
            justify-items: stretch;
            align-items: start;
            padding: 16px;
            gap: 12px;
            overflow-x: hidden;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        }

        .video-grid.one   { grid-template-columns: 1fr; }
        .video-grid.two   { grid-template-columns: 1fr 1fr; }
        .video-grid.many  { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }

        .call-stage {
            flex: 1;
            min-height: 0;
            display: flex;
            position: relative;
        }

        .call-chat-panel {
            position: absolute;
            top: 16px;
            right: 16px;
            bottom: 16px;
            width: min(360px, calc(100vw - 32px));
            border-radius: var(--radius-xl);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-solid-medium);
            backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.3);
            -webkit-backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.3);
            box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-subtle);
            display: flex;
            flex-direction: column;
            min-height: 0;
            z-index: 130;
            animation: call-menu-in var(--duration-fast) var(--easing-smooth) both;
        }

        .call-chat-panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 12px 12px 10px;
            border-bottom: 1px solid var(--glass-border-medium);
            font-size: var(--text-sm);
            font-weight: var(--font-medium);
            color: var(--text-primary);
        }

        .call-chat-panel-title {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .call-chat-panel-close {
            width: 30px;
            height: 30px;
            border-radius: var(--radius-full);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-tint-medium);
            color: var(--text-primary);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background var(--duration-fast) var(--easing-default);
        }

        .call-chat-panel-close:hover {
            background: var(--glass-tint-strong);
        }

        .call-chat-list {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .call-chat-item {
            border-radius: var(--radius-md);
            padding: 8px 10px;
            background: var(--glass-tint-medium);
            border: 1px solid var(--glass-border-subtle);
        }

        .call-chat-row {
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }

        .call-chat-avatar {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            color: rgba(255,255,255,0.96);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
            margin-top: 1px;
        }

        .call-chat-content {
            min-width: 0;
            flex: 1;
        }

        .call-chat-item.self {
            background: color-mix(in srgb, var(--accent) 24%, transparent);
            border-color: color-mix(in srgb, var(--accent) 42%, transparent);
        }

        .call-chat-item.failed {
            border-color: rgba(239,68,68,0.45);
        }

        .call-chat-meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 4px;
            font-size: 11px;
            color: rgba(255,255,255,0.58);
        }

        .call-chat-author {
            max-width: 160px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .call-chat-text {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            color: rgba(255,255,255,0.92);
            font-size: 13px;
            line-height: 1.35;
        }

        .call-chat-state {
            padding: 10px;
            font-size: var(--text-xs);
            color: var(--text-secondary);
        }

        .call-chat-composer {
            border-top: 1px solid var(--glass-border-medium);
            padding: 10px 12px 12px;
            display: flex;
            gap: 8px;
            align-items: flex-end;
        }

        .call-chat-input {
            flex: 1;
            min-height: 36px;
            max-height: 120px;
            resize: vertical;
            border-radius: var(--radius-md);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-tint-subtle);
            color: var(--text-primary);
            padding: 8px 10px;
            font-size: var(--text-sm);
            line-height: 1.3;
            outline: none;
        }

        .call-chat-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px var(--accent-subtle);
        }

        .call-chat-send {
            height: 36px;
            border-radius: var(--radius-md);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-tint-medium);
            color: var(--text-primary);
            padding: 0 12px;
            font-size: var(--text-xs);
            cursor: pointer;
            transition: background var(--duration-fast) var(--easing-default);
        }

        .call-chat-send:hover:not(:disabled) {
            background: var(--glass-tint-strong);
        }

        .call-chat-send:disabled {
            opacity: 0.5;
            cursor: default;
        }

        .call-chat-error {
            border-top: 1px solid rgba(239,68,68,0.45);
            color: rgba(254,202,202,0.95);
            font-size: 12px;
            padding: 8px 12px;
            background: rgba(127,29,29,0.32);
        }

        @media (max-width: 640px) {
            .call-chat-panel {
                top: auto;
                right: 8px;
                left: 8px;
                bottom: 10px;
                width: auto;
                max-height: min(60vh, 430px);
            }

            .video-grid {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                justify-content: flex-start;
                gap: 12px;
                padding: 12px;
            }
            .video-grid.two {
                grid-template-columns: unset;
                flex-direction: column;
            }
        }

        .participant-tile {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            overflow: hidden;
            width: 100%;
            max-width: 100%;
            flex-shrink: 0;
            aspect-ratio: 16 / 9;
            position: relative;
            z-index: 0;
            isolation: isolate;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /*
         * iOS WebKit: слой декодированного видео часто перехватывает hit-testing поверх z-index.
         * pointer-events: none на <video> оставляет клики оверлею; кнопки/подписи — pointer-events: auto.
         */
        .participant-tile video {
            width: 100%;
            height: 100%;
            object-fit: cover;
            pointer-events: none;
        }

        .participant-tile .participant-name,
        .participant-tile .tile-fs-btn {
            pointer-events: auto;
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
            pointer-events: auto;
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
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0,0,0,0.55);
            color: #fff;
            z-index: 50;
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
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: #fff;
            background: rgba(0,0,0,0.5);
            padding: 3px 10px;
            border-radius: 100px;
        }

        .participant-admin-crown {
            display: inline-flex;
            color: #fbbf24;
        }

        .tile-action-btn {
            position: absolute;
            top: 8px;
            left: 8px;
            width: 34px;
            height: 34px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0,0,0,0.55);
            color: #fff;
            z-index: 51;
            transition: background 0.15s;
            pointer-events: auto;
        }

        .tile-action-btn:hover {
            background: rgba(0,0,0,0.75);
        }

        .tile-action-menu {
            position: absolute;
            top: 46px;
            left: 8px;
            min-width: 220px;
            padding: 8px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            background: rgba(20, 20, 26, 0.95);
            backdrop-filter: blur(12px);
            z-index: 60;
            pointer-events: auto;
        }

        .tile-action-menu-item {
            width: 100%;
            border: none;
            border-radius: 10px;
            padding: 8px 10px;
            background: transparent;
            color: #fff;
            text-align: left;
            cursor: pointer;
            font-size: 13px;
        }

        .tile-action-menu-item:hover {
            background: rgba(255, 255, 255, 0.12);
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

        .controls-bar {
            flex-shrink: 0;
            position: relative;
            z-index: 100;
            transform: translateZ(0);
            isolation: isolate;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 20px 24px;
            background: rgba(0,0,0,0.4);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            touch-action: manipulation;
        }

        .controls-slot {
            display: flex;
            align-items: center;
            min-height: 52px;
        }

        .controls-slot--left {
            flex: 0 0 auto;
            justify-content: flex-start;
            position: relative;
        }

        .controls-slot--center {
            flex: 1 1 auto;
            justify-content: center;
            gap: 16px;
        }

        .controls-slot--right {
            flex: 0 0 auto;
            justify-content: flex-end;
            position: relative;
            gap: 8px;
        }

        .call-menu {
            position: absolute;
            bottom: calc(100% + 12px);
            min-width: 240px;
            max-width: min(340px, 92vw);
            padding: var(--space-3) 0;
            font-family: var(--font-sans);
            font-size: var(--text-sm);
            line-height: var(--leading-normal);
            color: var(--text-primary);
            background: var(--glass-solid-medium);
            backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.35);
            -webkit-backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.35);
            border: 1px solid var(--glass-border-medium);
            border-radius: var(--radius-xl);
            box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-subtle);
            z-index: 10010;
            pointer-events: auto;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
            animation: call-menu-in var(--duration-fast) var(--easing-smooth) both;
        }

        @keyframes call-menu-in {
            from {
                opacity: 0;
                transform: translateY(6px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .call-menu--left {
            left: 0;
        }

        .call-menu--right {
            right: 0;
        }

        .call-menu label {
            display: block;
            padding: var(--space-2) var(--space-4) var(--space-1);
            font-size: var(--text-xs);
            font-weight: var(--font-semibold);
            letter-spacing: var(--tracking-wide);
            text-transform: uppercase;
            color: var(--text-tertiary);
        }

        .call-menu select {
            display: block;
            width: calc(100% - 2 * var(--space-4));
            margin: 0 var(--space-4) var(--space-3);
            padding: var(--space-2) var(--space-8) var(--space-2) var(--space-3);
            appearance: none;
            -webkit-appearance: none;
            border-radius: var(--radius-md);
            border: 1px solid var(--glass-border-medium);
            background: var(--glass-tint-medium);
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.45)' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 10px center;
            color: var(--text-primary);
            font-family: inherit;
            font-size: var(--text-sm);
            cursor: pointer;
            transition: border-color var(--duration-fast) var(--easing-default),
                background var(--duration-fast) var(--easing-default),
                box-shadow var(--duration-fast) var(--easing-default);
        }

        .call-menu select:hover:not(:disabled) {
            border-color: var(--glass-border-strong);
            background: var(--glass-tint-strong);
        }

        .call-menu select:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-subtle);
        }

        .call-menu select:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }

        .call-menu-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-3);
            margin: 0 var(--space-2);
            padding: var(--space-3) var(--space-3);
            cursor: pointer;
            border: none;
            width: calc(100% - 2 * var(--space-2));
            border-radius: var(--radius-md);
            background: transparent;
            color: var(--text-primary);
            font: inherit;
            font-weight: var(--font-medium);
            text-align: left;
            transition: background var(--duration-fast) var(--easing-default);
        }

        .call-menu-item:hover {
            background: var(--glass-tint-medium);
        }

        .call-menu-item:focus-visible {
            outline: none;
            box-shadow: 0 0 0 2px var(--accent-subtle);
        }

        .call-menu-item--sub {
            position: relative;
            display: block;
            padding: 0;
        }

        .call-menu-item--sub > button.call-menu-item {
            width: calc(100% - 2 * var(--space-2));
        }

        .call-menu-chevron {
            flex-shrink: 0;
            opacity: 0.45;
        }

        .call-menu-flyout {
            position: absolute;
            right: calc(100% + 8px);
            left: auto;
            top: 0;
            bottom: auto;
            min-width: 260px;
            padding: var(--space-2) 0;
            font-family: var(--font-sans);
            background: var(--glass-solid-medium);
            backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.35);
            -webkit-backdrop-filter: blur(var(--glass-blur-medium)) saturate(1.35);
            border: 1px solid var(--glass-border-medium);
            border-radius: var(--radius-xl);
            box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-subtle);
            z-index: 10011;
            pointer-events: auto;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
            animation: call-menu-in var(--duration-fast) var(--easing-smooth) both;
        }

        @media (max-width: 640px) {
            .call-menu-item--sub {
                display: flex;
                flex-direction: column;
                align-items: stretch;
            }
            .call-menu-flyout {
                position: relative;
                right: auto;
                left: auto;
                top: auto;
                bottom: auto;
                transform: none;
                width: 100%;
                min-width: 0;
                margin-top: var(--space-2);
                max-height: min(50vh, 360px);
                overflow-y: auto;
            }
        }

        .call-menu-toggle {
            display: grid;
            grid-template-columns: 1fr auto;
            align-items: center;
            column-gap: var(--space-4);
            margin: 2px var(--space-2);
            padding: var(--space-3) var(--space-3);
            border-radius: var(--radius-md);
            cursor: pointer;
            font-size: var(--text-sm);
            font-weight: var(--font-medium);
            color: var(--text-primary);
            transition: background var(--duration-fast) var(--easing-default);
            min-height: 44px;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }

        .call-menu-toggle:hover {
            background: var(--glass-tint-medium);
        }

        .call-menu-toggle-label {
            line-height: var(--leading-tight);
            min-width: 0;
        }

        .call-switch-input {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }

        .call-switch-visual {
            position: relative;
            flex-shrink: 0;
            width: 46px;
            height: 28px;
            border-radius: var(--radius-full);
            background: rgba(255, 255, 255, 0.14);
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.2);
            transition: background var(--duration-fast) var(--easing-default);
            justify-self: end;
            align-self: center;
        }

        .call-switch-visual::after {
            content: '';
            position: absolute;
            top: 3px;
            left: 4px;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #fff;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
            transition: transform var(--duration-fast) var(--easing-default);
        }

        .call-menu-toggle:has(.call-switch-input:checked) .call-switch-visual {
            background: var(--accent);
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.15), var(--accent-glow);
        }

        .call-menu-toggle:has(.call-switch-input:checked) .call-switch-visual::after {
            transform: translateX(16px);
        }

        .call-menu-toggle:has(.call-switch-input:focus-visible) .call-switch-visual {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }

        .ctrl-btn[disabled] {
            opacity: 0.35;
            cursor: not-allowed;
        }

        .ctrl-btn[disabled]:hover {
            background: rgba(255,255,255,0.12);
        }

        .settings-error {
            padding: 8px 24px 0;
            color: #f87171;
            font-size: 13px;
            text-align: center;
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
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
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
            flex-shrink: 0;
            position: relative;
            z-index: 100;
            transform: translateZ(0);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px 8px;
            color: rgba(255,255,255,0.6);
            font-size: 13px;
        }

        .header .ctrl-btn {
            pointer-events: auto;
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

        .recording-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #ef4444;
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .recording-badge-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #ef4444;
            box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8);
            animation: recording-dot-pulse 1.2s ease-in-out infinite;
        }

        @keyframes recording-dot-pulse {
            0% {
                opacity: 1;
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8);
            }
            70% {
                opacity: 0.45;
                box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
            }
            100% {
                opacity: 1;
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
            }
        }

        .ctrl-btn.recording-btn {
            width: 56px;
            height: 56px;
        }

        .ctrl-btn.recording-btn.recording-btn--active {
            width: 64px;
            height: 64px;
            background: #ef4444;
            color: #fff;
            box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.35);
        }

        .ctrl-btn.recording-btn.recording-btn--active:hover {
            background: #dc2626;
        }

        .ctrl-btn.chat-toggle-btn.chat-toggle-btn--active {
            background: var(--accent);
            color: #fff;
            box-shadow: var(--accent-glow);
        }
    `,
    ];

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
        this._devicesMenuOpen = false;
        this._moreMenuOpen = false;
        this._audioQualitySubOpen = false;
        this._deviceLists = { audioinput: [], videoinput: [], audiooutput: [] };
        this._audioOutputSupported = typeof HTMLMediaElement !== 'undefined'
            && 'setSinkId' in HTMLMediaElement.prototype;
        this._audioPrefs = _readAudioCapturePrefs();
        this._onCallSignalHandler = (e) => this._onCallSignal(e);
        this._onDocumentPointerDown = this._onDocumentPointerDown.bind(this);
        this._onDocumentKeydown = this._onDocumentKeydown.bind(this);
        this._mediaSettingsError = null;
        this._cameraEnabledBeforeScreenShare = true;
        this._cameraSuspendedForScreenShare = false;
        this._copyLinkFeedback = false;
        this._recordingStatus = 'idle';
        this._recordingError = null;
        this._participantMenuIdentity = null;
        this._chatPanelOpen = false;
        this._chatInput = '';
        this._chatSending = false;
        this._chatError = null;
        this._storeUnsubscribe = null;
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._copyLinkFeedbackTimerId = null;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    _tp(key, params) {
        return this.i18n.t(key, params ?? {});
    }

    _sfuMediaUiAvailable() {
        return Boolean(this._room && this._status === 'active');
    }

    _closeMenus() {
        this._devicesMenuOpen = false;
        this._moreMenuOpen = false;
        this._audioQualitySubOpen = false;
        this._participantMenuIdentity = null;
    }

    _pointerClientXY(e) {
        if (e.clientX != null && e.clientY != null) {
            return { x: e.clientX, y: e.clientY };
        }
        const t = e.touches?.[0] ?? e.changedTouches?.[0];
        if (t) return { x: t.clientX, y: t.clientY };
        return { x: 0, y: 0 };
    }

    /**
     * Закрывать меню только при касании вне панелей и вне кнопок-открывалок (шестерёнка / ⋯).
     * Весь оверлей (видео) считается «снаружи» меню — иначе меню никогда не закрыть тапом по сетке.
     */
    _pointerTargetsMenuChrome(e) {
        const testEl = (el) => {
            if (!(el instanceof Element)) return false;
            if (el.closest?.('.call-menu') || el.closest?.('.call-menu-flyout') || el.closest?.('.tile-action-menu')) return true;
            if (el.closest?.('.controls-bar') || el.closest?.('.header') || el.closest?.('.settings-error')) {
                return true;
            }
            return false;
        };
        const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
        if (path.some((n) => testEl(n))) return true;
        const { x, y } = this._pointerClientXY(e);
        if (x === 0 && y === 0 && !e.touches?.length && !e.changedTouches?.length) return false;
        const hit = document.elementFromPoint(x, y);
        return testEl(hit);
    }

    _onDocumentPointerDown(e) {
        if (!this._devicesMenuOpen && !this._moreMenuOpen && this._participantMenuIdentity == null) return;
        if (this._pointerTargetsMenuChrome(e)) return;
        this._closeMenus();
    }

    _onDocumentKeydown(e) {
        if (e.key !== 'Escape') return;
        if (this._devicesMenuOpen || this._moreMenuOpen || this._participantMenuIdentity != null) {
            this._closeMenus();
            e.preventDefault();
            return;
        }
        if (this._chatPanelOpen) {
            this._chatPanelOpen = false;
            e.preventDefault();
            return;
        }
        const fs = this._getFullscreenElement();
        if (fs && this.shadowRoot?.contains(fs)) {
            this._exitTileFullscreenIfOurs();
            e.preventDefault();
        }
    }

    async _toggleDevicesMenu(e) {
        e.stopPropagation();
        if (!this._sfuMediaUiAvailable()) return;
        const next = !this._devicesMenuOpen;
        this._moreMenuOpen = false;
        this._audioQualitySubOpen = false;
        this._devicesMenuOpen = next;
        this._mediaSettingsError = null;
        if (this._devicesMenuOpen) {
            await this._refreshDeviceLists();
        }
    }

    _toggleMoreMenu(e) {
        e.stopPropagation();
        if (!this._sfuMediaUiAvailable()) return;
        const next = !this._moreMenuOpen;
        this._devicesMenuOpen = false;
        this._audioQualitySubOpen = false;
        this._moreMenuOpen = next;
        this._mediaSettingsError = null;
    }

    _toggleAudioQualitySub(e) {
        e.stopPropagation();
        this._audioQualitySubOpen = !this._audioQualitySubOpen;
    }

    _isGuestIdentity(identity) {
        return typeof identity === 'string' && identity.startsWith('guest:');
    }

    _isMeetingAdminUser(identity) {
        const candidateIdentity = this._normalizedIdentity(identity);
        const meetingAdminIdentity = this._normalizedIdentity(this.meetingAdminUserId);
        return candidateIdentity !== '' && candidateIdentity === meetingAdminIdentity;
    }

    _normalizedIdentity(value) {
        if (typeof value !== 'string') return '';
        const trimmed = value.trim();
        return trimmed === '' ? '' : trimmed;
    }

    _currentIdentityCandidates() {
        const candidates = new Set();
        const currentUserIdentity = this._normalizedIdentity(this.currentUserId);
        if (currentUserIdentity !== '') {
            candidates.add(currentUserIdentity);
        }
        const providedIdentity = this._normalizedIdentity(this.identity);
        if (providedIdentity !== '') {
            candidates.add(providedIdentity);
        }
        const localParticipantIdentity = this._normalizedIdentity(this._room?.localParticipant?.identity);
        if (localParticipantIdentity !== '') {
            candidates.add(localParticipantIdentity);
        }
        return candidates;
    }

    _canTransferMeetingAdmin() {
        const meetingAdminIdentity = this._normalizedIdentity(this.meetingAdminUserId);
        if (meetingAdminIdentity === '') return false;
        return Array.from(this._currentIdentityCandidates()).some(
            (identity) => identity === meetingAdminIdentity
        );
    }

    _canStopRecording() {
        if (this._canTransferMeetingAdmin()) return true;
        const startedByIdentity = this._normalizedIdentity(this.recordingStartedByUserId);
        if (startedByIdentity === '') return false;
        return Array.from(this._currentIdentityCandidates()).some(
            (identity) => identity === startedByIdentity
        );
    }

    _toggleParticipantMenu(e, identity) {
        e.stopPropagation();
        if (!this._canTransferMeetingAdmin()) return;
        if (this._participantMenuIdentity === identity) {
            this._participantMenuIdentity = null;
            return;
        }
        this._participantMenuIdentity = identity;
    }

    _assignMeetingAdmin(e, identity) {
        e.stopPropagation();
        if (!this._canTransferMeetingAdmin()) return;
        if (typeof identity !== 'string' || identity === '') return;
        if (this._isGuestIdentity(identity)) return;
        if (this._isMeetingAdminUser(identity)) return;
        this._participantMenuIdentity = null;
        this.dispatchEvent(new CustomEvent('call-transfer-admin', {
            detail: { callId: this.callId, targetUserId: identity },
            bubbles: true,
            composed: true,
        }));
    }

    async _refreshDeviceLists() {
        if (!navigator.mediaDevices?.enumerateDevices) {
            this._deviceLists = { audioinput: [], videoinput: [], audiooutput: [] };
            return;
        }
        const all = await navigator.mediaDevices.enumerateDevices();
        const audioinput = all.filter((d) => d.kind === 'audioinput');
        const videoinput = all.filter((d) => d.kind === 'videoinput');
        const audiooutput = all.filter((d) => d.kind === 'audiooutput');
        this._deviceLists = { audioinput, videoinput, audiooutput };
    }

    async _applySavedAudioCaptureOptions() {
        if (!this._room || !this._lk) return;
        const { Track } = this._lk;
        const pub = this._room.localParticipant.getTrackPublication(Track.Source.Microphone);
        const localTrack = pub?.track;
        if (!localTrack || typeof localTrack.restartTrack !== 'function') return;
        const prefs = _readAudioCapturePrefs();
        this._audioPrefs = { ...prefs };
        await localTrack.restartTrack({
            noiseSuppression: prefs.noiseSuppression,
            echoCancellation: prefs.echoCancellation,
            autoGainControl: prefs.autoGainControl,
        });
    }

    async _setAudioPref(key, value) {
        if (key === 'noiseSuppression') {
            _writeBoolLs(LS_AUDIO_NS_KEY, value);
        } else if (key === 'echoCancellation') {
            _writeBoolLs(LS_AUDIO_EC_KEY, value);
        } else if (key === 'autoGainControl') {
            _writeBoolLs(LS_AUDIO_AGC_KEY, value);
        }
        const next = _readAudioCapturePrefs();
        this._audioPrefs = { ...next };
        try {
            await this._applySavedAudioCaptureOptions();
            this._mediaSettingsError = null;
        } catch (err) {
            this._mediaSettingsError = err instanceof Error ? err.message : String(err);
        }
    }

    async _onAudioInputChange(e) {
        const deviceId = e.target.value;
        if (!this._room || !deviceId) return;
        try {
            await this._room.switchActiveDevice('audioinput', deviceId);
            this._mediaSettingsError = null;
        } catch (err) {
            this._mediaSettingsError = err instanceof Error ? err.message : String(err);
        }
    }

    async _onVideoInputChange(e) {
        const deviceId = e.target.value;
        if (!this._room || !deviceId) return;
        try {
            await this._room.switchActiveDevice('videoinput', deviceId);
            this._mediaSettingsError = null;
        } catch (err) {
            this._mediaSettingsError = err instanceof Error ? err.message : String(err);
        }
    }

    async _onAudioOutputChange(e) {
        const deviceId = e.target.value;
        if (!this._room || !deviceId || !this._audioOutputSupported) return;
        try {
            await this._room.switchActiveDevice('audiooutput', deviceId);
            this._mediaSettingsError = null;
        } catch (err) {
            this._mediaSettingsError = err instanceof Error ? err.message : String(err);
        }
    }

    _getFullscreenElement() {
        const d = document;
        return d.fullscreenElement
            ?? d.webkitFullscreenElement
            ?? d.mozFullScreenElement
            ?? d.msFullscreenElement
            ?? null;
    }

    _onFullscreenChange() {
        const el = this._getFullscreenElement();
        if (!el) {
            this._fullscreenTileKey = null;
        } else if (!this.shadowRoot?.contains(el)) {
            this._fullscreenTileKey = null;
        } else {
            let key = el.getAttribute?.('data-tile-key');
            if (!key && typeof el.closest === 'function') {
                const tile = el.closest('.participant-tile');
                key = tile?.getAttribute('data-tile-key') ?? null;
            }
            this._fullscreenTileKey = key;
        }
        this.requestUpdate();
    }

    _exitTileFullscreenIfOurs() {
        const el = this._getFullscreenElement();
        if (el && this.shadowRoot?.contains(el)) {
            const d = document;
            if (d.exitFullscreen) {
                d.exitFullscreen();
            } else if (d.webkitExitFullscreen) {
                d.webkitExitFullscreen();
            } else if (d.mozCancelFullScreen) {
                d.mozCancelFullScreen();
            } else if (d.msExitFullscreen) {
                d.msExitFullscreen();
            }
        }
    }

    _isIosLikeTouchSafari() {
        if (typeof navigator === 'undefined') return false;
        if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) return true;
        return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    }

    _onTileFullscreenClick(e) {
        e.stopPropagation();
        const tile = e.currentTarget.closest('.participant-tile');
        const video = tile?.querySelector('video');
        if (!tile || !video) return;
        const tileKey = tile.getAttribute('data-tile-key');
        const doc = document;
        const current = this._getFullscreenElement();
        if (current && (current === tile || tile.contains(current))) {
            if (doc.exitFullscreen) doc.exitFullscreen();
            else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
            else if (doc.mozCancelFullScreen) doc.mozCancelFullScreen();
            else if (doc.msExitFullscreen) doc.msExitFullscreen();
            return;
        }
        const preferVideoNativeFs =
            typeof video.webkitEnterFullscreen === 'function'
            && (
                doc.fullscreenEnabled === false
                || doc.fullscreenEnabled === undefined
                || this._isIosLikeTouchSafari()
            );
        if (preferVideoNativeFs) {
            if (!video._callOverlayWebkitFsEnd) {
                video._callOverlayWebkitFsEnd = () => {
                    this._fullscreenTileKey = null;
                    this.requestUpdate();
                };
                video.addEventListener('webkitendfullscreen', video._callOverlayWebkitFsEnd);
            }
            video.webkitEnterFullscreen();
            this._fullscreenTileKey = tileKey;
            this.requestUpdate();
            return;
        }
        const req = tile.requestFullscreen?.bind(tile);
        if (req) {
            const p = req();
            if (p && typeof p.catch === 'function') {
                p.catch(() => {
                    if (typeof video.webkitEnterFullscreen === 'function') {
                        video.webkitEnterFullscreen();
                        this._fullscreenTileKey = tileKey;
                        this.requestUpdate();
                    }
                });
            }
            return;
        }
        if (typeof video.webkitEnterFullscreen === 'function') {
            video.webkitEnterFullscreen();
            this._fullscreenTileKey = tileKey;
            this.requestUpdate();
            return;
        }
        if (tile.webkitRequestFullscreen) {
            tile.webkitRequestFullscreen();
        } else if (tile.mozRequestFullScreen) {
            tile.mozRequestFullScreen();
        } else if (tile.msRequestFullscreen) {
            tile.msRequestFullscreen();
        }
    }

    _tileFullscreenButton(tileKey, hasVideo) {
        if (!hasVideo) return html``;
        const active = this._fullscreenTileKey === tileKey;
        return html`
            <button
                type="button"
                class="tile-fs-btn ${active ? 'active' : ''}"
                title=${active ? this._tp('call_overlay.fullscreen_exit') : this._tp('call_overlay.fullscreen_enter')}
                @click=${this._onTileFullscreenClick}
            >
                ${active
                    ? html`<platform-icon name="minimize" size="18" aria-hidden="true"></platform-icon>`
                    : html`<platform-icon name="fullscreen" size="18" aria-hidden="true"></platform-icon>`
                }
            </button>
        `;
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this.style.setProperty(
            '--platform-modal-layer-z',
            String(nextModalLayerZIndex()),
        );
        document.addEventListener('fullscreenchange', this._onFullscreenChange);
        document.addEventListener('webkitfullscreenchange', this._onFullscreenChange);
        document.addEventListener('mozfullscreenchange', this._onFullscreenChange);
        document.addEventListener('MSFullscreenChange', this._onFullscreenChange);
        document.addEventListener('pointerdown', this._onDocumentPointerDown, false);
        document.addEventListener('touchstart', this._onDocumentPointerDown, false);
        document.addEventListener('keydown', this._onDocumentKeydown, true);
        this._durationInterval = setInterval(() => this._duration++, 1000);
        this._storeUnsubscribe = SyncStore.subscribe(() => {
            this.requestUpdate();
        });
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
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        document.removeEventListener('fullscreenchange', this._onFullscreenChange);
        document.removeEventListener('webkitfullscreenchange', this._onFullscreenChange);
        document.removeEventListener('mozfullscreenchange', this._onFullscreenChange);
        document.removeEventListener('MSFullscreenChange', this._onFullscreenChange);
        document.removeEventListener('pointerdown', this._onDocumentPointerDown, false);
        document.removeEventListener('touchstart', this._onDocumentPointerDown, false);
        document.removeEventListener('keydown', this._onDocumentKeydown, true);
        this._sfuSessionFinished = true;
        clearInterval(this._durationInterval);
        this._storeUnsubscribe?.();
        this._storeUnsubscribe = null;
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

    /**
     * При активном screen share одна видеотрансляция: только плитка экрана (локально и у remote).
     */
    _videoPubsForGrid(participant) {
        const pubs = this._orderedVideoPubs(participant, participant.isLocal);
        const Track = this._lk.Track;
        const hasScreen = pubs.some((p) => p.source === Track.Source.ScreenShare);
        if (hasScreen) {
            return pubs.filter((p) => p.source === Track.Source.ScreenShare);
        }
        return pubs;
    }

    async _connectSFU() {
        if (!this.livekitToken || !this.livekitUrl) {
            throw new Error(this._tp('call_overlay.err_livekit_required'));
        }
        // Предотвращаем двойной вызов (race condition в updated())
        if (this._connecting) return;
        this._connecting = true;

        this._lk = await import('@livekit/client');
        const { Room, RoomEvent, ScreenSharePresets } = this._lk;
        this._room = new Room({
            publishDefaults: {
                screenShareEncoding: ScreenSharePresets.h1080fps30.encoding,
            },
        });

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
        const camOn = this.callType === 'audio' ? false : _readCameraPref();
        await this._room.localParticipant.setCameraEnabled(camOn);
        this._camOff = !camOn;
        this._audioPrefs = _readAudioCapturePrefs();
        if (_hasStoredAudioPrefs()) {
            try {
                await this._applySavedAudioCaptureOptions();
            } catch (err) {
                this._error = err instanceof Error ? err.message : String(err);
                this._status = 'error';
                this._connecting = false;
                this._room.disconnect();
                this._room = null;
                this._lk = null;
                return;
            }
        }
        this._status = 'active';
        this._connecting = false;
        this._syncParticipants();
    }

    async _connectP2P() {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error(
                this._tp('call_overlay.err_webrtc_https', { origin: window.location.origin }),
            );
        }

        const turnRes = await fetch('/sync/api/v1/calls/turn-credentials', { credentials: 'include' });
        if (!turnRes.ok) {
            throw new Error(this._tp('call_overlay.err_turn_credentials', { status: String(turnRes.status) }));
        }
        const turnData = await turnRes.json();
        const iceServers = [{ urls: turnData.uris, username: turnData.username, credential: turnData.credential }];

        const wantVideo = this.callType !== 'audio';
        this._localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: wantVideo,
        });
        const camOn = wantVideo ? _readCameraPref() : false;
        this._localStream.getVideoTracks().forEach((t) => {
            t.enabled = camOn;
        });
        this._camOff = !camOn;

        // P2P: подключение к WS обрабатывается sync-ws.service.js и SyncStore.
        // CallOverlay получает сигналы через событие call-signal на window.
        window.addEventListener('call-signal', this._onCallSignalHandler);
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
        const localPubs = this._videoPubsForGrid(local);
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
            const pubs = this._videoPubsForGrid(remote);
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
        void this._restoreCameraIfScreenShareEnded();
    }

    async _restoreCameraAfterScreenShare() {
        if (!this._room || !this._cameraSuspendedForScreenShare) return;
        this._cameraSuspendedForScreenShare = false;
        const want = this._cameraEnabledBeforeScreenShare;
        await this._room.localParticipant.setCameraEnabled(want);
        this._camOff = !want;
        _writeCameraPref(want);
        this.requestUpdate();
    }

    async _restoreCameraIfScreenShareEnded() {
        if (!this._room || !this._cameraSuspendedForScreenShare) return;
        if (this._room.localParticipant.isScreenShareEnabled) return;
        await this._restoreCameraAfterScreenShare();
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
        if (this._room?.localParticipant?.isScreenShareEnabled) {
            this._mediaSettingsError = this._tp('call_overlay.media_stop_screen_for_cam');
            return;
        }
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
        const lp = this._room.localParticipant;
        try {
            const next = !lp.isScreenShareEnabled;
            if (next) {
                this._cameraEnabledBeforeScreenShare = lp.isCameraEnabled;
                this._cameraSuspendedForScreenShare = true;
                await lp.setCameraEnabled(false);
                this._camOff = true;
                await lp.setScreenShareEnabled(true);
            } else {
                await lp.setScreenShareEnabled(false);
                await this._restoreCameraAfterScreenShare();
            }
            this.requestUpdate();
        } catch (e) {
            if (this._cameraSuspendedForScreenShare && !lp.isScreenShareEnabled) {
                await this._restoreCameraAfterScreenShare();
            }
            const name = e && typeof e === 'object' && 'name' in e ? e.name : '';
            if (name === 'NotAllowedError' || name === 'AbortError') return;
            this._error = e instanceof Error ? e.message : String(e);
        }
    }

    _clearCopyLinkFeedbackTimer() {
        if (this._copyLinkFeedbackTimerId != null) {
            clearTimeout(this._copyLinkFeedbackTimerId);
            this._copyLinkFeedbackTimerId = null;
        }
    }

    _requestMinimize() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            return;
        }
        this.dispatchEvent(new CustomEvent('call-minimize-request', { bubbles: true, composed: true }));
    }

    async _copyLink() {
        if (!this.callId) return;

        let resolvedUrl = null;
        const urlPromise = fetch('/sync/api/v1/calls/links', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                channel_id: this.channelId,
                call_type: 'video',
                call_id: this.callId,
            }),
        }).then(res => {
            if (!res.ok) throw new Error('fetch');
            return res.json();
        }).then(body => {
            const url = body.join_url;
            if (typeof url !== 'string' || url.trim() === '') throw new Error('fetch');
            resolvedUrl = url;
            return url;
        });

        // ClipboardItem с deferred blob: clipboard.write() вызывается синхронно
        // в рамках user gesture, данные резолвятся async — работает на mobile Safari/Chrome
        if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
            try {
                const item = new ClipboardItem({
                    'text/plain': urlPromise.then(u => new Blob([u], { type: 'text/plain' })),
                });
                await navigator.clipboard.write([item]);
                this._onCopyLinkDone();
                return;
            } catch {
                if (resolvedUrl === null) {
                    this._mediaSettingsError = this._tp('call_overlay.copy_link_bad_response');
                    this.requestUpdate();
                    return;
                }
            }
        }

        if (resolvedUrl === null) {
            try {
                await urlPromise;
            } catch {
                this._mediaSettingsError = this._tp('call_overlay.copy_link_bad_response');
                this.requestUpdate();
                return;
            }
        }
        try {
            await copyTextToClipboard(resolvedUrl);
        } catch {
            this._mediaSettingsError = this._tp('call_overlay.copy_link_clipboard_failed');
            this.requestUpdate();
            return;
        }
        this._onCopyLinkDone();
    }

    _onCopyLinkDone() {
        this._clearCopyLinkFeedbackTimer();
        this._copyLinkFeedback = true;
        this.requestUpdate();
        this._copyLinkFeedbackTimerId = window.setTimeout(() => {
            this._copyLinkFeedbackTimerId = null;
            this._copyLinkFeedback = false;
            this.requestUpdate();
        }, 2000);
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

    _toggleRecording() {
        if (!this.callId) return;
        if (this._recordingStatus === 'starting' || this._recordingStatus === 'stopping') return;
        const start = this._recordingStatus === 'idle' || this._recordingStatus === 'failed';
        if (start) {
            if (!this._canTransferMeetingAdmin()) {
                this._recordingError = this._tp('call_overlay.recording_admin_only');
                return;
            }
            this._recordingStatus = 'starting';
            this.dispatchEvent(new CustomEvent('call-recording-start', {
                bubbles: true,
                composed: true,
                detail: { callId: this.callId },
            }));
            return;
        }
        if (!this._canStopRecording()) {
            this._recordingError = this._tp('call_overlay.recording_stop_restricted');
            return;
        }
        this._recordingStatus = 'stopping';
        this.dispatchEvent(new CustomEvent('call-recording-stop', {
            bubbles: true,
            composed: true,
            detail: { callId: this.callId },
        }));
    }

    setRecordingStatus(status, error = null) {
        this._recordingStatus = status;
        this._recordingError = error;
        this.requestUpdate();
    }

    _cleanup() {
        this._clearCopyLinkFeedbackTimer();
        this._copyLinkFeedback = false;
        this._exitTileFullscreenIfOurs();
        this._fullscreenTileKey = null;
        this._connecting = false;
        if (this._room) { this._room.disconnect(); this._room = null; }
        if (this._localStream) {
            this._localStream.getTracks().forEach(t => t.stop());
            this._localStream = null;
        }
        window.removeEventListener('call-signal', this._onCallSignalHandler);
        this._lk = null;
        this._tiles = [];
        this._mediaSettingsError = null;
        this._cameraSuspendedForScreenShare = false;
        this._closeMenus();
    }

    _sfuParticipantCount() {
        if (!this._room) return 0;
        return 1 + this._room.remoteParticipants.size;
    }

    _activeDeviceId(kind) {
        if (!this._room) return '';
        const id = this._room.getActiveDevice(kind);
        return id ?? '';
    }

    _deviceLabel(d, index) {
        if (d.label && d.label.trim()) return d.label;
        return this._tp('call_overlay.device_fallback', { n: index + 1 });
    }

    _formatDuration(sec) {
        const m = Math.floor(sec / 60).toString().padStart(2, '0');
        const s = (sec % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    }

    _overlayChatMessages() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            return [];
        }
        return SyncStore.getCallOverlayDisplayMessages(this.channelId);
    }

    _chatSenderName(message) {
        const sender = message?.sender;
        if (sender && typeof sender === 'object') {
            if (typeof sender.display_name === 'string' && sender.display_name.trim() !== '') {
                return sender.display_name.trim();
            }
            if (typeof sender.user_id === 'string' && sender.user_id !== '') {
                return sender.user_id;
            }
            if (typeof sender.id === 'string' && sender.id !== '') {
                return sender.id;
            }
        }
        return this._tp('call_overlay.participant_fallback');
    }

    _chatSenderIdentity(message) {
        const sender = message?.sender;
        if (sender && typeof sender === 'object') {
            if (typeof sender.user_id === 'string' && sender.user_id !== '') {
                return sender.user_id;
            }
            if (typeof sender.id === 'string' && sender.id !== '') {
                return sender.id;
            }
        }
        return this._chatSenderName(message);
    }

    _chatSenderInitial(message) {
        const senderName = this._chatSenderName(message).trim();
        if (senderName === '') return '?';
        return senderName.slice(0, 1).toUpperCase();
    }

    _chatSenderAvatarStyle(message) {
        const senderIdentity = this._chatSenderIdentity(message);
        const hue = hueFromString(senderIdentity);
        return `background:hsl(${hue} 48% 42%)`;
    }

    _chatText(message) {
        const contents = Array.isArray(message?.contents) ? message.contents : [];
        const textBlock = contents.find(
            (item) => item?.type === 'text/plain' && item?.data && typeof item.data.body === 'string',
        );
        return textBlock?.data?.body ?? '';
    }

    _isOwnMessage(message) {
        const sender = message?.sender;
        if (!sender || typeof sender !== 'object') {
            return false;
        }
        const senderId = typeof sender.user_id === 'string' && sender.user_id !== ''
            ? sender.user_id
            : sender.id;
        return typeof this.currentUserId === 'string'
            && this.currentUserId !== ''
            && senderId === this.currentUserId;
    }

    _messageTimeText(message) {
        if (typeof message?.sent_at !== 'string' || message.sent_at === '') {
            return '';
        }
        const dt = new Date(message.sent_at);
        if (Number.isNaN(dt.getTime())) {
            return '';
        }
        const loc = this.i18n.getCurrentLocale() === 'ru' ? 'ru-RU' : 'en-US';
        return dt.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' });
    }

    async _loadOverlayChat() {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            this._chatError = this._tp('call_overlay.chat_no_channel');
            return;
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            this._chatError = this._tp('call_overlay.chat_no_messages_service');
            return;
        }
        this._chatError = null;
        try {
            await SyncStore.loadCallOverlayMessages(syncApi, this.channelId);
        } catch (e) {
            this._chatError = e instanceof Error ? e.message : String(e);
        }
    }

    async _loadOlderOverlayHistory(listEl) {
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            return;
        }
        const history = SyncStore.getCallOverlayHistoryState(this.channelId);
        if (!history.hasMoreOlder || history.loadingOlder) {
            return;
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            throw new Error(this._tp('message_list.err_sync_api'));
        }
        const prevHeight = listEl.scrollHeight;
        const prevTop = listEl.scrollTop;
        await SyncStore.loadOlderCallOverlayMessages(syncApi, this.channelId);
        await this.updateComplete;
        const nextHeight = listEl.scrollHeight;
        const delta = nextHeight - prevHeight;
        if (delta > 0) {
            listEl.scrollTop = prevTop + delta;
        }
    }

    _onOverlayChatScroll(e) {
        const listEl = e.target;
        if (listEl.scrollTop <= 60) {
            void this._loadOlderOverlayHistory(listEl);
        }
    }

    _buildOverlayPendingMessage(commandId, text) {
        const senderId = this.currentUserId;
        if (typeof senderId !== 'string' || senderId === '') {
            throw new Error(this._tp('call_overlay.err_current_user_send'));
        }
        const senderName = this.names?.[senderId] || this._tp('composer.you');
        return {
            id: `pending:${commandId}`,
            channel_id: this.channelId,
            thread_id: null,
            parent_message_id: null,
            sender: { user_id: senderId, id: senderId, display_name: senderName, avatar_url: null },
            status: 'pending',
            sent_at: new Date().toISOString(),
            edited_at: null,
            contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
        };
    }

    async _sendOverlayChatMessage() {
        const text = this._chatInput.trim();
        if (text === '') {
            return;
        }
        if (typeof this.channelId !== 'string' || this.channelId === '') {
            this._chatError = this._tp('call_overlay.chat_send_no_channel');
            return;
        }
        const syncApi = this.services.get('syncApi');
        if (!syncApi) {
            this._chatError = this._tp('call_overlay.chat_no_messages_service');
            return;
        }
        const commandId = typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID()
            : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
        const pendingMessage = this._buildOverlayPendingMessage(commandId, text);
        this._chatInput = '';
        this._chatSending = true;
        this._chatError = null;
        SyncStore.addCallOverlayPending(this.channelId, commandId, pendingMessage);
        try {
            const sent = await syncApi.sendMessage(this.channelId, {
                thread_id: null,
                parent_message_id: null,
                contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
            });
            SyncStore.resolveCallOverlayPending(this.channelId, commandId, sent);
        } catch (e) {
            SyncStore.failCallOverlayPending(this.channelId, commandId);
            this._chatError = e instanceof Error ? e.message : String(e);
        } finally {
            this._chatSending = false;
        }
    }

    _onChatInputKeydown(e) {
        if (e.key !== 'Enter' || e.shiftKey) {
            return;
        }
        e.preventDefault();
        void this._sendOverlayChatMessage();
    }

    _toggleChatPanel() {
        this._chatPanelOpen = !this._chatPanelOpen;
    }

    render() {
        if (this._status === 'error') {
            return html`
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:20px;padding:32px;">
                    <div style="font-size:48px;">⚠️</div>
                    <div style="color:#f87171;font-size:16px;font-weight:600;text-align:center;">${this._tp('call_overlay.call_error_title')}</div>
                    <div style="color:rgba(255,255,255,0.6);font-size:13px;text-align:center;max-width:400px;">${this._error}</div>
                    <button class="ctrl-btn hangup" @click=${this._hangup}>${this._tp('close')}</button>
                </div>
            `;
        }
        if (this._status === 'ended') {
            return html`<div style="display:flex;align-items:center;justify-content:center;height:100%;color:rgba(255,255,255,0.5);font-size:18px;">${this._tp('call_overlay.call_ended')}</div>`;
        }

        const gridItems = this._room ? this._tiles : this._participants;
        const gridCount = gridItems.length;
        const gridClass = gridCount === 1 ? 'one' : gridCount === 2 ? 'two' : 'many';
        const participantCount = this._room ? this._sfuParticipantCount() : this._participants.length;
        const screenOn = this._room?.localParticipant?.isScreenShareEnabled === true;
        const canControlRecording = this._recordingStatus === 'recording'
            ? this._canStopRecording()
            : this._canTransferMeetingAdmin();
        const overlayHistory = SyncStore.getCallOverlayHistoryState(this.channelId);

        return html`
            <div class="header">
                <span>
                    ${this._status === 'active' ? html`<span class="status-dot"></span>` : ''}
                    ${this._status === 'connecting' ? this._tp('call_overlay.connecting') : this._formatDuration(this._duration)}
                </span>
                <div style="display:flex;align-items:center;gap:8px;">
                    ${typeof this.channelId === 'string' && this.channelId !== '' ? html`
                        <button
                            type="button"
                            class="ctrl-btn"
                            style="width:36px;height:36px;"
                            @click=${this._requestMinimize}
                            title=${this._tp('call_overlay.minimize_title')}
                        >
                            <platform-icon name="chevron-down" size="18" aria-hidden="true"></platform-icon>
                        </button>
                    ` : ''}
                    ${this._recordingStatus !== 'idle' ? html`
                        <span
                            class="recording-badge"
                            style="color:${this._recordingStatus === 'recording' ? '#ef4444' : 'rgba(255,255,255,0.75)'};"
                        >
                            ${this._recordingStatus === 'recording' ? html`<span class="recording-badge-dot"></span>` : ''}
                            REC
                        </span>
                    ` : ''}
                    <span style="opacity:0.5">${this._tp('call_overlay.participants_abbr', { n: participantCount })}</span>
                    ${this.callId ? html`
                        <button class="ctrl-btn" style="width:36px;height:36px;font-size:14px;" @click=${this._copyLink} title=${this._tp('call_overlay.copy_link_title')}>
                            ${this._copyLinkFeedback
                                ? html`<span style="color:#22c55e"><platform-icon name="check" size="16" aria-hidden="true"></platform-icon></span>`
                                : html`<platform-icon name="copy" size="16" aria-hidden="true"></platform-icon>`}
                        </button>
                    ` : ''}
                </div>
            </div>

            <div class="call-stage">
                <div class="video-grid ${gridClass}">
                    ${gridItems.map((p, i) => this._renderTile(p, i))}
                </div>
                ${this._chatPanelOpen ? html`
                <section class="call-chat-panel">
                    <div class="call-chat-panel-header">
                        <span class="call-chat-panel-title">${this._tp('call_overlay.chat_panel_title')}</span>
                        <button
                            type="button"
                            class="call-chat-panel-close"
                            title=${this._tp('call_overlay.chat_hide')}
                            @click=${this._toggleChatPanel}
                        >
                            <platform-icon name="close" size="14" aria-hidden="true"></platform-icon>
                        </button>
                    </div>
                    <div class="call-chat-list" @scroll=${this._onOverlayChatScroll}>
                        ${overlayHistory.loadingOlder
                            ? html`<div class="call-chat-state">${this._tp('call_overlay.loading_history')}</div>`
                            : ''}
                        ${SyncStore.getCallOverlayLoading(this.channelId)
                            ? html`<div class="call-chat-state">${this._tp('call_overlay.loading_messages')}</div>`
                            : this._overlayChatMessages().length === 0
                                ? html`<div class="call-chat-state">${this._tp('call_overlay.no_messages_yet')}</div>`
                                : this._overlayChatMessages().map((message) => {
                                    const text = this._chatText(message);
                                    if (text === '') {
                                        return html``;
                                    }
                                    const own = this._isOwnMessage(message);
                                    return html`
                                        <article class="call-chat-item ${own ? 'self' : ''} ${message.status === 'failed' ? 'failed' : ''}">
                                            <div class="call-chat-row">
                                                <span class="call-chat-avatar" style=${this._chatSenderAvatarStyle(message)}>
                                                    ${this._chatSenderInitial(message)}
                                                </span>
                                                <div class="call-chat-content">
                                                    <div class="call-chat-meta">
                                                        <span class="call-chat-author">${this._chatSenderName(message)}</span>
                                                        <span>${this._messageTimeText(message)}</span>
                                                    </div>
                                                    <p class="call-chat-text">${text}</p>
                                                </div>
                                            </div>
                                        </article>
                                    `;
                                })}
                    </div>
                    ${this._chatError ? html`<div class="call-chat-error">${this._chatError}</div>` : ''}
                    <div class="call-chat-composer">
                        <textarea
                            class="call-chat-input"
                            .value=${this._chatInput}
                            @input=${(e) => { this._chatInput = e.target.value; }}
                            @keydown=${this._onChatInputKeydown}
                            placeholder=${this._tp('call_overlay.message_placeholder')}
                            rows="2"
                        ></textarea>
                        <button
                            type="button"
                            class="call-chat-send"
                            ?disabled=${this._chatSending || this._chatInput.trim() === ''}
                            @click=${() => void this._sendOverlayChatMessage()}
                        >
                            ${this._chatSending ? '...' : this._tp('call_overlay.send')}
                        </button>
                    </div>
                </section>
                ` : ''}
            </div>

            ${this._mediaSettingsError ? html`
                <div class="settings-error">${this._mediaSettingsError}</div>
            ` : ''}

            <div class="controls-bar">
                <div class="controls-slot controls-slot--left">
                    ${this._sfuMediaUiAvailable() ? html`
                        <button
                            type="button"
                            class="ctrl-btn"
                            style="width:48px;height:48px;"
                            title=${this._tp('call_overlay.devices_settings_title')}
                            @click=${this._toggleDevicesMenu}
                        >
                            <platform-icon name="settings" size="22" aria-hidden="true"></platform-icon>
                        </button>
                        ${this._devicesMenuOpen ? html`
                            <div class="call-menu call-menu--left" @click=${(e) => e.stopPropagation()}>
                                <label>${this._tp('call_overlay.label_mic')}</label>
                                <select
                                    .value=${this._activeDeviceId('audioinput')}
                                    ?disabled=${this._deviceLists.audioinput.length === 0}
                                    @change=${this._onAudioInputChange}
                                >
                                    ${this._deviceLists.audioinput.length === 0
                                        ? html`<option value="">${this._tp('call_overlay.no_devices')}</option>`
                                        : this._deviceLists.audioinput.map((d, i) => html`
                                        <option value=${d.deviceId}>${this._deviceLabel(d, i)}</option>
                                    `)}
                                </select>
                                ${this.callType !== 'audio' ? html`
                                    <label>${this._tp('call_overlay.label_camera')}</label>
                                    <select
                                        .value=${this._activeDeviceId('videoinput')}
                                        ?disabled=${this._deviceLists.videoinput.length === 0}
                                        @change=${this._onVideoInputChange}
                                    >
                                        ${this._deviceLists.videoinput.length === 0
                                            ? html`<option value="">${this._tp('call_overlay.no_devices')}</option>`
                                            : this._deviceLists.videoinput.map((d, i) => html`
                                            <option value=${d.deviceId}>${this._deviceLabel(d, i)}</option>
                                        `)}
                                    </select>
                                ` : ''}
                                ${this._audioOutputSupported ? html`
                                    <label>${this._tp('call_overlay.label_speaker')}</label>
                                    <select
                                        .value=${this._activeDeviceId('audiooutput')}
                                        ?disabled=${this._deviceLists.audiooutput.length === 0}
                                        @change=${this._onAudioOutputChange}
                                    >
                                        ${this._deviceLists.audiooutput.length === 0
                                            ? html`<option value="">${this._tp('call_overlay.no_devices')}</option>`
                                            : this._deviceLists.audiooutput.map((d, i) => html`
                                            <option value=${d.deviceId}>${this._deviceLabel(d, i)}</option>
                                        `)}
                                    </select>
                                ` : ''}
                            </div>
                        ` : ''}
                    ` : ''}
                </div>
                <div class="controls-slot controls-slot--center">
                    <button class="ctrl-btn ${this._micMuted ? '' : 'active'}" @click=${this._toggleMic} title=${this._micMuted ? this._tp('call_overlay.mic_enable') : this._tp('call_overlay.mic_disable')}>
                        ${this._micMuted
                            ? html`<platform-icon name="mic-off" size="20" aria-hidden="true"></platform-icon>`
                            : html`<platform-icon name="mic" size="20" aria-hidden="true"></platform-icon>`
                        }
                    </button>
                    <button
                        class="ctrl-btn ${this._camOff ? '' : 'active'}"
                        ?disabled=${screenOn}
                        @click=${this._toggleCam}
                        title=${screenOn ? this._tp('call_overlay.cam_stop_screen_first') : (this._camOff ? this._tp('call_overlay.cam_enable') : this._tp('call_overlay.cam_disable'))}
                    >
                        ${this._camOff
                            ? html`<platform-icon name="videocam-off" size="20" aria-hidden="true"></platform-icon>`
                            : html`<platform-icon name="video-call" size="20" filled aria-hidden="true"></platform-icon>`
                        }
                    </button>
                    ${this._room && this._canScreenShare() ? html`
                        <button class="ctrl-btn ${screenOn ? 'active' : ''}" @click=${this._toggleScreenShare} title=${screenOn ? this._tp('call_overlay.screen_share_stop') : this._tp('call_overlay.screen_share_start')}>
                            <platform-icon name="screen-share" size="20" aria-hidden="true"></platform-icon>
                        </button>
                    ` : ''}
                    <button
                        class="ctrl-btn recording-btn ${this._recordingStatus === 'recording' ? 'recording-btn--active' : ''}"
                        ?disabled=${!canControlRecording}
                        @click=${this._toggleRecording}
                        title=${canControlRecording
                            ? (this._recordingStatus === 'recording' ? this._tp('call_overlay.recording_stop') : this._tp('call_overlay.recording_start_meeting'))
                            : (this._recordingStatus === 'recording'
                                ? this._tp('call_overlay.recording_tooltip_stop_denied')
                                : this._tp('call_overlay.recording_tooltip_start_denied'))}
                    >
                        ${this._recordingStatus === 'recording'
                            ? html`<platform-icon name="stop" size="30" filled aria-hidden="true"></platform-icon>`
                            : html`<platform-icon name="fiber-manual-record" size="24" filled aria-hidden="true"></platform-icon>`
                        }
                    </button>
                    <button class="ctrl-btn hangup" @click=${this._hangup} title=${this._tp('call_overlay.hangup_title')}>
                        <platform-icon name="phone-ended" size="24" filled aria-hidden="true"></platform-icon>
                    </button>
                </div>
                <div class="controls-slot controls-slot--right">
                    <button
                        type="button"
                        class="ctrl-btn chat-toggle-btn ${this._chatPanelOpen ? 'chat-toggle-btn--active' : ''}"
                        style="width:48px;height:48px;"
                        title=${this._chatPanelOpen ? this._tp('call_overlay.chat_hide') : this._tp('call_overlay.chat_show')}
                        @click=${this._toggleChatPanel}
                    >
                        <platform-icon name="chat" size="22" aria-hidden="true"></platform-icon>
                    </button>
                    ${this._sfuMediaUiAvailable() ? html`
                        <button
                            type="button"
                            class="ctrl-btn"
                            style="width:48px;height:48px;"
                            title=${this._tp('call_overlay.more_menu')}
                            @click=${this._toggleMoreMenu}
                        >
                            <platform-icon name="more-vert" size="22" filled aria-hidden="true"></platform-icon>
                        </button>
                        ${this._moreMenuOpen ? html`
                            <div class="call-menu call-menu--right" @click=${(e) => e.stopPropagation()}>
                                <div class="call-menu-item--sub">
                                    <button type="button" class="call-menu-item" @click=${this._toggleAudioQualitySub}>
                                        ${this._tp('call_overlay.audio_quality')}
                                        <platform-icon class="call-menu-chevron" name="chevron-right" size="16" aria-hidden="true"></platform-icon>
                                    </button>
                                    ${this._audioQualitySubOpen ? html`
                                        <div class="call-menu-flyout" @click=${(e) => e.stopPropagation()}>
                                            <label class="call-menu-toggle">
                                                <span class="call-menu-toggle-label">${this._tp('call_overlay.noise_suppression')}</span>
                                                <input
                                                    type="checkbox"
                                                    class="call-switch-input"
                                                    .checked=${this._audioPrefs.noiseSuppression}
                                                    @change=${(e) => this._setAudioPref('noiseSuppression', e.target.checked)}
                                                />
                                                <span class="call-switch-visual" aria-hidden="true"></span>
                                            </label>
                                            <label class="call-menu-toggle">
                                                <span class="call-menu-toggle-label">${this._tp('call_overlay.echo_cancellation')}</span>
                                                <input
                                                    type="checkbox"
                                                    class="call-switch-input"
                                                    .checked=${this._audioPrefs.echoCancellation}
                                                    @change=${(e) => this._setAudioPref('echoCancellation', e.target.checked)}
                                                />
                                                <span class="call-switch-visual" aria-hidden="true"></span>
                                            </label>
                                            <label class="call-menu-toggle">
                                                <span class="call-menu-toggle-label">${this._tp('call_overlay.auto_gain')}</span>
                                                <input
                                                    type="checkbox"
                                                    class="call-switch-input"
                                                    .checked=${this._audioPrefs.autoGainControl}
                                                    @change=${(e) => this._setAudioPref('autoGainControl', e.target.checked)}
                                                />
                                                <span class="call-switch-visual" aria-hidden="true"></span>
                                            </label>
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                        ` : ''}
                    ` : ''}
                </div>
            </div>
            ${this._recordingError ? html`
                <div class="settings-error">${this._recordingError}</div>
            ` : ''}
        `;
    }

    _resolveDisplayName(identity) {
        if (!identity) return '?';
        // Гость: "guest:{uuid}:{name}"
        if (identity.startsWith('guest:')) {
            const parts = identity.split(':');
            return parts.slice(2).join(':') || this._tp('call_overlay.guest');
        }
        // Зарегистрированный: смотрим в переданную карту имён
        return this.names?.[identity] || identity;
    }

    _renderTileAdminBadge(identity) {
        if (!this._isMeetingAdminUser(identity)) return html``;
        return html`
            <span class="participant-admin-crown" title=${this._tp('call_overlay.meeting_admin')}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M3 19h18l-1.5-10-5.5 4-2-6-2 6-5.5-4L3 19z"></path>
                </svg>
            </span>
        `;
    }

    _renderTileAdminMenu(identity) {
        if (!this._canTransferMeetingAdmin()) return html``;
        if (typeof identity !== 'string' || identity === '') return html``;
        const menuOpen = this._participantMenuIdentity === identity;
        const canAssign = !this._isGuestIdentity(identity) && !this._isMeetingAdminUser(identity);
        return html`
            <button
                type="button"
                class="tile-action-btn"
                title=${this._tp('call_overlay.participant_menu')}
                @click=${(e) => this._toggleParticipantMenu(e, identity)}
            >
                <platform-icon name="more-vert" size="16" filled aria-hidden="true"></platform-icon>
            </button>
            ${menuOpen ? html`
                <div class="tile-action-menu">
                    ${canAssign ? html`
                        <button
                            type="button"
                            class="tile-action-menu-item"
                            @click=${(e) => this._assignMeetingAdmin(e, identity)}
                        >
                            ${this._tp('call_overlay.promote_meeting_admin')}
                        </button>
                    ` : html`
                        <div class="tile-action-menu-item">${this._tp('call_overlay.participant_action_unavailable')}</div>
                    `}
                </div>
            ` : ''}
        `;
    }

    _renderTile(item, index) {
        if (this._room) {
            const label = item.isLocal ? this._tp('composer.you') : this._resolveDisplayName(item.identity);
            const displayLabel = item.isScreen ? this._tp('call_overlay.screen_tile_suffix', { label }) : label;
            const hasVideo = item.track != null;
            const tileClass = item.isScreen ? 'participant-tile screen' : 'participant-tile';
            const tileKey = item.key;
            return html`
                <div class="${tileClass}" data-idx=${index} data-tile-key=${tileKey}>
                    ${this._renderTileAdminMenu(item.identity)}
                    ${hasVideo
                        ? html`<video autoplay playsinline ?muted=${item.isLocal}></video>`
                        : html`<div class="avatar-placeholder">${displayLabel?.[0]?.toUpperCase() ?? '?'}</div>`
                    }
                    <span class="participant-name">
                        ${this._renderTileAdminBadge(item.identity)}
                        ${displayLabel}
                    </span>
                    ${this._tileFullscreenButton(tileKey, hasVideo)}
                </div>
            `;
        }
        const participant = item;
        const label = participant.isLocal ? this._tp('composer.you') : this._resolveDisplayName(participant.identity);
        const stream = participant.stream;
        const hasVideo = stream?.getVideoTracks().some((t) => t.readyState === 'live' && t.enabled);
        const tileKey = `p2p-${index}`;
        return html`
            <div class="participant-tile" data-idx=${index} data-tile-key=${tileKey}>
                ${this._renderTileAdminMenu(participant.identity)}
                ${this._tileFullscreenButton(tileKey, hasVideo)}
                ${hasVideo
                    ? html`<video autoplay playsinline muted></video>`
                    : html`<div class="avatar-placeholder">${label?.[0]?.toUpperCase() ?? '?'}</div>`
                }
                <span class="participant-name">
                    ${this._renderTileAdminBadge(participant.identity)}
                    ${label}
                </span>
            </div>
        `;
    }

    updated(changedProps) {
        const critical = this._status === 'error' || this._status === 'ended';
        this.toggleAttribute('data-overlay-critical', critical);
        if (changedProps.has('channelId')) {
            this._chatError = null;
            void this._loadOverlayChat();
        }
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
