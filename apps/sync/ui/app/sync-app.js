/**
 * SyncApp — главное приложение Sync Chat
 * Наследует PlatformApp, подключает единый платформенный auth.
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { SyncAPIService } from '../services/sync-api.service.js';
import { SyncWsService } from '../services/sync-ws.service.js';
import { SyncStore } from '../store/sync.store.js';
import { lanePreviewFromMessagePayload } from '../utils/lane-preview.js';
import { hueFromString } from '../utils/sync-hue.js';
import { senderUserId } from '../utils/sender.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/layout/platform-island.js';
import '../features/call-overlay.js';
import '../features/call-incoming.js';

export class SyncApp extends PlatformApp {
    static properties = {
        ...PlatformApp.properties,
        _chat: { state: true },
        _ui: { state: true },
        _activeCall: { state: true },
        _incomingCall: { state: true },
        _activeCallChannels: { state: true },
        _mobileShell: { state: true },
        _meetingsChannelFilter: { state: true },
        _meetingsDateFrom: { state: true },
        _meetingsDateTo: { state: true },
        _meetingDetailsById: { state: true },
        _meetingsDetailsLoadingId: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }

            @media (max-width: 767px) {
                :host {
                    overflow-x: hidden;
                    overflow-y: hidden;
                    overscroll-behavior-y: none;
                }
            }

            /*
             * Активный звонок: iOS WebKit иначе может оставить hit-testing на .main (flex на весь экран)
             * под полноэкранным call-overlay — кнопки оверлея не получают касания.
             * inert снимает интерактив с подложки; overflow: visible снимает обрезку fixed-детей.
             */
            :host([data-call-active]) {
                overflow: visible;
            }

            :host([data-call-active]) .sidebar,
            :host([data-call-active]) .main {
                pointer-events: none;
            }

            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }

            .main {
                flex: 1;
                height: var(--app-vh, 100vh);
                overflow: hidden;
                display: flex;
                min-height: 0;
                padding: var(--space-4);
            }

            platform-island {
                flex: 1;
                min-height: calc(var(--app-vh, 100vh) - 2rem);
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }

            .meetings-overlay {
                position: fixed;
                inset: 0;
                z-index: var(--z-modal, 1000);
                background: rgba(2, 6, 23, 0.52);
                backdrop-filter: blur(6px);
                -webkit-backdrop-filter: blur(6px);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }

            .meetings-modal {
                width: min(1320px, 100%);
                height: min(88vh, 980px);
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-strong);
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            .meetings-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                flex-shrink: 0;
            }

            .meetings-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .meetings-controls {
                display: grid;
                grid-template-columns: minmax(220px, 320px) minmax(160px, 220px) minmax(160px, 220px) auto;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }

            .back-btn {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                padding: 8px 12px;
                cursor: pointer;
                text-decoration: none;
                transition: background var(--duration-fast), border-color var(--duration-fast);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .back-btn:hover {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
            }

            .meetings-select,
            .meetings-date {
                width: 100%;
                min-height: 40px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                padding: 0 var(--space-3);
                outline: none;
            }

            .meetings-select:focus,
            .meetings-date:focus {
                border-color: var(--accent);
            }

            .meetings-body {
                display: grid;
                grid-template-columns: minmax(340px, 460px) minmax(0, 1fr);
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4) var(--space-4);
                min-height: 0;
                flex: 1;
            }

            .meetings-list {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                overflow: auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .meeting-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                cursor: pointer;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                text-align: left;
                color: var(--text-primary);
                transition: border-color var(--duration-fast), background var(--duration-fast);
            }

            .meeting-card:hover {
                border-color: var(--glass-border-medium);
                background: var(--glass-solid-medium);
            }

            .meeting-card.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }

            .meeting-card-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .meeting-channel {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .meeting-channel-badge {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                color: #fff;
                font-size: 11px;
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .meeting-channel-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .meeting-meta {
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .meeting-status {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 72px;
                padding: 2px 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                font-size: 11px;
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }

            .meeting-status.done {
                color: rgb(22, 163, 74);
                border-color: rgba(22, 163, 74, 0.35);
                background: rgba(22, 163, 74, 0.12);
            }

            .meeting-status.pending {
                color: rgb(217, 119, 6);
                border-color: rgba(217, 119, 6, 0.35);
                background: rgba(217, 119, 6, 0.12);
            }

            .meeting-status.failed {
                color: rgb(220, 38, 38);
                border-color: rgba(220, 38, 38, 0.35);
                background: rgba(220, 38, 38, 0.12);
            }

            .meetings-detail {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                overflow: auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .meetings-empty {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                padding: var(--space-2);
            }

            .detail-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2) var(--space-3);
            }

            .detail-label {
                font-size: 11px;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .detail-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .detail-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            @media (max-width: 767px) {
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }

                .main {
                    padding: 0;
                }

                platform-island {
                    min-height: 0;
                }

                .meetings-overlay {
                    padding: var(--space-1);
                }

                .meetings-modal {
                    width: 100%;
                    height: 100%;
                    border-radius: var(--radius-lg);
                }

                .meetings-header {
                    padding: var(--space-2) var(--space-3);
                }

                .meetings-title {
                    font-size: var(--text-base);
                }

                .meetings-controls {
                    grid-template-columns: 1fr;
                    padding: var(--space-2) var(--space-3);
                }

                .meetings-body {
                    grid-template-columns: 1fr;
                    padding: var(--space-2) var(--space-3) var(--space-3);
                }

                .detail-grid {
                    grid-template-columns: 1fr;
                }
            }
        `
    ];

    /** @type {MediaQueryList | null} */
    _mqMobileShell = null;

    /** @type {((e: MediaQueryListEvent) => void) | null} */
    _onMobileShellChange = null;

    _mobileShellMqBound = false;

    constructor() {
        super();
        this._chat = SyncStore.state.chat;
        this._ui = SyncStore.state.ui;
        this._ws = null;
        this._unsubscribe = null;
        this._typingPruneTimer = null;
        this._wsEverConnected = false;
        this._activeCallChannels = {};
        this._meetingsChannelFilter = 'all';
        this._meetingsDateFrom = '';
        this._meetingsDateTo = '';
        this._meetingDetailsById = {};
        this._meetingsDetailsLoadingId = null;
        /** id WS-команд call.hangup — ack тоже содержит CallRead с call_id, без фильтра открыл бы оверлей снова */
        this._callHangupRequestIds = new Set();
        this._mqMobileShell = window.matchMedia('(max-width: 767px)');
        this._mobileShell = this._mqMobileShell.matches;
        this._boundWindowOpenMeetings = () => {
            void this._openMeetingsPanel();
        };
    }

    setupStore() {
        return SyncStore;
    }

    getBaseUrl() {
        return '/sync';
    }

    async initServices() {
        await super.initServices();
        await this.services.registerCore('/sync');
        this.services.register('syncApi', new SyncAPIService('/sync/api/v1'));

        this._unsubscribe = SyncStore.subscribe((state) => {
            this._chat = state.chat;
            this._ui = state.ui;
        });
    }

    async checkAuth() {
        const auth = this.auth;
        const isAuthenticated = await auth.validateToken();
        if (!isAuthenticated) {
            return false;
        }
        return true;
    }

    async connectedCallback() {
        try {
            await super.connectedCallback();

            if (!this._mobileShellMqBound) {
                this._mobileShellMqBound = true;
                this._onMobileShellChange = (e) => {
                    this._mobileShell = e.matches;
                    this.requestUpdate();
                };
                this._mqMobileShell.addEventListener('change', this._onMobileShellChange);
            }

            if (!this._isAuthenticated) return;

            window.addEventListener('sync-open-meetings', this._boundWindowOpenMeetings);

            const syncApi = this.services.get('syncApi');

            await Promise.all([
                SyncStore.loadSpaces(syncApi),
                SyncStore.loadChannels(syncApi),
                SyncStore.loadCompanyMembers(syncApi),
            ]);

            SyncStore.sanitizeChatSelectionAfterLoad();
            const params = new URLSearchParams(window.location.search);
            const channelFromUrl = params.get('channel');
            if (typeof channelFromUrl === 'string' && channelFromUrl !== '') {
                const ch = SyncStore.state.channels.list.find((c) => c.id === channelFromUrl);
                if (ch) {
                    await SyncStore.selectChannelAndLoadMessages(syncApi, ch.space_id, ch.id);
                } else {
                    await this._restoreLastSelection();
                }
            } else {
                await this._restoreLastSelection();
            }
            this._connectWs();
        } catch (err) {
            console.error('[SyncApp] Ошибка инициализации:', err);
            this.redirectToAuth();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        if (this._mobileShellMqBound) {
            this._mobileShellMqBound = false;
            this._mqMobileShell?.removeEventListener('change', this._onMobileShellChange);
        }
        if (this._typingPruneTimer != null) {
            clearInterval(this._typingPruneTimer);
            this._typingPruneTimer = null;
        }
        window.removeEventListener('sync-open-meetings', this._boundWindowOpenMeetings);
        this._unsubscribe?.();
        this._ws?.close();
        this._ws = null;
        this._wsEverConnected = false;
    }

    async _restoreLastSelection() {
        const { selectedChannelId } = SyncStore.state.chat;
        if (!selectedChannelId) return;

        const channel = SyncStore.state.channels.list.find(c => c.id === selectedChannelId);
        if (!channel) {
            SyncStore.selectChannel(null, null);
            return;
        }

        const syncApi = this.services.get('syncApi');
        await SyncStore.selectChannelAndLoadMessages(syncApi, channel.space_id, channel.id);
    }

    /**
     * Сначала realtime-события (есть type), затем ack команд (ok + id без type).
     * Иначе кадры с полями ok/id перехватываются до channel.typing и индикатор не обновляется.
     */
    _handleWsMessage(data) {
        const msg = JSON.parse(data);
        if (msg === null || typeof msg !== 'object' || Array.isArray(msg)) {
            throw new Error('[sync-ws] ожидался JSON-объект.');
        }
        if (typeof msg.type === 'string' && msg.type !== '') {
            this._dispatchRealtimeEvent(msg);
            return;
        }
        if (typeof msg.ok === 'boolean' && typeof msg.id === 'string') {
            if (this._callHangupRequestIds.delete(msg.id)) {
                return;
            }
            if (msg.ok) {
                if (msg.result && msg.result.call_id) {
                    // call.invite вернул CallRead — открываем оверлей у инициатора.
                    // call.hangup тоже возвращает call_id; такие ack снимаются выше по id (_callHangupRequestIds).
                    this._openCallOverlay(msg.result).catch(err => {
                        console.error('[calls] _openCallOverlay failed:', err);
                    });
                } else if (msg.result) {
                    SyncStore.resolvePending(msg.id, msg.result);
                }
            } else {
                SyncStore.failPending(msg.id);
            }
            return;
        }
        throw new Error(`[sync-ws] неизвестный кадр WebSocket: ${JSON.stringify(msg)}`);
    }

    _dispatchRealtimeEvent(msg) {
        const selectedChannelId = SyncStore.state.chat.selectedChannelId;
        let selectedNorm = null;
        if (typeof selectedChannelId === 'string' && selectedChannelId !== '') {
            selectedNorm = SyncStore.normalizeSyncChannelId(selectedChannelId);
        }

        if (msg.type === 'channel.typing') {
            const p = msg.payload;
            if (!p || typeof p.channel_id !== 'string' || p.channel_id === '') return;
            const uid = p.user?.user_id;
            const myId = this.auth?.user?.id;
            if (typeof myId === 'string' && myId !== '' && uid === myId) return;
            SyncStore.applyChannelTyping({
                channel_id: p.channel_id,
                thread_id: p.thread_id ?? null,
                typing: !!p.typing,
                user: p.user,
            });
            return;
        }

        if (msg.type === 'user.presence') {
            const p = msg.payload;
            if (!p || typeof p !== 'object') return;
            const auth = this.auth?.user;
            const companyId = auth?.company_id;
            if (typeof companyId !== 'string' || companyId === '') {
                throw new Error('user.presence: auth.user.company_id обязателен.');
            }
            if (p.company_id !== companyId) return;
            SyncStore.applyUserPresence(p);
            return;
        }

        const p = msg.payload;
        if (!p || typeof p !== 'object') {
            throw new Error(`${msg.type}: payload обязателен.`);
        }

        if (
            msg.type === 'message.created'
            && this._activeCall
            && typeof this._activeCall.channel_id === 'string'
            && this._activeCall.channel_id !== ''
            && typeof p.channel_id === 'string'
        ) {
            const activeCallNorm = SyncStore.normalizeSyncChannelId(this._activeCall.channel_id);
            const payloadNorm = SyncStore.normalizeSyncChannelId(p.channel_id);
            if (activeCallNorm === payloadNorm) {
                SyncStore.upsertCallOverlayMessage(this._activeCall.channel_id, p);
            }
        }

        if (msg.type === 'channel.member_added') {
            const authUser = this.auth?.user;
            const myId = authUser?.id;
            const added = p.added_user_id;
            if (
                typeof myId === 'string'
                && myId !== ''
                && typeof added === 'string'
                && added === myId
            ) {
                const syncApi = this.services.get('syncApi');
                SyncStore.loadChannels(syncApi);
            }
            return;
        }

        if (msg.type === 'space.created') {
            const syncApi = this.services.get('syncApi');
            void SyncStore.loadSpaces(syncApi).then(() => {
                SyncStore.sanitizeChatSelectionAfterLoad();
            });
            return;
        }

        if (msg.type === 'channel.read_updated') {
            const authUser = this.auth?.user;
            const myId = authUser?.id;
            if (typeof myId !== 'string' || myId === '') {
                throw new Error('channel.read_updated: auth.user.id обязателен.');
            }
            if (p.reader_user_id === myId && typeof p.channel_id === 'string') {
                SyncStore.patchChannelFields(p.channel_id, {
                    unread_count: 0,
                    mention_unread_count: 0,
                });
            } else if (
                p.reader_user_id !== myId
                && typeof p.channel_id === 'string'
                && typeof p.read_at === 'string'
            ) {
                SyncStore.setPeerReadAt(p.channel_id, p.read_at);
            }
            return;
        }

        if (msg.type === 'message.created' && selectedNorm && typeof p.channel_id === 'string') {
            const pChNorm = SyncStore.normalizeSyncChannelId(p.channel_id);
            if (pChNorm === selectedNorm) {
                const authUser = this.auth?.user;
                const myId = authUser?.id;
                if (typeof myId !== 'string' || myId === '') {
                    throw new Error('message.created: auth.user.id обязателен.');
                }
                if (senderUserId(p.sender) === myId) {
                    SyncStore.resolveOwnMessageBroadcast(p);
                } else {
                    SyncStore.upsertMessage(p);
                }
                return;
            }
        }

        if (msg.type === 'message.created' && !p.thread_id && typeof p.channel_id === 'string') {
            const pChNorm = SyncStore.normalizeSyncChannelId(p.channel_id);
            if (selectedNorm && pChNorm === selectedNorm) {
                return;
            }
            const list = SyncStore.state.channels.list;
            if (!list.some((c) => SyncStore.normalizeSyncChannelId(c.id) === pChNorm)) {
                return;
            }
            const authUser = this.auth?.user;
            const myId = authUser?.id;
            if (typeof myId !== 'string' || myId === '') {
                throw new Error('Нет user id для синхронизации списка каналов.');
            }
            const preview = lanePreviewFromMessagePayload(p);
            const patch = {
                last_message_preview: preview,
                last_message_at: p.sent_at,
            };
            if (senderUserId(p.sender) !== myId) {
                const cur = list.find((c) => SyncStore.normalizeSyncChannelId(c.id) === pChNorm);
                const n = (typeof cur?.unread_count === 'number' ? cur.unread_count : 0) + 1;
                patch.unread_count = n;
                const mids = p.mentioned_user_ids;
                if (Array.isArray(mids) && mids.some((id) => id === myId)) {
                    const mn = (typeof cur?.mention_unread_count === 'number' ? cur.mention_unread_count : 0) + 1;
                    patch.mention_unread_count = mn;
                }
            }
            SyncStore.patchChannelFields(p.channel_id, patch);
            return;
        }
        if (msg.type === 'message.updated') {
            if (
                selectedNorm
                && typeof p.channel_id === 'string'
                && SyncStore.normalizeSyncChannelId(p.channel_id) === selectedNorm
            ) {
                SyncStore.upsertMessage(p);
            }
            return;
        }
        if (msg.type === 'message.reaction_changed') {
            if (
                selectedNorm
                && typeof p.channel_id === 'string'
                && SyncStore.normalizeSyncChannelId(p.channel_id) === selectedNorm
            ) {
                const mid = p.message_id;
                if (typeof mid !== 'string') throw new Error('message.reaction_changed: нет message_id.');
                SyncStore.mergeMessageFields(mid, { reactions: p.reactions });
            }
            return;
        }
        if (msg.type === 'message.deleted') {
            if (
                selectedNorm
                && typeof p.channel_id === 'string'
                && SyncStore.normalizeSyncChannelId(p.channel_id) === selectedNorm
            ) {
                SyncStore.scheduleMessageRemovalAfterDeleteAnimation(p.message_id);
            }
            return;
        }
        if (msg.type === 'channel.pins_changed') {
            if (p.id) {
                SyncStore.mergeChannel(p);
            }
            return;
        }
        if (msg.type === 'message.status_changed') {
            if (
                selectedNorm
                && typeof p.channel_id === 'string'
                && SyncStore.normalizeSyncChannelId(p.channel_id) === selectedNorm
            ) {
                const mid = p.message_id;
                if (typeof mid !== 'string') throw new Error('message.status_changed: нет message_id.');
                SyncStore.mergeMessageFields(mid, { status: p.status });
            }
            return;
        }

        if (msg.type === 'call.incoming') {
            const myId = this.auth?.user?.id;
            // Трекаем активный звонок ВСЕГДА — нужно для индикатора в сайдбаре у всех участников.
            this._activeCallChannels = { ...this._activeCallChannels, [p.channel_id]: { call_id: p.call_id, call_type: p.call_type } };
            // Инициатор уже открыл оверлей через WS-ack — баннер ему не нужен.
            if (p.initiator_user_id && p.initiator_user_id === myId) return;
            if (this._activeCall?.call_id === p.call_id) return;
            const channel = SyncStore.state.channels.list.find(c => c.id === p.channel_id);
            const names = this._buildNamesMap();
            let channelName;
            if (channel) {
                channelName = SyncStore.channelDisplayTitle(channel);
            } else if (typeof p.channel_display_name === 'string' && p.channel_display_name.trim() !== '') {
                channelName = p.channel_display_name;
            } else if (p.incoming_channel_kind === 'direct' && typeof p.caller_display_name === 'string') {
                channelName = p.caller_display_name;
            } else {
                channelName = p.channel_id;
            }
            const callerName = (typeof p.caller_display_name === 'string' && p.caller_display_name !== '')
                ? p.caller_display_name
                : (names[p.created_by_user_id] ?? p.created_by_user_id);
            this._incomingCall = {
                call_id: p.call_id,
                call_type: p.call_type,
                channel_id: p.channel_id,
                caller_name: callerName,
                channel_name: channelName,
            };
            return;
        }
        if (msg.type === 'call.signal') {
            const myId = this.auth?.user?.id;
            // Фильтруем: обрабатываем только сигналы предназначенные нам.
            if (p.target_user_id && p.target_user_id !== myId) return;
            window.dispatchEvent(new CustomEvent('call-signal', { detail: p }));
            return;
        }
        if (msg.type === 'call.ended') {
            if (this._activeCall?.call_id === p.call_id) {
                this._activeCall = null;
            }
            if (this._incomingCall?.call_id === p.call_id) {
                this._incomingCall = null;
            }
            // Убираем из трекера активных звонков.
            if (p.channel_id) {
                const next = { ...this._activeCallChannels };
                delete next[p.channel_id];
                this._activeCallChannels = next;
            }
            return;
        }
        if (msg.type === 'call.recording.started') {
            if (this._activeCall?.call_id === p.call_id) {
                this._activeCall = {
                    ...this._activeCall,
                    recording_started_by_user_id: p.started_by_user_id || '',
                };
                const overlay = this.renderRoot?.querySelector('call-overlay');
                overlay?.setRecordingStatus?.('recording');
            }
            return;
        }
        if (msg.type === 'call.admin.changed') {
            if (this._activeCall?.call_id === p.call_id) {
                this._activeCall = { ...this._activeCall, created_by_user_id: p.created_by_user_id };
            }
            if (this._incomingCall?.call_id === p.call_id) {
                this._incomingCall = { ...this._incomingCall };
            }
            return;
        }
        if (msg.type === 'call.recording.stopped') {
            if (this._activeCall?.call_id === p.call_id) {
                this._activeCall = {
                    ...this._activeCall,
                    recording_started_by_user_id: '',
                };
                const overlay = this.renderRoot?.querySelector('call-overlay');
                overlay?.setRecordingStatus?.('idle');
            }
            return;
        }
        if (msg.type === 'call.recording.failed') {
            if (this._activeCall?.call_id === p.call_id) {
                this._activeCall = {
                    ...this._activeCall,
                    recording_started_by_user_id: '',
                };
                const overlay = this.renderRoot?.querySelector('call-overlay');
                overlay?.setRecordingStatus?.('failed', p.error || 'Ошибка записи');
            }
            return;
        }
        if (
            msg.type === 'call.transcript.ready'
            || msg.type === 'call.summary.ready'
            || msg.type === 'call.export.crm.done'
            || msg.type === 'call.export.crm.failed'
        ) {
            SyncStore.upsertMeeting(p);
            return;
        }
        if (msg.type === 'call.transcript.failed' || msg.type === 'call.summary.failed') {
            SyncStore.upsertMeeting(p);
            const errorText = (typeof p.error === 'string' && p.error !== '') ? p.error : 'Ошибка обработки встречи';
            console.error(`[sync] ${msg.type}: ${errorText}`, p);
            if (this._activeCall?.call_id === p.call_id) {
                const overlay = this.renderRoot?.querySelector('call-overlay');
                overlay?.setRecordingStatus?.('failed', errorText);
            }
            return;
        }
        if (msg.type === 'call.accepted') {
            return;
        }
        if (msg.type === 'call.declined'
            || msg.type === 'call.participant_joined'
            || msg.type === 'call.participant_left') {
            return;
        }

        const noop = new Set([
            'channel.created',
            'thread.created',
            'git_resource.upserted',
        ]);
        if (noop.has(msg.type)) {
            return;
        }

        throw new Error(`[sync-ws] неизвестное realtime-событие: ${msg.type}`);
    }

    _buildNamesMap() {
        const members = SyncStore.state.companyMembers?.list ?? [];
        const map = {};
        for (const m of members) {
            if (m.user_id) map[m.user_id] = m.name || m.user_id;
        }
        const authUser = this.auth?.user;
        if (authUser?.id) map[authUser.id] = authUser.name || authUser.id;
        return map;
    }

    async _joinCallInChannel(channelId) {
        const callInfo = this._activeCallChannels[channelId];
        if (!callInfo) return;
        const syncApi = this.services.get('syncApi');
        const [callData, tokenData] = await Promise.all([
            syncApi.get(`/calls/${callInfo.call_id}`),
            syncApi.get(`/calls/${callInfo.call_id}/token`),
        ]);
        const ws = this.services.get('syncWs');
        if (ws) {
            const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
                (c ^ (Math.random() * 16 >> c / 4)).toString(16));
            ws.sendJson({ id, type: 'call.accept', payload: { call_id: callInfo.call_id } });
        }
        this._activeCall = { ...callData, livekit_token: tokenData.token, livekit_url: tokenData.livekit_url };
    }

    async _openCallOverlay(callData) {
        this._activeCall = callData;
        this._incomingCall = null;
        const syncApi = this.services.get('syncApi');
        const pending = [syncApi.get(`/calls/${callData.call_id}/recordings`)];
        if (callData.mode === 'sfu') {
            pending.push(syncApi.get(`/calls/${callData.call_id}/token`));
        }
        const [recordingsData, tokenData] = await Promise.all(pending);
        if (!this._activeCall || this._activeCall.call_id !== callData.call_id) return;
        const recordings = Array.isArray(recordingsData) ? recordingsData : [];
        const activeRecording = recordings.find((item) =>
            item
            && (item.status === 'requested' || item.status === 'recording')
        );
        const nextCallData = {
            ...callData,
            recording_started_by_user_id: activeRecording?.started_by_user_id || '',
        };
        if (callData.mode === 'sfu') {
            nextCallData.livekit_token = tokenData.token;
            nextCallData.livekit_url = tokenData.livekit_url;
        }
        this._activeCall = nextCallData;
        const overlay = this.renderRoot?.querySelector('call-overlay');
        if (overlay && activeRecording) {
            overlay.setRecordingStatus('recording');
        }
    }

    async _acceptCall(callId) {
        this._incomingCall = null;
        const ws = this.services.get('syncWs');
        if (!ws) throw new Error('syncWs не инициализирован при accept.');
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.accept', payload: { call_id: callId } });

        const syncApi = this.services.get('syncApi');
        const callData = await syncApi.get(`/calls/${callId}`);
        if (callData.mode === 'sfu') {
            const tokenData = await syncApi.get(`/calls/${callId}/token`);
            this._activeCall = { ...callData, livekit_token: tokenData.token, livekit_url: tokenData.livekit_url };
        } else {
            this._activeCall = callData;
        }
    }

    _declineCall(callId) {
        this._incomingCall = null;
        // Убираем индикатор звонка в сайдбаре чтобы не было случайного повторного входа.
        const next = { ...this._activeCallChannels };
        for (const [chId, info] of Object.entries(next)) {
            if (info.call_id === callId) { delete next[chId]; break; }
        }
        this._activeCallChannels = next;
        const ws = this.services.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.decline', payload: { call_id: callId } });
    }

    _sendCallHangupWs(callId) {
        if (typeof callId !== 'string' || callId === '') return;
        const ws = this.services.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        this._callHangupRequestIds.add(id);
        ws.sendJson({ id, type: 'call.hangup', payload: { call_id: callId } });
    }

    _sendCallRecordingWs(callId, action) {
        if (typeof callId !== 'string' || callId === '') return;
        if (action !== 'start' && action !== 'stop') {
            throw new Error('action должен быть start или stop.');
        }
        const ws = this.services.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({
            id,
            type: action === 'start' ? 'call.recording.start' : 'call.recording.stop',
            payload: { call_id: callId },
        });
    }

    _sendCallTransferAdminWs(callId, targetUserId) {
        if (typeof callId !== 'string' || callId === '') return;
        if (typeof targetUserId !== 'string' || targetUserId === '') return;
        const ws = this.services.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({
            id,
            type: 'call.admin.transfer',
            payload: { call_id: callId, target_user_id: targetUserId },
        });
    }

    async _refetchOnReconnect() {
        const syncApi = this.services.get('syncApi');
        await SyncStore.loadChannels(syncApi);
        const { selectedChannelId } = SyncStore.state.chat;
        if (selectedChannelId) {
            await SyncStore.loadMessages(syncApi, selectedChannelId);
        }
    }

    _connectWs() {
        if (this._ws) return;

        const ws = new SyncWsService();
        this._ws = ws;
        this.services.register('syncWs', ws);

        ws.onOpen(() => {
            const isReconnect = this._wsEverConnected;
            this._wsEverConnected = true;
            SyncStore.setWsState('open');
            if (isReconnect) {
                void this._refetchOnReconnect();
            }
        });

        ws.onClose(() => {
            SyncStore.setWsState('closed');
        });

        ws.onError(() => {
            SyncStore.setWsState('closed');
            SyncStore.failAllPending();
        });

        ws.onMessage((data) => {
            try {
                this._handleWsMessage(data);
            } catch (e) {
                console.error('[sync-ws] ошибка обработки кадра:', e, { raw: data });
            }
        });

        ws.connect();

        if (this._typingPruneTimer != null) {
            clearInterval(this._typingPruneTimer);
        }
        this._typingPruneTimer = setInterval(() => {
            SyncStore.pruneExpiredTypingPeers();
        }, 1200);
    }

    async _openMeetingsPanel() {
        SyncStore.openMeetingsPanel();
        const syncApi = this.services.get('syncApi');
        await SyncStore.loadMeetings(syncApi, { limit: 200 });
    }

    _meetingDateMs(meeting) {
        if (!meeting || typeof meeting !== 'object') {
            return null;
        }
        const iso = typeof meeting.created_at === 'string' && meeting.created_at !== ''
            ? meeting.created_at
            : meeting.updated_at;
        if (typeof iso !== 'string' || iso === '') {
            return null;
        }
        const parsed = Date.parse(iso);
        if (Number.isNaN(parsed)) {
            return null;
        }
        return parsed;
    }

    _filteredMeetings() {
        const meetings = SyncStore.state.meetings.list;
        const channelFilter = this._meetingsChannelFilter;
        const fromFilter = this._meetingsDateFrom;
        const toFilter = this._meetingsDateTo;
        const fromMs = fromFilter !== '' ? Date.parse(`${fromFilter}T00:00:00`) : null;
        const toMs = toFilter !== '' ? Date.parse(`${toFilter}T23:59:59.999`) : null;
        return meetings.filter((meeting) => {
            if (channelFilter !== 'all' && meeting.channel_id !== channelFilter) {
                return false;
            }
            const meetingDateMs = this._meetingDateMs(meeting);
            if (fromMs !== null && meetingDateMs !== null && meetingDateMs < fromMs) {
                return false;
            }
            if (toMs !== null && meetingDateMs !== null && meetingDateMs > toMs) {
                return false;
            }
            return true;
        });
    }

    _meetingChannelOptions(meetings) {
        const channelIds = new Set();
        for (const meeting of meetings) {
            if (typeof meeting.channel_id === 'string' && meeting.channel_id !== '') {
                channelIds.add(meeting.channel_id);
            }
        }
        const options = [];
        for (const channelId of channelIds) {
            const channel = SyncStore.state.channels.list.find((item) => item.id === channelId);
            const title = channel ? SyncStore.channelDisplayTitle(channel) : channelId;
            options.push({ channelId, title });
        }
        options.sort((left, right) => left.title.localeCompare(right.title, 'ru'));
        return options;
    }

    _formatMeetingDate(isoValue) {
        if (typeof isoValue !== 'string' || isoValue === '') {
            return '—';
        }
        const date = new Date(isoValue);
        if (Number.isNaN(date.getTime())) {
            return '—';
        }
        return new Intl.DateTimeFormat('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        }).format(date);
    }

    _channelName(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            return '—';
        }
        const channel = SyncStore.state.channels.list.find((item) => item.id === channelId);
        if (!channel) {
            return channelId;
        }
        return SyncStore.channelDisplayTitle(channel);
    }

    _channelInitials(channelId) {
        const label = this._channelName(channelId).trim();
        if (label === '') {
            return '?';
        }
        return label.slice(0, 1).toUpperCase();
    }

    _statusLabel(exportStatus) {
        if (exportStatus === 'done') return 'готово';
        if (exportStatus === 'pending') return 'в работе';
        if (exportStatus === 'failed') return 'ошибка';
        return '—';
    }

    _selectedMeeting() {
        const selected = SyncStore.state.meetings.selected;
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            return null;
        }
        const details = this._meetingDetailsById[selected.meeting_id];
        if (details) {
            return details;
        }
        return selected;
    }

    _meetingParticipants(meetingDetails) {
        const segments = Array.isArray(meetingDetails?.segments) ? meetingDetails.segments : [];
        const participants = new Set();
        for (const segment of segments) {
            if (typeof segment.speaker_user_id === 'string' && segment.speaker_user_id !== '') {
                participants.add(segment.speaker_user_id);
                continue;
            }
            if (typeof segment.speaker_guest_name === 'string' && segment.speaker_guest_name !== '') {
                participants.add(segment.speaker_guest_name);
                continue;
            }
            if (typeof segment.speaker_identity === 'string' && segment.speaker_identity !== '') {
                participants.add(segment.speaker_identity);
            }
        }
        return [...participants];
    }

    _durationText(meetingDetails) {
        const startedAt = meetingDetails?.recording?.started_at;
        const endedAt = meetingDetails?.recording?.ended_at;
        if (typeof startedAt !== 'string' || typeof endedAt !== 'string') {
            return '—';
        }
        const startedMs = Date.parse(startedAt);
        const endedMs = Date.parse(endedAt);
        if (Number.isNaN(startedMs) || Number.isNaN(endedMs) || endedMs <= startedMs) {
            return '—';
        }
        const diffSeconds = Math.round((endedMs - startedMs) / 1000);
        const hours = Math.floor(diffSeconds / 3600);
        const minutes = Math.floor((diffSeconds % 3600) / 60);
        const seconds = diffSeconds % 60;
        if (hours > 0) {
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    async _openMeetingDetails(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error('meetingId обязателен.');
        }
        const syncApi = this.services.get('syncApi');
        this._meetingsDetailsLoadingId = meetingId;
        const details = await syncApi.getMeeting(meetingId);
        if (!details || typeof details !== 'object' || !details.meeting) {
            this._meetingsDetailsLoadingId = null;
            throw new Error('Некорректный ответ details встречи.');
        }
        const selected = {
            ...details.meeting,
            recording: details.recording ?? null,
            segments: Array.isArray(details.segments) ? details.segments : [],
        };
        this._meetingDetailsById = {
            ...this._meetingDetailsById,
            [meetingId]: selected,
        };
        this._meetingsDetailsLoadingId = null;
        SyncStore.setMeetingSelected(selected);
    }

    async _exportSelectedMeeting() {
        const selected = this._selectedMeeting();
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            throw new Error('meeting_id обязателен.');
        }
        const syncApi = this.services.get('syncApi');
        await syncApi.exportMeetingToCrm(selected.meeting_id, null);
        await SyncStore.loadMeetings(syncApi, { limit: 200 });
        await this._openMeetingDetails(selected.meeting_id);
    }

    async _retrySelectedMeeting() {
        const selected = this._selectedMeeting();
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            throw new Error('meeting_id обязателен.');
        }
        const syncApi = this.services.get('syncApi');
        await syncApi.retryMeetingProcessing(selected.meeting_id);
        await SyncStore.loadMeetings(syncApi, { limit: 200 });
        await this._openMeetingDetails(selected.meeting_id);
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }
        if (!this._isAuthenticated) {
            return html`<app-loader></app-loader>`;
        }

        const callUiLocked = this._activeCall != null;
        const meetingsOpen = this._ui.meetingsPanelOpen === true;
        const meetingsState = SyncStore.state.meetings;
        const filteredMeetings = this._filteredMeetings();
        const meetingChannelOptions = this._meetingChannelOptions(meetingsState.list);
        const selectedMeeting = this._selectedMeeting();
        const selectedParticipants = selectedMeeting ? this._meetingParticipants(selectedMeeting) : [];

        return html`
            <div class="sidebar" ?inert=${callUiLocked}>
                <sync-sidebar
                    .activeCallChannels=${this._activeCallChannels}
                    @join-call-channel=${(e) => this._joinCallInChannel(e.detail.channelId)}
                ></sync-sidebar>
            </div>

            <div class="main" ?inert=${callUiLocked}>
                <platform-island padding="none" content-no-scroll>
                    <chat-view></chat-view>
                </platform-island>
            </div>

            <space-settings-modal></space-settings-modal>

            ${meetingsOpen ? html`
                <div
                    class="meetings-overlay"
                    @click=${(e) => {
        if (e.target === e.currentTarget) {
            SyncStore.closeMeetingsPanel();
        }
    }}
                >
                    <div class="meetings-modal" @click=${(e) => e.stopPropagation()}>
                        <div class="meetings-header">
                            <div class="meetings-title">Встречи компании</div>
                            <button type="button" class="back-btn" @click=${() => SyncStore.closeMeetingsPanel()}>Закрыть</button>
                        </div>
                        <div class="meetings-controls">
                            <select
                                class="meetings-select"
                                .value=${this._meetingsChannelFilter}
                                @change=${(e) => {
                                    const nextValue = e.target.value;
                                    this._meetingsChannelFilter = nextValue;
                                }}
                            >
                                <option value="all">Все каналы</option>
                                ${meetingChannelOptions.map((item) => html`
                                    <option value=${item.channelId}>${item.title}</option>
                                `)}
                            </select>
                            <input
                                class="meetings-date"
                                type="date"
                                .value=${this._meetingsDateFrom}
                                @change=${(e) => {
                                    this._meetingsDateFrom = e.target.value;
                                }}
                            />
                            <input
                                class="meetings-date"
                                type="date"
                                .value=${this._meetingsDateTo}
                                @change=${(e) => {
                                    this._meetingsDateTo = e.target.value;
                                }}
                            />
                            <button
                                type="button"
                                class="back-btn"
                                @click=${() => {
        this._meetingsChannelFilter = 'all';
        this._meetingsDateFrom = '';
        this._meetingsDateTo = '';
    }}
                            >
                                Сбросить фильтры
                            </button>
                        </div>
                        <div class="meetings-body">
                            <div class="meetings-list">
                                ${meetingsState.loading ? html`<div class="meetings-empty">Загрузка встреч...</div>` : ''}
                                ${!meetingsState.loading && filteredMeetings.length === 0
                                    ? html`<div class="meetings-empty">По фильтрам ничего не найдено.</div>`
                                    : ''}
                                ${filteredMeetings.map((meeting) => {
        const isActive = selectedMeeting?.meeting_id === meeting.meeting_id;
        const loading = this._meetingsDetailsLoadingId === meeting.meeting_id;
        const statusClass = `meeting-status ${meeting.export_status}`;
        const badgeColor = `background:hsl(${hueFromString(meeting.channel_id)} 48% 42%)`;
        const details = this._meetingDetailsById[meeting.meeting_id];
        const duration = details ? this._durationText(details) : '—';
        return html`
                                        <button
                                            type="button"
                                            class="meeting-card ${isActive ? 'active' : ''}"
                                            @click=${async () => {
            try {
                await this._openMeetingDetails(meeting.meeting_id);
            } catch (err) {
                const text = err instanceof Error ? err.message : String(err);
                this.error(text);
            }
        }}
                                        >
                                            <div class="meeting-card-row">
                                                <span class="meeting-channel">
                                                    <span class="meeting-channel-badge" style=${badgeColor}>${this._channelInitials(meeting.channel_id)}</span>
                                                    <span class="meeting-channel-name">${this._channelName(meeting.channel_id)}</span>
                                                </span>
                                                <span class=${statusClass}>${this._statusLabel(meeting.export_status)}</span>
                                            </div>
                                            <div class="meeting-meta">Дата: ${this._formatMeetingDate(meeting.created_at)}</div>
                                            <div class="meeting-meta">Длительность: ${duration}</div>
                                            <div class="meeting-meta">meeting_id: ${meeting.meeting_id.slice(0, 12)}...</div>
                                            ${loading ? html`<div class="meeting-meta">Загрузка деталей...</div>` : ''}
                                        </button>
                                    `;
    })}
                            </div>
                            <div class="meetings-detail">
                                ${selectedMeeting ? html`
                                    <div class="meetings-title">Детали встречи</div>
                                    <div class="detail-grid">
                                        <div>
                                            <div class="detail-label">Канал</div>
                                            <div class="detail-value">${this._channelName(selectedMeeting.channel_id)}</div>
                                        </div>
                                        <div>
                                            <div class="detail-label">Дата</div>
                                            <div class="detail-value">${this._formatMeetingDate(selectedMeeting.created_at)}</div>
                                        </div>
                                        <div>
                                            <div class="detail-label">Длительность</div>
                                            <div class="detail-value">${this._durationText(selectedMeeting)}</div>
                                        </div>
                                        <div>
                                            <div class="detail-label">Статус</div>
                                            <div class="detail-value">${this._statusLabel(selectedMeeting.export_status)}</div>
                                        </div>
                                        <div>
                                            <div class="detail-label">Участники</div>
                                            <div class="detail-value">${selectedParticipants.length > 0 ? selectedParticipants.join(', ') : '—'}</div>
                                        </div>
                                        <div>
                                            <div class="detail-label">meeting_id</div>
                                            <div class="detail-value">${selectedMeeting.meeting_id}</div>
                                        </div>
                                    </div>
                                    <div class="detail-actions">
                                        ${selectedMeeting.recording?.raw_file_download_url ? html`
                                            <a
                                                class="back-btn"
                                                href=${selectedMeeting.recording.raw_file_download_url}
                                                download
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >Скачать запись</a>
                                        ` : ''}
                                        ${selectedMeeting.transcript_text_download_url ? html`
                                            <a
                                                class="back-btn"
                                                href=${selectedMeeting.transcript_text_download_url}
                                                download
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >Скачать транскрипт</a>
                                        ` : ''}
                                        <button
                                            type="button"
                                            class="back-btn"
                                            @click=${async () => {
            try {
                await this._exportSelectedMeeting();
            } catch (err) {
                const text = err instanceof Error ? err.message : String(err);
                this.error(text);
            }
        }}
                                        >
                                            Экспорт в CRM
                                        </button>
                                        <button
                                            type="button"
                                            class="back-btn"
                                            @click=${async () => {
            try {
                await this._retrySelectedMeeting();
            } catch (err) {
                const text = err instanceof Error ? err.message : String(err);
                this.error(text);
            }
        }}
                                        >
                                            Повторить обработку
                                        </button>
                                    </div>
                                ` : html`
                                    <div class="meetings-empty">Выберите карточку встречи в списке слева.</div>
                                `}
                            </div>
                        </div>
                    </div>
                </div>
            ` : ''}

            ${this._activeCall ? html`
                <call-overlay
                    call-id=${this._activeCall.call_id}
                    channel-id=${this._activeCall.channel_id || ''}
                    mode=${this._activeCall.mode}
                    call-type=${this._activeCall.call_type}
                    current-user-id=${this.auth?.user?.id || ''}
                    meeting-admin-user-id=${this._activeCall.created_by_user_id || ''}
                    recording-started-by-user-id=${this._activeCall.recording_started_by_user_id || ''}
                    livekit-url=${this._activeCall.livekit_url || ''}
                    livekit-token=${this._activeCall.livekit_token || ''}
                    .names=${this._buildNamesMap()}
                    @call-ended=${() => { this._activeCall = null; }}
                    @call-hangup-request=${(e) => this._sendCallHangupWs(e.detail?.callId)}
                    @call-recording-start=${(e) => this._sendCallRecordingWs(e.detail?.callId, 'start')}
                    @call-recording-stop=${(e) => this._sendCallRecordingWs(e.detail?.callId, 'stop')}
                    @call-transfer-admin=${(e) => this._sendCallTransferAdminWs(e.detail?.callId, e.detail?.targetUserId)}
                ></call-overlay>
            ` : ''}

            ${this._incomingCall ? html`
                <call-incoming
                    call-id=${this._incomingCall.call_id}
                    call-type=${this._incomingCall.call_type}
                    channel-name=${this._incomingCall.channel_name}
                    caller-name=${this._incomingCall.caller_name}
                    @call-accept=${(e) => this._acceptCall(e.detail.callId)}
                    @call-decline=${(e) => this._declineCall(e.detail.callId)}
                ></call-incoming>
            ` : ''}
        `;
    }

    updated(changedProps) {
        super.updated(changedProps);
        if (changedProps.has('_activeCall')) {
            this.toggleAttribute('data-call-active', this._activeCall != null);
        }
    }
}

customElements.define('sync-app', SyncApp);
