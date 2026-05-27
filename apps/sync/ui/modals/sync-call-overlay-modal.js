/**
 * sync-call-overlay-modal — полноэкранный оверлей звонка LiveKit (SFU).
 *
 * Полностью соответствует event-канону (`frontend.mdc`, `ui_factories.mdc`,
 * `ui_components.mdc`):
 *   - State через фабрики `useOp`/`useSlice`/`useEvent`/`select`.
 *   - Никаких `localStorage` напрямую, никакого `fetch/httpRequest`.
 *   - Аудионастройки (NS/EC/AGC, camera default, deviceIds) живут в slice
 *     `sync/call_prefs`, persist делает bridge-effect
 *     `sync-call-prefs.effect.js` через `STORAGE_PERSIST_REQUESTED`.
 *
 * Что внутри:
 *   - полноэкранная чёрная stage (position: fixed inset 0).
 *   - Header: status-dot + duration / "Подключение…", REC-badge, participants
 *     count, copy-link, minimize.
 *   - Video-grid: tiles per participant (one/two/many layout), avatar для
 *     placeholder, screen-share как отдельный tile, при демонстрации экрана
 *     камера может оставаться включённой; плавающая панель с превью камеры и
 *     кнопками; при поддержке Chromium — Document Picture-in-Picture (отдельное
 *     окно поверх других приложений, видно при смене вкладки / шаринге не браузера),
 *     иначе панель внутри оверлея. fullscreen-tile-кнопка,
 *     per-tile admin-menu (transfer admin) для meeting admin.
 *   - Controls bar (3 слота): [Devices menu] | [mic/cam/screen/recording/
 *     hangup] | [chat-toggle/more-menu (audio quality NS/EC/AGC)].
 *   - Chat panel (правый сайдбар): сообщения текущего канала из
 *     `state.syncMessagesStore.byChannelId[channelId]`, ленивая загрузка старых,
 *     send через `messagesSendOp`.
 *   - Minimize: атрибут `data-minimized` на :host; для открытой модалки нужен
 *     селектор `:host([open][data-minimized])`, иначе `display:flex !important`
 *     от :host([open]) перекрывает скрытие. LiveKit Room остаётся в JS; expand из
 *     шапки чата снимает minimized.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import { initialsFromName, syncAvatarHueVar } from '../_helpers/sync-hue.js';
import { formatDurationSeconds } from '@platform/lib/utils/format-duration.js';

const SCROLL_TOP_THRESHOLD = 60;
const COPY_LINK_FEEDBACK_MS = 2000;

function _canUseMediaDevices() {
    if (typeof navigator === 'undefined') return false;
    const md = navigator.mediaDevices;
    return md !== null && md !== undefined && typeof md.getUserMedia === 'function';
}

export class SyncCallOverlayModal extends PlatformModal {
    static modalKind = 'sync.call_overlay';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformModal.properties,
        callId: { type: String },
        callType: { type: String },
        channelId: { type: String },
        /** Предзагруженные учётные данные LiveKit после гостевого join_accept (без sync/call_token). */
        livekitToken: { type: String },
        livekitUrl: { type: String },
        participantNames: { type: Object },
        /** LiveKit participant_identity из JoinResponse, для чата и подписей «Вы». */
        participantIdentity: { type: String },
        _connecting: { state: true },
        _status: { state: true },
        _error: { state: true },
        _tiles: { state: true },
        _participantsCount: { state: true },
        _duration: { state: true },
        _micMuted: { state: true },
        _camOff: { state: true },
        _screenOn: { state: true },
        _devicesMenuOpen: { state: true },
        _moreMenuOpen: { state: true },
        /** Узкая ширина: запись и устройства только в меню «⋯». */
        _controlsCompact: { state: true },
        _audioQualitySubOpen: { state: true },
        _participantMenuParticipantIdentity: { state: true },
        _deviceLists: { state: true },
        _audioOutputSupported: { state: true },
        _fullscreenTileKey: { state: true },
        _copyLinkFeedback: { state: true },
        _chatInput: { state: true },
        _chatSending: { state: true },
        /** Пользователь свернул плавающую панель «камера при демонстрации экрана» (трек не гасим). */
        _sharePipDismissed: { state: true },
    };

    static styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            :host {
                position: fixed;
                inset: 0;
                z-index: var(--z-modal, 9999);
                background: var(--bg-deep, #0a0a0f);
                color: #fff;
                display: flex;
                flex-direction: column;
                box-sizing: border-box;
                max-height: 100vh;
                max-height: 100dvh;
                overflow: hidden;
                padding-top: env(safe-area-inset-top, 0px);
                padding-right: env(safe-area-inset-right, 0px);
                padding-bottom: env(safe-area-inset-bottom, 0px);
                padding-left: env(safe-area-inset-left, 0px);
                touch-action: manipulation;
                --call-overlay-chrome: 200px;
            }
            :host([open]) {
                display: flex !important;
                flex-direction: column;
                width: 100%;
                height: 100%;
                max-width: none;
                min-height: 0;
                z-index: var(--platform-modal-layer-z, var(--z-modal, 9999)) !important;
                box-sizing: border-box;
                padding-top: max(var(--space-2), var(--platform-safe-top));
                padding-right: max(var(--space-2), var(--platform-safe-right));
                padding-bottom: max(var(--space-2), var(--platform-safe-bottom));
                padding-left: max(var(--space-2), var(--platform-safe-left));
            }
            :host([data-minimized]) {
                position: fixed !important;
                left: -9999px !important;
                top: 0 !important;
                width: 4px !important;
                height: 4px !important;
                visibility: hidden !important;
                pointer-events: none !important;
                clip-path: inset(50%) !important;
            }
            :host([open][data-minimized]) {
                display: none !important;
            }

            .header {
                position: relative;
                z-index: 10000;
                isolation: isolate;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4) var(--space-6) var(--space-2);
                color: rgba(255, 255, 255, 0.65);
                font-size: var(--text-sm);
                pointer-events: auto;
            }
            .header-left, .header-right {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .header .ctrl platform-icon {
                pointer-events: none;
            }
            .header .header-right .ctrl.header-icon-btn {
                width: 36px;
                height: 36px;
                min-width: 36px;
                min-height: 36px;
                flex-shrink: 0;
                touch-action: manipulation;
                -webkit-tap-highlight-color: transparent;
            }
            .status-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success, #22c55e);
                display: inline-block;
                margin-right: 6px;
            }
            .recording-badge {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                color: var(--color-error, #ef4444);
                font-size: var(--text-xs);
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            .recording-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--color-error, #ef4444);
                animation: rec-pulse 1.2s ease-in-out infinite;
            }
            @keyframes rec-pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.45; transform: scale(0.85); }
            }

            .stage {
                flex: 1 1 0;
                min-height: 0;
                position: relative;
                display: flex;
                overflow: hidden;
            }
            .video-grid {
                flex: 1;
                min-height: 0;
                min-width: 0;
                display: grid;
                align-content: start;
                padding: var(--space-4);
                gap: var(--space-3);
                overflow-y: auto;
                overflow-x: hidden;
            }
            .video-grid.one  { grid-template-columns: 1fr; align-content: center; justify-items: center; }
            .video-grid.two  { grid-template-columns: 1fr 1fr; }
            .video-grid.many { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }

            /* Резерв под шапку оверлея + панель + error-bar; без лимита плитка 16:9 на ультрашироком экране
               вырастает выше viewport и уезжает под нижний край вместе с кнопками. */
            .video-grid.one .tile {
                width: min(100%, calc((100vh - var(--call-overlay-chrome)) * 16 / 9));
                width: min(100%, calc((100dvh - var(--call-overlay-chrome)) * 16 / 9));
                max-width: 100%;
                max-height: calc(100vh - var(--call-overlay-chrome));
                max-height: calc(100dvh - var(--call-overlay-chrome));
                height: auto;
            }

            .tile {
                position: relative;
                background: rgba(255, 255, 255, 0.05);
                border-radius: var(--radius-2xl, 18px);
                overflow: hidden;
                aspect-ratio: 16 / 9;
                isolation: isolate;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .tile.screen { background: #000; }
            .tile video {
                width: 100%;
                height: 100%;
                object-fit: cover;
                pointer-events: none;
            }
            .tile.screen video { object-fit: contain; }
            .tile:fullscreen, .tile:-webkit-full-screen {
                width: 100%;
                height: 100%;
                aspect-ratio: auto;
                border-radius: 0;
            }
            .tile:fullscreen video, .tile:-webkit-full-screen video {
                object-fit: contain;
                pointer-events: auto;
            }

            .avatar {
                width: 88px;
                height: 88px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                font-weight: 700;
                font-size: var(--text-2xl, 28px);
            }
            .avatar.pastel-initials {
                --sync-avatar-h: 0;
                background: hsl(var(--sync-avatar-h), 34%, 38%);
                color: #fff;
            }
            .name {
                position: absolute;
                left: var(--space-3);
                bottom: var(--space-3);
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 4px 10px;
                background: rgba(0, 0, 0, 0.55);
                color: #fff;
                font-size: var(--text-xs);
                border-radius: 999px;
                pointer-events: auto;
            }
            .crown { display: inline-flex; color: #fbbf24; }
            .tile-btn {
                position: absolute;
                width: 34px;
                height: 34px;
                border-radius: var(--radius-md, 10px);
                border: none;
                background: rgba(0, 0, 0, 0.55);
                color: #fff;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                z-index: 50;
                pointer-events: auto;
                transition: background var(--duration-fast);
            }
            .tile-btn:hover { background: rgba(0, 0, 0, 0.78); }
            .tile-btn.active { background: var(--accent); }
            .tile-fs { top: var(--space-2); right: var(--space-2); }
            .tile-actions { top: var(--space-2); left: var(--space-2); }
            .tile-action-menu {
                position: absolute;
                top: 46px;
                left: var(--space-2);
                min-width: 220px;
                padding: var(--space-1);
                background: rgba(20, 20, 26, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: var(--radius-lg, 12px);
                z-index: 60;
            }
            .tile-action-menu button {
                width: 100%;
                padding: 8px 10px;
                background: transparent;
                border: none;
                border-radius: var(--radius-md, 8px);
                color: #fff;
                text-align: left;
                cursor: pointer;
                font-size: var(--text-sm);
            }
            .tile-action-menu button:hover { background: rgba(255, 255, 255, 0.12); }

            .chat-panel {
                position: absolute;
                top: var(--space-4);
                right: var(--space-4);
                bottom: var(--space-4);
                width: min(360px, calc(100vw - var(--space-8)));
                background: rgba(20, 20, 26, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: var(--radius-2xl, 16px);
                display: flex;
                flex-direction: column;
                z-index: 130;
            }
            .chat-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                color: #fff;
                font-weight: var(--font-semibold);
            }
            .chat-close {
                width: 30px; height: 30px;
                border: 1px solid rgba(255, 255, 255, 0.18);
                background: rgba(255, 255, 255, 0.06);
                color: #fff;
                border-radius: 50%;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .chat-list {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-3);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .chat-empty {
                text-align: center;
                color: rgba(255, 255, 255, 0.55);
                font-size: var(--text-xs);
                padding: var(--space-3);
            }
            .chat-item {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: var(--radius-md, 10px);
                padding: 8px 10px;
                color: #fff;
            }
            .chat-item.self {
                background: rgba(99, 102, 241, 0.22);
                border-color: rgba(99, 102, 241, 0.42);
            }
            .chat-meta {
                display: flex;
                justify-content: space-between;
                gap: 6px;
                margin-bottom: 4px;
                font-size: 11px;
                color: rgba(255, 255, 255, 0.6);
            }
            .chat-text {
                margin: 0;
                white-space: pre-wrap;
                word-break: break-word;
                color: rgba(255, 255, 255, 0.92);
                font-size: var(--text-sm);
                line-height: 1.4;
            }
            .chat-composer {
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                padding: var(--space-2) var(--space-3);
                display: flex;
                gap: var(--space-2);
                align-items: flex-end;
            }
            .chat-input {
                flex: 1;
                min-height: 36px;
                max-height: 120px;
                padding: 8px 10px;
                border-radius: var(--radius-md, 8px);
                border: 1px solid rgba(255, 255, 255, 0.18);
                background: rgba(255, 255, 255, 0.06);
                color: #fff;
                font: inherit;
                font-size: var(--text-sm);
                resize: none;
                outline: none;
            }
            .chat-input:focus { border-color: var(--accent); }
            .chat-send {
                height: 36px;
                padding: 0 12px;
                border-radius: var(--radius-md, 8px);
                border: 1px solid var(--accent);
                background: var(--accent);
                color: #fff;
                cursor: pointer;
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }
            .chat-send:disabled { opacity: 0.5; cursor: default; }

            .controls {
                flex-shrink: 0;
                display: grid;
                grid-template-columns: 1fr auto 1fr;
                align-items: center;
                padding: var(--space-3) var(--space-6) var(--space-4);
                gap: var(--space-3);
                position: relative;
            }
            .slot-left, .slot-right {
                display: inline-flex;
                gap: var(--space-2);
                align-items: center;
                position: relative;
            }
            .slot-right { justify-content: flex-end; }
            .slot-center {
                display: inline-flex;
                gap: var(--space-3);
                align-items: center;
                justify-content: center;
            }

            .ctrl {
                width: 52px;
                height: 52px;
                border-radius: 50%;
                border: none;
                background: rgba(255, 255, 255, 0.12);
                color: #fff;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                transition: background var(--duration-fast), transform var(--duration-fast);
            }
            .ctrl:hover { background: rgba(255, 255, 255, 0.2); }
            .ctrl.active { background: rgba(255, 255, 255, 0.92); color: #000; }
            .ctrl[disabled] { opacity: 0.35; cursor: not-allowed; }
            .ctrl.hangup {
                width: 60px; height: 60px;
                background: var(--color-error, #ef4444);
            }
            .ctrl.hangup:hover { background: #dc2626; }
            .ctrl.recording-active {
                background: var(--color-error, #ef4444);
                box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.35);
            }
            .ctrl.chat-active { background: var(--accent); }
            .ctrl.login-in-call {
                width: auto;
                min-width: 36px;
                padding: 0 10px;
                font-size: var(--text-xs);
                white-space: nowrap;
            }

            .menu {
                position: absolute;
                bottom: calc(100% + var(--space-2));
                min-width: 240px;
                padding: var(--space-2);
                background: rgba(20, 20, 26, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: var(--radius-lg, 12px);
                color: #fff;
                z-index: 100;
            }
            .menu.left { left: 0; }
            .menu.right { right: 0; }
            .menu label {
                display: block;
                font-size: var(--text-xs);
                color: rgba(255, 255, 255, 0.65);
                margin: var(--space-2) 0 4px;
            }
            .menu select {
                width: 100%;
                padding: 8px 10px;
                border-radius: var(--radius-md, 8px);
                border: 1px solid rgba(255, 255, 255, 0.18);
                background: rgba(255, 255, 255, 0.08);
                color: #fff;
                font-size: var(--text-sm);
            }
            .menu-toggle-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: 8px 4px;
                font-size: var(--text-sm);
                color: rgba(255, 255, 255, 0.95);
            }
            .menu-toggle-label {
                flex: 1;
                min-width: 0;
                line-height: 1.3;
            }
            .menu-toggle-row platform-switch {
                flex-shrink: 0;
            }
            .menu-toggle-row + .menu-toggle-row { border-top: 1px solid rgba(255, 255, 255, 0.08); }
            .menu-section-title {
                padding: 6px 4px;
                font-size: var(--text-xs);
                color: rgba(255, 255, 255, 0.55);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
            .menu-hint {
                margin: 0 0 var(--space-3);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                line-height: 1.45;
                color: #fde68a;
                background: rgba(234, 179, 8, 0.12);
                border: 1px solid rgba(234, 179, 8, 0.35);
                border-radius: var(--radius-md, 10px);
            }

            .error-bar {
                padding: var(--space-2) var(--space-6);
                color: #fca5a5;
                background: rgba(127, 29, 29, 0.32);
                font-size: var(--text-xs);
                text-align: center;
            }

            .center-state {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                color: rgba(255, 255, 255, 0.7);
            }

            .local-share-pip {
                position: absolute;
                top: var(--space-4);
                right: var(--space-4);
                z-index: 120;
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
                width: min(200px, 38vw);
                padding: var(--space-2);
                border-radius: var(--radius-lg, 12px);
                background: rgba(12, 12, 18, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.2);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
                pointer-events: auto;
            }
            .local-share-pip video {
                width: 100%;
                aspect-ratio: 16 / 9;
                border-radius: var(--radius-md, 8px);
                background: #111;
                object-fit: cover;
                display: block;
            }
            .local-share-pip-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                justify-content: flex-end;
            }
            .local-share-pip-actions button {
                min-width: 36px;
                height: 36px;
                padding: 0 8px;
                border-radius: var(--radius-md, 8px);
                border: none;
                background: rgba(255, 255, 255, 0.14);
                color: #fff;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            .local-share-pip-actions button:hover {
                background: rgba(255, 255, 255, 0.24);
            }
            .local-share-pip-restore {
                position: absolute;
                top: var(--space-4);
                right: var(--space-4);
                z-index: 119;
                padding: 8px 12px;
                border-radius: var(--radius-md, 999px);
                border: 1px solid rgba(255, 255, 255, 0.22);
                background: rgba(12, 12, 18, 0.88);
                color: rgba(255, 255, 255, 0.92);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .local-share-pip-restore:hover {
                background: rgba(30, 30, 40, 0.95);
            }
            .local-share-pip--controls-only {
                width: auto;
                min-width: min(200px, 38vw);
            }
            .local-share-pip--controls-only .local-share-pip-actions {
                justify-content: center;
            }

            @media (max-width: 640px) {
                .chat-panel {
                    top: auto;
                    left: var(--space-2);
                    right: var(--space-2);
                    bottom: 80px;
                    width: auto;
                    max-height: min(60vh, 420px);
                }
                .controls { grid-template-columns: 1fr; }
                .slot-left, .slot-right { justify-content: center; }
            }

            .controls--compact {
                padding: var(--space-2) var(--space-3) var(--space-3);
                gap: var(--space-2);
            }
            .controls--compact .slot-center {
                gap: var(--space-2);
                flex-wrap: wrap;
                justify-content: center;
            }
            .controls--compact .ctrl:not(.hangup) {
                width: 48px;
                height: 48px;
            }
            .controls--compact .ctrl.hangup {
                width: 54px;
                height: 54px;
            }
            .menu-row-btn {
                display: flex;
                align-items: center;
                gap: 10px;
                width: 100%;
                margin: 0 0 var(--space-2);
                padding: 10px 12px;
                border: none;
                border-radius: var(--radius-md, 10px);
                background: rgba(255, 255, 255, 0.08);
                color: #fff;
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .menu-row-btn:hover {
                background: rgba(255, 255, 255, 0.14);
            }
            .menu-row-btn[disabled] {
                opacity: 0.4;
                cursor: not-allowed;
            }
            .menu-row-btn.recording-active {
                background: rgba(239, 68, 68, 0.35);
            }
            .menu-row-btn span {
                flex: 1;
                min-width: 0;
            }
            .menu-devices-inline {
                margin: 0 0 var(--space-3);
                padding: 0 4px var(--space-2);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
        `,
    ];

    constructor() {
        super();
        this.callId = '';
        this.callType = 'video';
        this.channelId = '';
        this.livekitToken = '';
        this.livekitUrl = '';
        this.participantNames = null;
        this.participantIdentity = '';
        this._connecting = true;
        this._status = 'connecting';
        this._error = null;
        this._tiles = [];
        this._participantsCount = 0;
        this._duration = 0;
        this._micMuted = false;
        this._camOff = false;
        this._screenOn = false;
        this._devicesMenuOpen = false;
        this._moreMenuOpen = false;
        this._controlsCompact = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
            ? window.matchMedia('(max-width: 640px)').matches
            : false;
        this._audioQualitySubOpen = false;
        this._participantMenuParticipantIdentity = null;
        this._deviceLists = { audioinput: [], videoinput: [], audiooutput: [] };
        this._audioOutputSupported = typeof HTMLMediaElement !== 'undefined'
            && 'setSinkId' in HTMLMediaElement.prototype;
        this._fullscreenTileKey = null;
        this._copyLinkFeedback = false;
        this._chatInput = '';
        this._chatSending = false;
        this._sharePipDismissed = false;
        /** Окно Document Picture-in-Picture (всегда поверх; видно при другой вкладке / не-браузерном шаринге). */
        this._pipDocWindowRef = null;
        /** `<video>` внутри окна Document PiP; если задано — дублирующая панель в оверлее не показывается. */
        this._pipDocVideoEl = null;

        this._room = null;
        this._lk = null;
        this._durationTimer = null;
        this._copyLinkTimer = null;
        this._minimizeDeferTimer = null;
        /** После тапа «свернуть» игнорировать сброс, пока не закончится жест (ложный hit на трубку). */
        this._suppressHangupUntil = 0;
        this._cameraEnabledBeforeScreenShare = true;
        this._roomDisconnecting = false;
        this._roomConnectRequestId = 0;

        this._tokenOp = this.useOp('sync/call_token');
        this._statusOp = this.useOp('sync/call_status');
        this._hangupOp = this.useOp('sync/calls_hangup');
        this._recordingStartOp = this.useOp('sync/calls_recording_start');
        this._recordingStopOp = this.useOp('sync/calls_recording_stop');
        this._adminTransferOp = this.useOp('sync/calls_admin_transfer');
        this._linkCreateOp = this.useOp('sync/call_link_create');
        this._sendMessageOp = this.useOp('sync/messages_send');
        this._loadOlderOp = this.useOp('sync/messages_load_older');

        this._callUi = this.useSlice('sync/call_ui');
        this._callPrefs = this.useSlice('sync/call_prefs');
        this._messagesStore = this.useSlice('sync/messages_store');

        this._callUiSel = this.select((s) => s.syncCallUi);
        this._prefsSel = this.select((s) => s.syncCallPrefs);
        this._messagesSel = this.select((s) => s.syncMessagesStore);
        this._authUserSel = this.select((s) => s.auth && s.auth.user);
        this._authStatusSel = this.select((s) => (s.auth && typeof s.auth.status === 'string' ? s.auth.status : 'unknown'));

        this.useEvent('sync/call/ended', (event) => this._onCallEnded(event));
        this.useEvent('sync/call/recording_started', (event) => this._onRecordingPush(event, 'recording'));
        this.useEvent('sync/call/recording_stopped', (event) => this._onRecordingPush(event, 'idle'));
        this.useEvent('sync/call/recording_failed', (event) => this._onRecordingPush(event, 'failed'));

        this._onFullscreenChange = this._onFullscreenChange.bind(this);
        this._onDocumentPointerDown = this._onDocumentPointerDown.bind(this);
        this._onDocumentKeydown = this._onDocumentKeydown.bind(this);
        this._onPipDocPageHide = this._onPipDocPageHide.bind(this);
        this._onMediaSessionEnterPip = this._onMediaSessionEnterPip.bind(this);
        /**
         * Сворачивание: клик по шапке иногда не доходит до @click (портал в body, перехват).
         * На capture фазе на хосте проверяем composedPath и обрабатываем до всплытия.
         * Без preventDefault: иначе на мобильных ломается цепочка pointerup/click после скрытия хоста.
         */
        this._onHostMinimizePointerCapture = (e) => {
            const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
            const hit = path.find((n) => n instanceof HTMLElement && n.hasAttribute('data-call-minimize'));
            if (!hit) return;
            e.stopPropagation();
            this._onMinimize(e);
        };
    }

    _sharePipRequestOptions() {
        return {
            width: 280,
            height: 260,
            copyStyleSheets: true,
        };
    }

    _onPipDocPageHide(ev) {
        if (this._pipDocWindowRef === null || ev.currentTarget !== this._pipDocWindowRef) {
            return;
        }
        this._pipDocWindowRef.removeEventListener('pagehide', this._onPipDocPageHide);
        this._pipDocWindowRef = null;
        this._pipDocVideoEl = null;
        this.requestUpdate();
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('pointerdown', this._onHostMinimizePointerCapture, true);
        document.addEventListener('fullscreenchange', this._onFullscreenChange);
        document.addEventListener('webkitfullscreenchange', this._onFullscreenChange);
        document.addEventListener('pointerdown', this._onDocumentPointerDown, true);
        document.addEventListener('keydown', this._onDocumentKeydown, true);
        this._durationTimer = window.setInterval(() => { this._duration += 1; }, 1000);
        this._mqlCompact = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
            ? window.matchMedia('(max-width: 640px)')
            : null;
        if (this._mqlCompact) {
            this._onMqlCompactChange = () => {
                this._controlsCompact = this._mqlCompact.matches;
            };
            this._controlsCompact = this._mqlCompact.matches;
            this._mqlCompact.addEventListener('change', this._onMqlCompactChange);
        }
    }

    disconnectedCallback() {
        this.removeEventListener('pointerdown', this._onHostMinimizePointerCapture, true);
        document.removeEventListener('fullscreenchange', this._onFullscreenChange);
        document.removeEventListener('webkitfullscreenchange', this._onFullscreenChange);
        document.removeEventListener('pointerdown', this._onDocumentPointerDown, true);
        document.removeEventListener('keydown', this._onDocumentKeydown, true);
        if (this._durationTimer !== null) {
            window.clearInterval(this._durationTimer);
            this._durationTimer = null;
        }
        if (this._copyLinkTimer !== null) {
            window.clearTimeout(this._copyLinkTimer);
            this._copyLinkTimer = null;
        }
        if (this._minimizeDeferTimer !== null) {
            window.clearTimeout(this._minimizeDeferTimer);
            this._minimizeDeferTimer = null;
        }
        if (this._mqlCompact && this._onMqlCompactChange) {
            this._mqlCompact.removeEventListener('change', this._onMqlCompactChange);
            this._mqlCompact = null;
            this._onMqlCompactChange = null;
        }
        this._disconnectRoom();
        super.disconnectedCallback();
    }

    async firstUpdated() {
        this._ensureActiveCallUi();
        await this._connectRoom();
    }

    /**
     * Слайс `activeCall` обязан совпадать с открытой модалкой: иначе свёртка
     * (баннер в шапке) не включается. Гостевой join и старые пути могли
     * открыть только модалку без overlay_opened.
     */
    _ensureActiveCallUi() {
        if (!this.callId || typeof this.callId !== 'string' || this.callId === '') return;
        const slice = this._callUiSel.value;
        if (slice && slice.activeCall && slice.activeCall.call_id === this.callId) return;
        const channelId = typeof this.channelId === 'string' ? this.channelId : '';
        const callType = typeof this.callType === 'string' && this.callType !== '' ? this.callType : 'video';
        this._callUi.openOverlay({
            call_id: this.callId,
            channel_id: channelId,
            call_type: callType,
            livekit_room_name: null,
            livekit_url: null,
        });
    }

    /**
     * Токен и URL из гостевого join_accept; иначе запрос sync/call_token (участник с сессией).
     */
    _prefetchedLiveKitBundle() {
        const tk = typeof this.livekitToken === 'string' ? this.livekitToken : '';
        const url = typeof this.livekitUrl === 'string' ? this.livekitUrl : '';
        if (tk === '' || url === '') return null;
        const raw = this.participantNames;
        const participant_names =
            raw !== null && raw !== undefined && typeof raw === 'object' ? raw : {};
        return { token: tk, livekit_url: url, participant_names };
    }

    async _connectRoom() {
        if (!this.callId) return;
        const connectRequestId = ++this._roomConnectRequestId;
        this._roomDisconnecting = false;
        try {
            let tokenResult = this._prefetchedLiveKitBundle();
            if (tokenResult === null) {
                try {
                    await this._tokenOp.run({ call_id: this.callId });
                } catch (err) {
                    if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
                    this._status = 'error';
                    this._error = err && typeof err.message === 'string' ? err.message : this.t('call_overlay.err_token_failed');
                    this._connecting = false;
                    return;
                }
                tokenResult = this._tokenOp.lastResult;
            }
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            if (!tokenResult || typeof tokenResult.token !== 'string' || typeof tokenResult.livekit_url !== 'string') {
                if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
                this._status = 'error';
                this._error = this.t('call_overlay.err_livekit_required');
                this._connecting = false;
                return;
            }
            const lk = await import('@livekit/client');
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            this._lk = lk;
            const room = new lk.Room({
                adaptiveStream: true,
                dynacast: true,
                publishDefaults: lk.ScreenSharePresets
                    ? { screenShareEncoding: lk.ScreenSharePresets.h1080fps30.encoding }
                    : undefined,
            });
            this._room = room;
            const ev = lk.RoomEvent;
            room.on(ev.ParticipantConnected, () => this._syncParticipants());
            room.on(ev.ParticipantDisconnected, () => this._syncParticipants());
            room.on(ev.TrackSubscribed, () => this._syncParticipants());
            room.on(ev.TrackUnsubscribed, () => this._syncParticipants());
            room.on(ev.LocalTrackPublished, () => this._syncParticipants());
            room.on(ev.LocalTrackUnpublished, () => this._syncParticipants());
            room.on(ev.Disconnected, () => this._onRoomDisconnected());

            await room.connect(tokenResult.livekit_url, tokenResult.token);
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            if (_canUseMediaDevices()) {
                await room.localParticipant.enableCameraAndMicrophone();
                if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
                const prefs = this._prefsSel.value;
                const wantCamera = this.callType === 'audio' ? false : (prefs ? prefs.cameraEnabled !== false : true);
                await room.localParticipant.setCameraEnabled(wantCamera);
                if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
                this._camOff = !wantCamera;
                this._micMuted = false;
            } else {
                if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
                this.toast('composer.voice_insecure_context', { type: 'warning' });
                this._camOff = true;
                this._micMuted = true;
            }
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            this._status = 'active';
            this._connecting = false;
            await this._loadDeviceLists();
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            this._syncParticipants();
            try {
                await this._statusOp.run({ call_id: this.callId });
            } catch (_err) {
                // не критично — без admin-меню overlay работает.
            }
        } catch (err) {
            if (connectRequestId !== this._roomConnectRequestId || this._roomDisconnecting) return;
            this._status = 'error';
            this._error = err && typeof err.message === 'string' ? err.message : this.t('call_overlay.err_connect_failed');
            this._connecting = false;
            this._disconnectRoom();
        }
    }

    _disconnectRoom() {
        this._unregisterSharePipMediaSession();
        this._removePipFallbackVideo();
        this._closeSharePipDocumentWindow();
        if (this._room) {
            this._roomDisconnecting = true;
            this._roomConnectRequestId += 1;
            try { this._room.removeAllListeners?.(); } catch (_err) { /* noop */ }
            try { this._room.disconnect(); } catch (_err) { /* noop */ }
            this._room = null;
            this._roomDisconnecting = false;
        }
        this._lk = null;
        this._tiles = [];
        this._participantsCount = 0;
    }

    _onRoomDisconnected() {
        if (this._status === 'ended' || this._status === 'error') return;
        this._status = 'ended';
        this._callUi.closeOverlay(null);
        super.close();
    }

    async _loadDeviceLists() {
        if (!navigator.mediaDevices || typeof navigator.mediaDevices.enumerateDevices !== 'function') {
            this._deviceLists = { audioinput: [], videoinput: [], audiooutput: [] };
            return;
        }
        const all = await navigator.mediaDevices.enumerateDevices();
        const lists = { audioinput: [], videoinput: [], audiooutput: [] };
        for (const d of all) {
            if (d.kind === 'audioinput' || d.kind === 'videoinput' || d.kind === 'audiooutput') {
                lists[d.kind].push({ deviceId: d.deviceId, label: d.label || '' });
            }
        }
        this._deviceLists = lists;
    }

    _allMediaInputsEmpty() {
        if (!_canUseMediaDevices()) return false;
        const l = this._deviceLists;
        return l.audioinput.length === 0 && l.videoinput.length === 0;
    }

    _syncParticipants() {
        if (!this._room || !this._lk) return;
        const Track = this._lk.Track;
        const tiles = [];
        const me = this._room.localParticipant;
        const localPubs = Array.from(me.videoTrackPublications.values()).filter((p) => p.track);
        const localScreen = localPubs.find((p) => p.source === Track.Source.ScreenShare);
        const localCam = localPubs.find((p) => p.source !== Track.Source.ScreenShare);
        if (localScreen) {
            tiles.push({ key: 'local-screen', participantIdentity: me.identity, isLocal: true, track: localScreen.track, isScreen: true });
        } else if (localCam) {
            tiles.push({ key: 'local-cam', participantIdentity: me.identity, isLocal: true, track: localCam.track, isScreen: false });
        } else {
            tiles.push({ key: 'local-ph', participantIdentity: me.identity, isLocal: true, track: null, isScreen: false });
        }
        for (const remote of this._room.remoteParticipants.values()) {
            const pubs = Array.from(remote.videoTrackPublications.values()).filter((p) => p.track && p.isSubscribed);
            const screen = pubs.find((p) => p.source === Track.Source.ScreenShare);
            if (screen) {
                tiles.push({ key: `r-${remote.identity}-screen`, participantIdentity: remote.identity, isLocal: false, track: screen.track, isScreen: true });
            } else {
                const cam = pubs[0] || null;
                tiles.push({
                    key: cam ? `r-${remote.identity}-cam` : `r-${remote.identity}-ph`,
                    participantIdentity: remote.identity,
                    isLocal: false,
                    track: cam ? cam.track : null,
                    isScreen: false,
                });
            }
        }
        this._tiles = tiles;
        this._participantsCount = 1 + this._room.remoteParticipants.size;
        this._screenOn = me.isScreenShareEnabled === true;
    }

    /**
     * После render: атрибут `data-minimized` из `overlayMinimized`, затем привязка треков LiveKit к `<video>`.
     */
    updated(changedProps) {
        super.updated(changedProps);
        const sliceState = this._callUiSel.value;
        const minimized = !!(sliceState && sliceState.overlayMinimized === true);
        if (minimized) {
            this.setAttribute('data-minimized', '');
        } else {
            this.removeAttribute('data-minimized');
        }
        // Attach LiveKit tracks к видеоэлементам после Lit-render.
        if (!this._room || !this._lk) return;
        const tileEls = this.renderRoot.querySelectorAll('.tile');
        this._tiles.forEach((tile, i) => {
            const el = tileEls[i];
            if (!el) return;
            const videoEl = el.querySelector('video');
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
        // Audio tracks remote — attach глобально.
        this._room.remoteParticipants.forEach((p) => {
            for (const pub of p.audioTrackPublications.values()) {
                if (pub.isSubscribed && pub.track && !pub.track._lkAttached) {
                    pub.track.attach();
                    pub.track._lkAttached = true;
                }
            }
        });
        this._attachLocalSharePipVideo();
    }

    _onDocumentPointerDown(e) {
        if (!this._devicesMenuOpen && !this._moreMenuOpen && this._participantMenuParticipantIdentity == null) return;
        const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
        const insideMenu = path.some((n) => n instanceof Element && (
            n.classList?.contains('menu')
            || n.classList?.contains('tile-action-menu')
            || (n.classList?.contains('ctrl') && n.closest('.controls'))
        ));
        if (insideMenu) return;
        this._closeMenus();
    }

    _onDocumentKeydown(e) {
        if (e.key === 'Escape') {
            if (this._devicesMenuOpen || this._moreMenuOpen || this._participantMenuParticipantIdentity != null) {
                this._closeMenus();
                e.stopPropagation();
            }
        }
    }

    _closeMenus() {
        this._devicesMenuOpen = false;
        this._moreMenuOpen = false;
        this._audioQualitySubOpen = false;
        this._participantMenuParticipantIdentity = null;
    }

    _onFullscreenChange() {
        if (!document.fullscreenElement && !document.webkitFullscreenElement) {
            this._fullscreenTileKey = null;
        }
    }

    _toggleTileFullscreen(tileKey, ev) {
        ev.stopPropagation();
        const tileEls = this.renderRoot.querySelectorAll('.tile');
        const idx = this._tiles.findIndex((t) => t.key === tileKey);
        if (idx === -1) return;
        const el = tileEls[idx];
        if (!el) return;
        if (this._fullscreenTileKey === tileKey) {
            if (document.exitFullscreen) document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
            this._fullscreenTileKey = null;
            return;
        }
        if (el.requestFullscreen) el.requestFullscreen();
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
        this._fullscreenTileKey = tileKey;
    }

    async _toggleMic() {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        this._micMuted = !this._micMuted;
        await this._room.localParticipant.setMicrophoneEnabled(!this._micMuted);
    }

    async _toggleCam() {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        this._camOff = !this._camOff;
        await this._room.localParticipant.setCameraEnabled(!this._camOff);
        this._callPrefs.setCamera({ value: !this._camOff });
    }

    _documentPipSupported() {
        return typeof window !== 'undefined'
            && window.documentPictureInPicture !== null
            && window.documentPictureInPicture !== undefined
            && typeof window.documentPictureInPicture.requestWindow === 'function';
    }

    _closeSharePipDocumentWindow() {
        if (this._pipDocWindowRef !== null) {
            try {
                this._pipDocWindowRef.removeEventListener('pagehide', this._onPipDocPageHide);
            } catch (_e) {
                /* noop */
            }
            try {
                this._pipDocWindowRef.close();
            } catch (_e) {
                /* noop */
            }
            this._pipDocWindowRef = null;
        }
        this._pipDocVideoEl = null;
    }

    _populateSharePipDocumentWindow(pipWin) {
        if (pipWin === null || pipWin === undefined) {
            return;
        }
        if (this._pipDocWindowRef === pipWin && this._pipDocVideoEl !== null) {
            return;
        }
        if (this._pipDocWindowRef !== null && this._pipDocWindowRef !== pipWin) {
            this._closeSharePipDocumentWindow();
        }
        this._pipDocWindowRef = pipWin;
        pipWin.addEventListener('pagehide', this._onPipDocPageHide);
        const doc = pipWin.document;
        doc.body.style.margin = '0';
        doc.body.style.background = '#0c0c12';
        doc.body.style.color = '#fff';
        doc.body.style.padding = '8px';
        doc.body.style.fontFamily = 'system-ui, sans-serif';
        doc.body.style.boxSizing = 'border-box';
        const wrap = doc.createElement('div');
        wrap.style.display = 'flex';
        wrap.style.flexDirection = 'column';
        wrap.style.gap = '8px';
        const video = doc.createElement('video');
        video.setAttribute('autoplay', '');
        video.setAttribute('playsinline', '');
        video.muted = true;
        video.style.width = '100%';
        video.style.aspectRatio = '16 / 9';
        video.style.borderRadius = '8px';
        video.style.background = '#111';
        video.style.objectFit = 'cover';
        const actions = doc.createElement('div');
        actions.style.display = 'flex';
        actions.style.gap = '6px';
        actions.style.justifyContent = 'flex-end';
        actions.style.flexWrap = 'wrap';
        const btnStop = doc.createElement('button');
        btnStop.type = 'button';
        btnStop.textContent = this.t('call_overlay.share_pip_doc_stop');
        btnStop.style.cssText = 'padding:6px 10px;border-radius:8px;border:none;background:rgba(255,255,255,0.14);color:#fff;cursor:pointer;font-size:12px;';
        btnStop.addEventListener('click', () => {
            void this._toggleScreenShare();
        });
        const btnHide = doc.createElement('button');
        btnHide.type = 'button';
        btnHide.textContent = this.t('call_overlay.share_pip_doc_hide_panel');
        btnHide.style.cssText = 'padding:6px 10px;border-radius:8px;border:none;background:rgba(255,255,255,0.14);color:#fff;cursor:pointer;font-size:12px;';
        btnHide.addEventListener('click', () => {
            this._dismissSharePip();
        });
        actions.appendChild(btnStop);
        actions.appendChild(btnHide);
        wrap.appendChild(video);
        wrap.appendChild(actions);
        doc.body.appendChild(wrap);
        this._pipDocVideoEl = video;
    }

    _registerSharePipMediaSession() {
        if (!('mediaSession' in navigator)) {
            return;
        }
        if (typeof window.MediaMetadata === 'function') {
            try {
                navigator.mediaSession.metadata = new window.MediaMetadata({
                    title: 'Sync',
                    artist: 'Humanitec',
                });
            } catch (_e) {
                /* noop */
            }
        }
        try {
            navigator.mediaSession.setActionHandler('enterpictureinpicture', this._onMediaSessionEnterPip);
        } catch (_e) {
            /* enterpictureinpicture не во всех сборках */
        }
    }

    _unregisterSharePipMediaSession() {
        if (!('mediaSession' in navigator)) {
            return;
        }
        try {
            navigator.mediaSession.setActionHandler('enterpictureinpicture', null);
        } catch (_e) {
            /* noop */
        }
    }

    async _onMediaSessionEnterPip() {
        if (!this._documentPipSupported()) {
            return;
        }
        if (!this._room || this._screenOn !== true) {
            return;
        }
        const pipApi = window.documentPictureInPicture;
        if (pipApi.window) {
            return;
        }
        if (this._pipDocWindowRef !== null) {
            try {
                this._pipDocWindowRef.removeEventListener('pagehide', this._onPipDocPageHide);
            } catch (_e) {
                /* noop */
            }
            this._pipDocWindowRef = null;
            this._pipDocVideoEl = null;
        }
        let pipWin = null;
        try {
            pipWin = await pipApi.requestWindow(this._sharePipRequestOptions());
        } catch (_e) {
            return;
        }
        if (pipWin === null || pipWin === undefined) {
            return;
        }
        this._populateSharePipDocumentWindow(pipWin);
        this.requestUpdate();
        this._attachLocalSharePipVideo();
    }

    _ensurePipFallbackVideo() {
        if (typeof document === 'undefined') {
            return null;
        }
        const existing = document.getElementById('sync-call-media-pip-video');
        if (existing) {
            return existing;
        }
        const v = document.createElement('video');
        v.id = 'sync-call-media-pip-video';
        v.setAttribute('playsinline', '');
        v.setAttribute('autopictureinpicture', '');
        v.muted = true;
        v.autoplay = true;
        v.style.cssText = 'position:fixed;width:2px;height:2px;opacity:0.02;pointer-events:none;left:0;top:0;z-index:0;';
        document.body.appendChild(v);
        return v;
    }

    _removePipFallbackVideo() {
        const v = typeof document !== 'undefined' ? document.getElementById('sync-call-media-pip-video') : null;
        if (v !== null && v.parentNode) {
            v.srcObject = null;
            v.parentNode.removeChild(v);
        }
    }

    async _toggleScreenShare() {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        const lp = this._room.localParticipant;
        const next = !lp.isScreenShareEnabled;
        const callTypeResolved = typeof this.callType === 'string' && this.callType !== '' ? this.callType : 'video';
        try {
            if (next) {
                this._cameraEnabledBeforeScreenShare = lp.isCameraEnabled;
                this._sharePipDismissed = false;
                const screenOpts = {
                    selfBrowserSurface: 'exclude',
                    surfaceSwitching: 'include',
                };
                await lp.setScreenShareEnabled(true, screenOpts);
                if (callTypeResolved !== 'audio' && this._documentPipSupported()) {
                    this._registerSharePipMediaSession();
                    const pipApi = window.documentPictureInPicture;
                    if (pipApi.window) {
                        try {
                            pipApi.window.close();
                        } catch (_e) {
                            /* noop */
                        }
                    }
                    let pipWin = null;
                    try {
                        pipWin = await pipApi.requestWindow(this._sharePipRequestOptions());
                    } catch (_e) {
                        pipWin = null;
                    }
                    if (pipWin !== null) {
                        this._populateSharePipDocumentWindow(pipWin);
                    }
                    this._attachLocalSharePipVideo();
                }
            } else {
                await lp.setScreenShareEnabled(false);
                this._unregisterSharePipMediaSession();
                this._closeSharePipDocumentWindow();
                this._sharePipDismissed = false;
                if (this._cameraEnabledBeforeScreenShare) {
                    await lp.setCameraEnabled(true);
                    this._camOff = false;
                }
            }
        } catch (err) {
            const name = err && err.name;
            if (name === 'NotAllowedError' || name === 'AbortError') return;
            this.toast('call_overlay.toast_screen_failed', { type: 'error' });
        }
    }

    _dismissSharePip() {
        this._sharePipDismissed = true;
        this._closeSharePipDocumentWindow();
    }

    async _restoreSharePip() {
        this._sharePipDismissed = false;
        const callTypeResolved = typeof this.callType === 'string' && this.callType !== '' ? this.callType : 'video';
        if (callTypeResolved !== 'audio' && this._documentPipSupported()) {
            const pipApi = window.documentPictureInPicture;
            if (pipApi.window) {
                try {
                    pipApi.window.close();
                } catch (_e) {
                    /* noop */
                }
            }
            const pipPromise = pipApi.requestWindow(this._sharePipRequestOptions());
            let pipWin = null;
            try {
                pipWin = await pipPromise;
            } catch (_e) {
                pipWin = null;
            }
            if (pipWin !== null) {
                this._populateSharePipDocumentWindow(pipWin);
                this._attachLocalSharePipVideo();
            }
        }
        this.requestUpdate();
    }

    _localCameraTrackForPip() {
        if (!this._room || !this._lk) return null;
        const Track = this._lk.Track;
        const me = this._room.localParticipant;
        for (const pub of me.videoTrackPublications.values()) {
            if (pub.source === Track.Source.Camera && pub.track) {
                return pub.track;
            }
        }
        return null;
    }

    _attachLocalSharePipVideo() {
        if (!this._room || !this._lk) {
            return;
        }
        const camTrack = this._localCameraTrackForPip();
        const fallback = this._ensurePipFallbackVideo();
        if (fallback) {
            if (!camTrack) {
                fallback.srcObject = null;
            } else {
                const fid = camTrack.mediaStreamTrack.id;
                if (fallback._pipTrackId !== fid || !fallback.srcObject) {
                    fallback.srcObject = new MediaStream([camTrack.mediaStreamTrack]);
                    fallback._pipTrackId = fid;
                    this._playPipVideoElement(fallback);
                }
            }
        }
        const pipVideo = this._pipDocVideoEl || this.renderRoot.querySelector('.local-share-pip video');
        if (!pipVideo) {
            return;
        }
        if (!camTrack) {
            pipVideo.srcObject = null;
            return;
        }
        const trackId = camTrack.mediaStreamTrack.id;
        if (pipVideo._pipTrackId === trackId && pipVideo.srcObject) {
            return;
        }
        pipVideo.srcObject = new MediaStream([camTrack.mediaStreamTrack]);
        pipVideo._pipTrackId = trackId;
        this._playPipVideoElement(pipVideo);
    }

    _playPipVideoElement(el) {
        if (!el || typeof el.play !== 'function') {
            return;
        }
        const p = el.play();
        if (p !== undefined && typeof p.catch === 'function') {
            p.catch(() => {});
        }
    }

    _toggleDevicesMenu(e) {
        e.stopPropagation();
        if (!this._controlsCompact) {
            this._moreMenuOpen = false;
        }
        this._participantMenuParticipantIdentity = null;
        this._devicesMenuOpen = !this._devicesMenuOpen;
    }

    _toggleMoreMenu(e) {
        e.stopPropagation();
        if (!this._controlsCompact) {
            this._devicesMenuOpen = false;
        }
        this._participantMenuParticipantIdentity = null;
        this._moreMenuOpen = !this._moreMenuOpen;
        if (!this._moreMenuOpen) {
            this._audioQualitySubOpen = false;
            if (this._controlsCompact) {
                this._devicesMenuOpen = false;
            }
        }
    }

    _toggleAudioQualitySub(e) {
        e.stopPropagation();
        this._audioQualitySubOpen = !this._audioQualitySubOpen;
    }

    _toggleParticipantMenu(participantIdentity, e) {
        e.stopPropagation();
        this._participantMenuParticipantIdentity = this._participantMenuParticipantIdentity === participantIdentity
            ? null
            : participantIdentity;
    }

    async _onAudioInputChange(e) {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        const id = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        await this._room.switchActiveDevice('audioinput', id);
        this._callPrefs.setDeviceId({ kind: 'audioinput', id });
    }

    async _onVideoInputChange(e) {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        const id = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        await this._room.switchActiveDevice('videoinput', id);
        this._callPrefs.setDeviceId({ kind: 'videoinput', id });
    }

    async _onAudioOutputChange(e) {
        if (!this._room) return;
        const id = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        await this._room.switchActiveDevice('audiooutput', id);
        this._callPrefs.setDeviceId({ kind: 'audiooutput', id });
    }

    async _setNoiseSuppression(value) {
        this._callPrefs.setNoiseSuppression({ value });
        await this._reapplyAudioCapture();
    }

    async _setEchoCancellation(value) {
        this._callPrefs.setEchoCancellation({ value });
        await this._reapplyAudioCapture();
    }

    async _setAutoGain(value) {
        this._callPrefs.setAutoGain({ value });
        await this._reapplyAudioCapture();
    }

    async _reapplyAudioCapture() {
        if (!this._room) return;
        if (!_canUseMediaDevices()) {
            this.toast('composer.voice_insecure_context', { type: 'warning' });
            return;
        }
        const prefs = this._prefsSel.value;
        const opts = {
            noiseSuppression: !!prefs.noiseSuppression,
            echoCancellation: !!prefs.echoCancellation,
            autoGainControl: !!prefs.autoGainControl,
        };
        const lp = this._room.localParticipant;
        try {
            await lp.setMicrophoneEnabled(false);
            await lp.setMicrophoneEnabled(true, opts);
        } catch (_err) {
            this.toast('call_overlay.toast_audio_settings_failed', { type: 'error' });
        }
    }

    _activeDeviceId(kind) {
        if (!this._room) return '';
        const id = this._room.getActiveDevice(kind);
        return typeof id === 'string' ? id : '';
    }

    /**
     * activeCall из openOverlay часто без created_by_user_id; полный CallRead приходит
     * из sync/call_status после connect — объединяем, иначе админ встречи не определяется и REC недоступен.
     */
    _activeCallFromState() {
        const slice = this._callUiSel.value;
        const status = this._statusOp.lastResult;
        const sliceCall =
            slice && slice.activeCall && slice.activeCall.call_id === this.callId
                ? slice.activeCall
                : null;
        const statusCall =
            status &&
            typeof status.call_id === 'string' &&
            status.call_id === this.callId
                ? status
                : null;
        if (sliceCall && statusCall) {
            return { ...sliceCall, ...statusCall };
        }
        if (statusCall) {
            return statusCall;
        }
        return sliceCall;
    }

    _adminUserId() {
        const call = this._activeCallFromState();
        if (call && typeof call.created_by_user_id === 'string' && call.created_by_user_id !== '') {
            return call.created_by_user_id;
        }
        return null;
    }

    _myUserId() {
        if (typeof this.participantIdentity === 'string' && this.participantIdentity !== '') {
            return this.participantIdentity;
        }
        const me = this._authUserSel.value;
        return me && typeof me.user_id === 'string' ? me.user_id : '';
    }

    _showLoginInCall() {
        return this._authStatusSel.value === 'unauthenticated';
    }

    _onOpenLogin() {
        const path = typeof window !== 'undefined' ? `${window.location.pathname}${window.location.search}` : '';
        this.openModal('auth.login', { returnPath: path });
    }

    _livekitDisplayNames() {
        const pref = this._prefetchedLiveKitBundle();
        if (pref !== null && pref.participant_names && typeof pref.participant_names === 'object') {
            return pref.participant_names;
        }
        const tr = this._tokenOp.lastResult;
        if (tr && tr.participant_names && typeof tr.participant_names === 'object') {
            return tr.participant_names;
        }
        return null;
    }

    _isMeetingAdmin(userId) {
        const adminId = this._adminUserId();
        return typeof userId === 'string' && userId !== '' && userId === adminId;
    }

    _canTransferAdmin() {
        const me = this._myUserId();
        return me !== '' && me === this._adminUserId();
    }

    _canControlRecording() {
        const me = this._myUserId();
        if (me === '') return false;
        const sliceState = this._callUiSel.value;
        const status = sliceState ? sliceState.recordingStatus : 'idle';
        if (status === 'recording') {
            // stop: admin or starter
            const recordings = this._messagesStore && undefined;
            void recordings;
            // backend сейчас не публикует started_by в slice, поэтому позволим админу.
            return this._canTransferAdmin();
        }
        return this._canTransferAdmin();
    }

    async _toggleRecording() {
        if (!this.callId) return;
        const sliceState = this._callUiSel.value;
        const status = sliceState ? sliceState.recordingStatus : 'idle';
        if (!this._canControlRecording()) {
            this.toast('call_overlay.toast_recording_admin_only', { type: 'error' });
            return;
        }
        if (status === 'recording') {
            this._callUi.setRecordingStatus({ status: 'stopping', error: null });
            try {
                await this._recordingStopOp.run({ call_id: this.callId });
            } catch (err) {
                this._callUi.setRecordingStatus({ status: 'recording', error: String(err && err.message ? err.message : err) });
            }
        } else {
            this._callUi.setRecordingStatus({ status: 'starting', error: null });
            try {
                await this._recordingStartOp.run({ call_id: this.callId });
            } catch (err) {
                this._callUi.setRecordingStatus({ status: 'idle', error: String(err && err.message ? err.message : err) });
            }
        }
    }

    _onRecordingPush(event, status) {
        const p = event && event.payload;
        if (!p || p.call_id !== this.callId) return;
        const error = status === 'failed' && typeof p.error === 'string' ? p.error : null;
        this._callUi.setRecordingStatus({ status: status === 'failed' ? 'idle' : status, error });
    }

    async _assignAdmin(participantIdentity, e) {
        e.stopPropagation();
        if (!this.callId || typeof participantIdentity !== 'string' || participantIdentity === '') return;
        await this._adminTransferOp.run({ call_id: this.callId, target_user_id: participantIdentity });
        if (this._adminTransferOp.lastResult === null) {
            const detail = this._adminTransferOp.error;
            this.toast('call_overlay.toast_admin_transfer_failed', {
                type: 'error',
                vars: { detail: typeof detail === 'string' ? detail : '' },
            });
        }
        this._participantMenuParticipantIdentity = null;
    }

    _onMinimize(e) {
        if (e) {
            e.stopPropagation();
        }
        if (this._minimizeDeferTimer !== null) {
            return;
        }
        this._suppressHangupUntil = Date.now() + 450;
        this._minimizeDeferTimer = window.setTimeout(() => {
            this._minimizeDeferTimer = null;
            this._ensureActiveCallUi();
            this._callUi.minimizeOverlay({
                banner_hangup_guard_until: Date.now() + 750,
            });
        }, 0);
    }

    async _onHangup() {
        if (Date.now() < this._suppressHangupUntil) {
            return;
        }
        if (!this.callId) return;
        try {
            await this._hangupOp.run({ call_id: this.callId });
        } catch (_err) { /* noop */ }
        this._disconnectRoom();
        this._callUi.closeOverlay(null);
        super.close();
    }

    _onCallEnded(event) {
        const p = event && event.payload;
        if (!p || p.call_id !== this.callId) return;
        this._disconnectRoom();
        this._callUi.closeOverlay(null);
        super.close();
    }

    async _copyLink() {
        if (!this.callId || !this.channelId) return;
        try {
            await this._linkCreateOp.run({
                channel_id: this.channelId,
                call_type: 'video',
                call_id: this.callId,
            });
        } catch (_err) {
            this.toast('call_overlay.toast_copy_link_failed', { type: 'error' });
            return;
        }
        const link = this._linkCreateOp.lastResult;
        const url = link && typeof link.join_url === 'string' ? link.join_url : '';
        if (url === '') {
            this.toast('call_overlay.toast_copy_link_failed', { type: 'error' });
            return;
        }
        this.copyToClipboard(url, {
            success_i18n_key: 'sync:call_overlay.toast_link_copied',
            error_i18n_key: 'sync:call_overlay.toast_copy_link_failed',
        });
        this._copyLinkFeedback = true;
        if (this._copyLinkTimer !== null) window.clearTimeout(this._copyLinkTimer);
        this._copyLinkTimer = window.setTimeout(() => {
            this._copyLinkFeedback = false;
            this._copyLinkTimer = null;
        }, COPY_LINK_FEEDBACK_MS);
    }

    _toggleChatPanel() {
        const slice = this._callUiSel.value;
        const open = !(slice && slice.overlayChatOpen === true);
        this._callUi.setOverlayChatOpen({ open });
    }

    _chatMessages() {
        if (!this.channelId) return [];
        const slice = this._messagesSel.value;
        if (!slice || !slice.byChannelId) return [];
        const channelData = slice.byChannelId[this.channelId];
        if (!channelData || !Array.isArray(channelData.items)) return [];
        return channelData.items;
    }

    async _onChatScroll(e) {
        if (!this.channelId) return;
        if (e.target.scrollTop > SCROLL_TOP_THRESHOLD) return;
        const slice = this._messagesSel.value;
        const channelData = slice && slice.byChannelId && slice.byChannelId[this.channelId];
        if (!channelData || !channelData.pagination || channelData.pagination.hasOlder !== true) return;
        if (channelData.loadingOlder) return;
        const oldest = channelData.pagination.oldestCursor;
        if (typeof oldest !== 'string' || oldest === '') return;
        this._messagesStore.startOlder({ channelId: this.channelId });
        try {
            await this._loadOlderOp.run({
                channel_id: this.channelId,
                limit: 30,
                before: oldest,
                direction: 'older',
            });
            const result = this._loadOlderOp.lastResult;
            if (!result || !Array.isArray(result.items)) return;
            const hasOlder = typeof result.has_older === 'boolean'
                ? result.has_older
                : (typeof result.prev_cursor === 'string' && result.prev_cursor !== '');
            const oldestCursorNext = typeof result.oldest_cursor === 'string'
                ? result.oldest_cursor
                : (typeof result.prev_cursor === 'string' ? result.prev_cursor : null);
            this._messagesStore.loadedOlder({
                channelId: this.channelId,
                items: result.items,
                hasOlder,
                oldestCursor: oldestCursorNext,
            });
        } catch (_err) { /* noop */ }
    }

    async _sendChatMessage() {
        const text = this._chatInput.trim();
        if (text === '' || !this.channelId) return;
        const localId = `local_${Date.now().toString(36)}_${Math.floor(Math.random() * 0xffffff).toString(36)}`;
        const me = this._authUserSel.value;
        this._chatSending = true;
        this._messagesStore.addOptimistic({
            channelId: this.channelId,
            item: {
                local_id: localId,
                message_id: localId,
                channel_id: this.channelId,
                contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
                sender: me ? { user_id: me.user_id, display_name: me.name } : null,
                sent_at: new Date().toISOString(),
                status: 'sending',
            },
        });
        try {
            await this._sendMessageOp.run({
                channel_id: this.channelId,
                body: {
                    contents: [{ type: 'text/plain', data: { body: text }, order: 0 }],
                    local_id: localId,
                },
            });
            this._chatInput = '';
        } catch (err) {
            this._messagesStore.failOptimistic({
                channelId: this.channelId,
                localId,
                message: err && typeof err.message === 'string' ? err.message : 'failed',
            });
        }
        this._chatSending = false;
    }

    _onChatKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            void this._sendChatMessage();
        }
    }

    _formatDuration(sec) {
        return formatDurationSeconds(sec);
    }

    _resolveDisplayName(participantIdentity) {
        if (typeof participantIdentity !== 'string' || participantIdentity === '') return '?';
        const names = this._livekitDisplayNames();
        if (names && typeof names[participantIdentity] === 'string') return names[participantIdentity];
        if (participantIdentity.startsWith('guest:')) {
            const parts = participantIdentity.split(':');
            return parts.slice(2).join(':') || this.t('call_overlay.guest');
        }
        return participantIdentity;
    }

    _renderTile(tile, idx) {
        const display = tile.isLocal ? this.t('call_overlay.you') : this._resolveDisplayName(tile.participantIdentity);
        const label = tile.isScreen ? this.t('call_overlay.screen_tile_suffix', { label: display }) : display;
        const tileClass = tile.isScreen ? 'tile screen' : 'tile';
        const isAdmin = this._isMeetingAdmin(tile.participantIdentity);
        const showActions = this._canTransferAdmin() && !tile.isLocal && !tile.isScreen;
        const menuOpen = this._participantMenuParticipantIdentity === tile.participantIdentity;
        const fsActive = this._fullscreenTileKey === tile.key;
        const hueVar = syncAvatarHueVar(tile.participantIdentity || `tile-${idx}`);
        return html`
            <div class="${tileClass}" data-idx=${idx} data-tile-key=${tile.key}>
                ${showActions ? html`
                    <button
                        class="tile-btn tile-actions"
                        title=${this.t('call_overlay.participant_menu')}
                        @click=${(e) => this._toggleParticipantMenu(tile.participantIdentity, e)}
                    ><platform-icon name="more-vertical" size="16"></platform-icon></button>
                    ${menuOpen ? html`
                        <div class="tile-action-menu" @click=${(e) => e.stopPropagation()}>
                            ${isAdmin ? html`
                                <div style="padding:8px 10px;color:rgba(255,255,255,0.55);font-size:var(--text-xs);">
                                    ${this.t('call_overlay.participant_action_unavailable')}
                                </div>
                            ` : html`
                                <button @click=${(e) => this._assignAdmin(tile.participantIdentity, e)}>
                                    ${this.t('call_overlay.promote_meeting_admin')}
                                </button>
                            `}
                        </div>
                    ` : ''}
                ` : ''}
                ${tile.track
                    ? html`<video autoplay playsinline ?muted=${tile.isLocal}></video>`
                    : html`<div class="avatar pastel-initials" style=${hueVar}>${initialsFromName(display)}</div>`}
                <span class="name">
                    ${isAdmin ? html`<span class="crown" title=${this.t('call_overlay.meeting_admin')}><platform-icon name="zap" size="12"></platform-icon></span>` : ''}
                    ${label}
                </span>
                ${tile.track ? html`
                    <button
                        class="tile-btn tile-fs ${fsActive ? 'active' : ''}"
                        title=${fsActive ? this.t('call_overlay.fullscreen_exit') : this.t('call_overlay.fullscreen_enter')}
                        @click=${(e) => this._toggleTileFullscreen(tile.key, e)}
                    ><platform-icon name=${fsActive ? 'minimize' : 'expand'} size="16"></platform-icon></button>
                ` : ''}
            </div>
        `;
    }

    _renderHeader() {
        const sliceState = this._callUiSel.value;
        const recordingStatus = sliceState ? sliceState.recordingStatus : 'idle';
        const showRec = recordingStatus === 'recording' || recordingStatus === 'starting' || recordingStatus === 'stopping';
        return html`
            <div class="header">
                <div class="header-left">
                    ${this._status === 'active' ? html`<span class="status-dot"></span>` : ''}
                    <span>${this._status === 'connecting' ? this.t('call_overlay.connecting') : this._formatDuration(this._duration)}</span>
                </div>
                <div class="header-right">
                    ${showRec ? html`
                        <span class="recording-badge">
                            ${recordingStatus === 'recording' ? html`<span class="recording-dot"></span>` : ''}
                            REC
                        </span>
                    ` : ''}
                    <span style="opacity:0.6;">
                        ${this.t('call_overlay.participants_abbr', { n: this._participantsCount })}
                    </span>
                    ${this._showLoginInCall() ? html`
                        <button
                            type="button"
                            class="ctrl login-in-call"
                            title=${this.t('call_overlay.login_account_title')}
                            @click=${() => this._onOpenLogin()}
                        >${this.t('call_overlay.login_account')}</button>
                    ` : ''}
                    ${this.callId ? html`
                        <button type="button" class="ctrl header-icon-btn" title=${this.t('call_overlay.copy_link_title')} @click=${this._copyLink}>
                            ${this._copyLinkFeedback
                                ? html`<platform-icon name="check" size="16"></platform-icon>`
                                : html`<platform-icon name="copy" size="16"></platform-icon>`}
                        </button>
                    ` : ''}
                    <button
                        type="button"
                        class="ctrl header-icon-btn"
                        data-call-minimize
                        title=${this.t('call_overlay.minimize_title')}
                        @click=${(e) => this._onMinimize(e)}
                    >
                        <platform-icon name="chevron-down" size="16"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }

    _deviceEnumConfig(listKey) {
        const list = this._deviceLists[listKey];
        if (!Array.isArray(list)) {
            throw new Error(`SyncCallOverlayModal._deviceEnumConfig: invalid list "${listKey}"`);
        }
        if (list.length === 0) {
            return { values: [{ value: '', label: this.t('call_overlay.no_devices') }] };
        }
        const values = [];
        let i = 0;
        for (const d of list) {
            if (!d || typeof d.deviceId !== 'string') {
                throw new Error('SyncCallOverlayModal._deviceEnumConfig: invalid device entry');
            }
            const label = typeof d.label === 'string' && d.label.length > 0
                ? d.label
                : this.t('call_overlay.device_fallback', { n: String(i + 1) });
            values.push({ value: d.deviceId, label });
            i += 1;
        }
        return { values };
    }

    _renderDevicesMenuFields() {
        return html`
            ${_canUseMediaDevices()
                ? (this._allMediaInputsEmpty()
                    ? html`<p class="menu-hint">${this.t('call_overlay.media_devices_empty_hint')}</p>`
                    : '')
                : html`<p class="menu-hint">${this.t('call_overlay.media_devices_insecure_hint')}</p>`}
            <div class="menu-section-title">${this.t('call_overlay.label_mic')}</div>
            <platform-field
                type="enum"
                mode="edit"
                .value=${this._activeDeviceId('audioinput')}
                .config=${this._deviceEnumConfig('audioinput')}
                @change=${this._onAudioInputChange}
            ></platform-field>
            ${this.callType !== 'audio' ? html`
                <div class="menu-section-title">${this.t('call_overlay.label_camera')}</div>
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${this._activeDeviceId('videoinput')}
                    .config=${this._deviceEnumConfig('videoinput')}
                    @change=${this._onVideoInputChange}
                ></platform-field>
            ` : ''}
            ${this._audioOutputSupported ? html`
                <div class="menu-section-title">${this.t('call_overlay.label_speaker')}</div>
                <platform-field
                    type="enum"
                    mode="edit"
                    .value=${this._activeDeviceId('audiooutput')}
                    .config=${this._deviceEnumConfig('audiooutput')}
                    @change=${this._onAudioOutputChange}
                ></platform-field>
            ` : ''}
        `;
    }

    _renderControls() {
        const prefs = this._prefsSel.value;
        const sliceState = this._callUiSel.value;
        const recordingStatus = sliceState ? sliceState.recordingStatus : 'idle';
        const recordingActive = recordingStatus === 'recording';
        const recordingBusy = recordingStatus === 'starting' || recordingStatus === 'stopping';
        const canRecord = this._canControlRecording();
        const chatOpen = !!(sliceState && sliceState.overlayChatOpen);
        const sfuReady = this._room && this._status === 'active';
        const compact = this._controlsCompact;
        const showDevicesInBar = sfuReady && !compact;
        const showRecordInBar = !compact;
        const recordingMenuLabel = canRecord
            ? (recordingActive ? this.t('call_overlay.recording_stop') : this.t('call_overlay.recording_start_meeting'))
            : (recordingActive ? this.t('call_overlay.recording_tooltip_stop_denied') : this.t('call_overlay.recording_tooltip_start_denied'));
        return html`
            <div class="controls ${compact ? 'controls--compact' : ''}" @click=${(e) => e.stopPropagation()}>
                <div class="slot-left">
                    ${showDevicesInBar ? html`
                        <button class="ctrl" title=${this.t('call_overlay.devices_settings_title')} @click=${this._toggleDevicesMenu}>
                            <platform-icon name="settings" size="22"></platform-icon>
                        </button>
                        ${this._devicesMenuOpen ? html`
                            <div class="menu left" @click=${(e) => e.stopPropagation()}>
                                ${this._renderDevicesMenuFields()}
                            </div>
                        ` : ''}
                    ` : ''}
                </div>

                <div class="slot-center">
                    <button class="ctrl ${this._micMuted ? '' : 'active'}" @click=${this._toggleMic}
                        title=${this._micMuted ? this.t('call_overlay.mic_enable') : this.t('call_overlay.mic_disable')}>
                        <platform-icon name=${this._micMuted ? 'mic-off' : 'mic'} size="22"></platform-icon>
                    </button>
                    <button class="ctrl ${this._camOff ? '' : 'active'}" @click=${this._toggleCam}
                        title=${this._camOff ? this.t('call_overlay.cam_enable') : this.t('call_overlay.cam_disable')}>
                        <platform-icon name=${this._camOff ? 'videocam-off' : 'video'} size="22"></platform-icon>
                    </button>
                    <button class="ctrl ${this._screenOn ? 'active' : ''}" @click=${this._toggleScreenShare}
                        title=${this._screenOn ? this.t('call_overlay.screen_share_stop') : this.t('call_overlay.screen_share_start')}>
                        <platform-icon name="screen-share" size="22"></platform-icon>
                    </button>
                    ${showRecordInBar ? html`
                        <button class="ctrl ${recordingActive ? 'recording-active' : ''}"
                            ?disabled=${!canRecord || recordingBusy}
                            @click=${this._toggleRecording}
                            title=${recordingMenuLabel}>
                            <platform-icon name=${recordingActive ? 'stop' : 'fiber-manual-record'} size="22"></platform-icon>
                        </button>
                    ` : ''}
                    <button class="ctrl hangup" @click=${this._onHangup} title=${this.t('call_overlay.hangup_title')}>
                        <platform-icon name="phone-ended" size="22"></platform-icon>
                    </button>
                </div>

                <div class="slot-right">
                    <button class="ctrl ${chatOpen ? 'chat-active' : ''}" @click=${this._toggleChatPanel}
                        title=${chatOpen ? this.t('call_overlay.chat_hide') : this.t('call_overlay.chat_show')}>
                        <platform-icon name="message-square" size="22"></platform-icon>
                    </button>
                    ${sfuReady ? html`
                        <button class="ctrl" title=${this.t('call_overlay.more_menu')} @click=${this._toggleMoreMenu}>
                            <platform-icon name="more-vertical" size="22"></platform-icon>
                        </button>
                        ${this._moreMenuOpen ? html`
                            <div class="menu right" @click=${(e) => e.stopPropagation()}>
                                ${compact ? html`
                                    <button type="button" class="menu-row-btn" @click=${this._toggleDevicesMenu}>
                                        <platform-icon name="settings" size="18"></platform-icon>
                                        <span>${this.t('call_overlay.devices_settings_title')}</span>
                                    </button>
                                    ${this._devicesMenuOpen ? html`
                                        <div class="menu-devices-inline">
                                            ${this._renderDevicesMenuFields()}
                                        </div>
                                    ` : ''}
                                    <div class="menu-section-title">${this.t('call_overlay.action_record')}</div>
                                    <button
                                        type="button"
                                        class="menu-row-btn ${recordingActive ? 'recording-active' : ''}"
                                        ?disabled=${!canRecord || recordingBusy}
                                        title=${recordingMenuLabel}
                                        @click=${(e) => {
                                            e.stopPropagation();
                                            void this._toggleRecording();
                                        }}
                                    >
                                        <platform-icon name=${recordingActive ? 'stop' : 'fiber-manual-record'} size="18"></platform-icon>
                                        <span>${recordingMenuLabel}</span>
                                    </button>
                                ` : ''}
                                <div class="menu-section-title">${this.t('call_overlay.audio_quality')}</div>
                                <div class="menu-toggle-row">
                                    <span class="menu-toggle-label">${this.t('call_overlay.noise_suppression')}</span>
                                    <platform-switch
                                        size="sm"
                                        .checked=${prefs ? !!prefs.noiseSuppression : true}
                                        @change=${(e) => this._setNoiseSuppression(e.detail.value)}
                                    ></platform-switch>
                                </div>
                                <div class="menu-toggle-row">
                                    <span class="menu-toggle-label">${this.t('call_overlay.echo_cancellation')}</span>
                                    <platform-switch
                                        size="sm"
                                        .checked=${prefs ? !!prefs.echoCancellation : true}
                                        @change=${(e) => this._setEchoCancellation(e.detail.value)}
                                    ></platform-switch>
                                </div>
                                <div class="menu-toggle-row">
                                    <span class="menu-toggle-label">${this.t('call_overlay.auto_gain')}</span>
                                    <platform-switch
                                        size="sm"
                                        .checked=${prefs ? !!prefs.autoGainControl : true}
                                        @change=${(e) => this._setAutoGain(e.detail.value)}
                                    ></platform-switch>
                                </div>
                            </div>
                        ` : ''}
                    ` : ''}
                </div>
            </div>
        `;
    }

    _renderChatPanel() {
        const items = this._chatMessages();
        const me = this._myUserId();
        return html`
            <section class="chat-panel" @click=${(e) => e.stopPropagation()}>
                <div class="chat-header">
                    <span>${this.t('call_overlay.chat_panel_title')}</span>
                    <button class="chat-close" title=${this.t('call_overlay.chat_hide')} @click=${this._toggleChatPanel}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
                <div class="chat-list" @scroll=${this._onChatScroll}>
                    ${items.length === 0 ? html`
                        <div class="chat-empty">${this.t('call_overlay.no_messages_yet')}</div>
                    ` : items.map((m) => {
                        const sender = m.sender || {};
                        const senderName = typeof sender.display_name === 'string' && sender.display_name !== ''
                            ? sender.display_name
                            : (typeof sender.user_id === 'string' ? sender.user_id : this.t('call_overlay.participant_fallback'));
                        const isOwn = typeof sender.user_id === 'string' && sender.user_id === me;
                        const text = (m.contents || [])
                            .filter((c) => c.type === 'text/plain' && c.data && typeof c.data.body === 'string')
                            .map((c) => c.data.body)
                            .join('\n');
                        if (text === '') return nothing;
                        const time = typeof m.sent_at === 'string'
                            ? new Date(m.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                            : '';
                        return html`
                            <article class="chat-item ${isOwn ? 'self' : ''}">
                                <div class="chat-meta">
                                    <span>${senderName}</span>
                                    <span>${time}</span>
                                </div>
                                <p class="chat-text">${text}</p>
                            </article>
                        `;
                    })}
                </div>
                <div class="chat-composer">
                    <textarea
                        class="chat-input"
                        data-canon="composer"
                        .value=${this._chatInput}
                        @input=${(e) => { this._chatInput = e.target.value; }}
                        @keydown=${this._onChatKeydown}
                        placeholder=${this.t('call_overlay.message_placeholder')}
                        rows="1"
                    ></textarea>
                    <button class="chat-send"
                        ?disabled=${this._chatSending || this._chatInput.trim() === ''}
                        @click=${() => void this._sendChatMessage()}>
                        ${this._chatSending ? '…' : this.t('call_overlay.send')}
                    </button>
                </div>
            </section>
        `;
    }

    _renderLocalSharePip() {
        if (this._status !== 'active' || !this._screenOn || this._sharePipDismissed) {
            return nothing;
        }
        if (this.callType === 'audio') {
            return nothing;
        }
        if (this._pipDocVideoEl !== null) {
            return nothing;
        }
        const hasCam = this._localCameraTrackForPip();
        const actions = html`
            <div class="local-share-pip-actions">
                <button
                    type="button"
                    title=${this.t('call_overlay.share_pip_stop_screen')}
                    @click=${(e) => {
                        e.stopPropagation();
                        void this._toggleScreenShare();
                    }}
                ><platform-icon name="screen-share" size="18"></platform-icon></button>
                <button
                    type="button"
                    title=${this.t('call_overlay.share_pip_hide')}
                    @click=${(e) => {
                        e.stopPropagation();
                        this._dismissSharePip();
                    }}
                ><platform-icon name="close" size="18"></platform-icon></button>
            </div>
        `;
        if (!hasCam) {
            return html`
                <div class="local-share-pip local-share-pip--controls-only" @click=${(e) => e.stopPropagation()}>
                    ${actions}
                </div>
            `;
        }
        return html`
            <div class="local-share-pip" @click=${(e) => e.stopPropagation()}>
                <video autoplay playsinline muted></video>
                ${actions}
            </div>
        `;
    }

    _renderSharePipRestore() {
        if (this._status !== 'active' || !this._screenOn || !this._sharePipDismissed) {
            return nothing;
        }
        if (this.callType === 'audio') {
            return nothing;
        }
        return html`
            <button type="button" class="local-share-pip-restore" @click=${(e) => {
                e.stopPropagation();
                void this._restoreSharePip();
            }}>${this.t('call_overlay.share_pip_show')}</button>
        `;
    }

    render() {
        const sliceState = this._callUiSel.value;
        if (this._status === 'error') {
            return html`
                ${this._renderHeader()}
                <div class="center-state">
                    <platform-icon name="alert-circle" size="48"></platform-icon>
                    <div style="font-weight:600;color:#fca5a5;">${this.t('call_overlay.call_error_title')}</div>
                    <div style="opacity:0.65;max-width:380px;text-align:center;">${this._error || ''}</div>
                    <button class="ctrl hangup" @click=${this._onHangup} style="margin-top:var(--space-3);">
                        <platform-icon name="close" size="20"></platform-icon>
                    </button>
                </div>
            `;
        }
        if (this._status === 'ended') {
            return html`<div class="center-state"><platform-icon name="phone-ended" size="48"></platform-icon>
                <div>${this.t('call_overlay.call_ended')}</div></div>`;
        }
        const tiles = this._tiles;
        const gridClass = tiles.length === 1 ? 'one' : tiles.length === 2 ? 'two' : 'many';
        const recError = sliceState && typeof sliceState.recordingError === 'string' ? sliceState.recordingError : '';
        const chatOpen = !!(sliceState && sliceState.overlayChatOpen);
        return html`
            ${this._renderHeader()}
            <div class="stage">
                <div class="video-grid ${gridClass}">
                    ${tiles.map((t, i) => this._renderTile(t, i))}
                </div>
                ${this._renderLocalSharePip()}
                ${this._renderSharePipRestore()}
                ${chatOpen ? this._renderChatPanel() : ''}
            </div>
            ${recError ? html`<div class="error-bar">${recError}</div>` : ''}
            ${this._renderControls()}
        `;
    }
}

customElements.define('sync-call-overlay-modal', SyncCallOverlayModal);
registerModalKind(SyncCallOverlayModal.modalKind, 'sync-call-overlay-modal');
