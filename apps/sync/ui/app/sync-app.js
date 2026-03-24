/**
 * SyncApp — главное приложение Sync Chat
 * Наследует PlatformApp, подключает единый платформенный auth.
 */
import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import { SyncAPIService } from '../services/sync-api.service.js';
import { SyncWsService } from '../services/sync-ws.service.js';
import { SyncStore } from '../store/sync.store.js';
import { lanePreviewFromMessagePayload } from '../utils/lane-preview.js';
import { senderUserId } from '../utils/sender.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/layout/platform-island.js';
import '../features/call-overlay.js';
import '../features/call-incoming.js';

export class SyncApp extends PlatformApp {
    static properties = {
        _chat: { state: true },
        _ui: { state: true },
        _activeCall: { state: true },
        _incomingCall: { state: true },
        _activeCallChannels: { state: true },
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
                padding: var(--space-4);
            }

            platform-island {
                flex: 1;
                min-height: calc(var(--app-vh, 100vh) - 2rem);
                overflow: hidden;
                display: flex;
                flex-direction: column;
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
            }
        `
    ];

    constructor() {
        super();
        this._chat = SyncStore.state.chat;
        this._ui = SyncStore.state.ui;
        this._ws = null;
        this._unsubscribe = null;
        this._typingPruneTimer = null;
        this._wsEverConnected = false;
        this._activeCallChannels = {};
    }

    setupStore() {
        return SyncStore;
    }

    getBaseUrl() {
        return '/sync';
    }

    async initServices() {
        await super.initServices();
        await ServiceRegistry.registerCore('/sync');
        ServiceRegistry.register('syncApi', new SyncAPIService('/sync/api/v1'));

        this._unsubscribe = SyncStore.subscribe((state) => {
            this._chat = state.chat;
            this._ui = state.ui;
        });
    }

    async checkAuth() {
        const auth = ServiceRegistry.auth;
        const isAuthenticated = await auth.validateToken();
        if (!isAuthenticated) {
            this.redirectToAuth();
            return false;
        }
        return true;
    }

    async connectedCallback() {
        await super.connectedCallback();

        if (!this._isAuthenticated) return;

        const syncApi = ServiceRegistry.get('syncApi');

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
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        if (this._typingPruneTimer != null) {
            clearInterval(this._typingPruneTimer);
            this._typingPruneTimer = null;
        }
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

        const syncApi = ServiceRegistry.get('syncApi');
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
            if (msg.ok) {
                if (msg.result && msg.result.call_id) {
                    // call.invite вернул CallRead — открываем оверлей у инициатора.
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
            const myId = ServiceRegistry.auth?.user?.id;
            if (typeof myId === 'string' && myId !== '' && uid === myId) return;
            SyncStore.applyChannelTyping({
                channel_id: p.channel_id,
                thread_id: p.thread_id ?? null,
                typing: !!p.typing,
                user: p.user,
            });
            return;
        }

        const p = msg.payload;
        if (!p || typeof p !== 'object') {
            throw new Error(`${msg.type}: payload обязателен.`);
        }

        if (msg.type === 'channel.member_added') {
            const authUser = ServiceRegistry.auth?.user;
            const myId = authUser?.id;
            const added = p.added_user_id;
            if (
                typeof myId === 'string'
                && myId !== ''
                && typeof added === 'string'
                && added === myId
            ) {
                const syncApi = ServiceRegistry.get('syncApi');
                SyncStore.loadChannels(syncApi);
            }
            return;
        }

        if (msg.type === 'space.created') {
            const syncApi = ServiceRegistry.get('syncApi');
            void SyncStore.loadSpaces(syncApi).then(() => {
                SyncStore.sanitizeChatSelectionAfterLoad();
            });
            return;
        }

        if (msg.type === 'channel.read_updated') {
            const authUser = ServiceRegistry.auth?.user;
            const myId = authUser?.id;
            if (typeof myId !== 'string' || myId === '') {
                throw new Error('channel.read_updated: auth.user.id обязателен.');
            }
            if (p.reader_user_id === myId && typeof p.channel_id === 'string') {
                SyncStore.patchChannelFields(p.channel_id, { unread_count: 0 });
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
                const authUser = ServiceRegistry.auth?.user;
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
            const authUser = ServiceRegistry.auth?.user;
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
            const myId = ServiceRegistry.auth?.user?.id;
            // Трекаем активный звонок ВСЕГДА — нужно для индикатора в сайдбаре у всех участников.
            this._activeCallChannels = { ...this._activeCallChannels, [p.channel_id]: { call_id: p.call_id, call_type: p.call_type } };
            // Инициатор уже открыл оверлей через WS-ack — баннер ему не нужен.
            if (p.initiator_user_id && p.initiator_user_id === myId) return;
            if (this._activeCall?.call_id === p.call_id) return;
            const channel = SyncStore.state.channels.list.find(c => c.id === p.channel_id);
            this._incomingCall = {
                call_id: p.call_id,
                call_type: p.call_type,
                channel_id: p.channel_id,
                caller_name: p.created_by_user_id,
                channel_name: channel?.name ?? p.channel_id,
            };
            return;
        }
        if (msg.type === 'call.signal') {
            const myId = ServiceRegistry.auth?.user?.id;
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
        const authUser = ServiceRegistry.auth?.user;
        if (authUser?.id) map[authUser.id] = authUser.name || authUser.id;
        return map;
    }

    async _joinCallInChannel(channelId) {
        const callInfo = this._activeCallChannels[channelId];
        if (!callInfo) return;
        const syncApi = ServiceRegistry.get('syncApi');
        const [callData, tokenData] = await Promise.all([
            syncApi.get(`/calls/${callInfo.call_id}`),
            syncApi.get(`/calls/${callInfo.call_id}/token`),
        ]);
        const ws = ServiceRegistry.get('syncWs');
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
        if (callData.mode === 'sfu') {
            const syncApi = ServiceRegistry.get('syncApi');
            const tokenData = await syncApi.get(`/calls/${callData.call_id}/token`);
            // Пока ждали токен — звонок мог завершиться. Не перезаписываем если уже null.
            if (!this._activeCall || this._activeCall.call_id !== callData.call_id) return;
            this._activeCall = { ...callData, livekit_token: tokenData.token, livekit_url: tokenData.livekit_url };
        }
    }

    async _acceptCall(callId) {
        this._incomingCall = null;
        const ws = ServiceRegistry.get('syncWs');
        if (!ws) throw new Error('syncWs не инициализирован при accept.');
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.accept', payload: { call_id: callId } });

        const syncApi = ServiceRegistry.get('syncApi');
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
        const ws = ServiceRegistry.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.decline', payload: { call_id: callId } });
    }

    _hangupCall(callId) {
        this._activeCall = null;
        if (!callId) return;
        const ws = ServiceRegistry.get('syncWs');
        if (!ws) return;
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.hangup', payload: { call_id: callId } });
    }

    async _refetchOnReconnect() {
        const syncApi = ServiceRegistry.get('syncApi');
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
        ServiceRegistry.register('syncWs', ws);

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

    render() {
        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }
        if (!this._isAuthenticated) {
            return html`<app-loader></app-loader>`;
        }

        return html`
            <div class="sidebar">
                <sync-sidebar
                    .activeCallChannels=${this._activeCallChannels}
                    @join-call-channel=${(e) => this._joinCallInChannel(e.detail.channelId)}
                ></sync-sidebar>
            </div>

            <div class="main">
                <platform-island>
                    <chat-view></chat-view>
                </platform-island>
            </div>

            <space-settings-modal></space-settings-modal>

            ${this._activeCall ? html`
                <call-overlay
                    call-id=${this._activeCall.call_id}
                    channel-id=${this._activeCall.channel_id || ''}
                    mode=${this._activeCall.mode}
                    call-type=${this._activeCall.call_type}
                    livekit-url=${this._activeCall.livekit_url || ''}
                    livekit-token=${this._activeCall.livekit_token || ''}
                    .names=${this._buildNamesMap()}
                    @call-ended=${() => { const id = this._activeCall?.call_id; if (id) this._hangupCall(id); }}
                    @call-hangup-request=${(e) => { if (e.detail.callId) this._hangupCall(e.detail.callId); }}
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
}

customElements.define('sync-app', SyncApp);
