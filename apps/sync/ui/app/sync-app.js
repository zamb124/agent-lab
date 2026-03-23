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

export class SyncApp extends PlatformApp {
    static properties = {
        _chat: { state: true },
        _ui: { state: true },
    };

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex !important;
                flex-direction: row !important;
                width: 100vw;
                height: 100vh;
                overflow: hidden;
                background: var(--bg-gradient);
            }

            .sidebar {
                height: 100vh;
                flex-shrink: 0;
                overflow: visible;
                background: transparent;
            }

            .main {
                flex: 1;
                height: 100vh;
                overflow: hidden;
                display: flex;
                padding: var(--space-4);
            }

            platform-island {
                flex: 1;
                min-height: calc(100vh - 2rem);
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
        await this._restoreLastSelection();
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
                if (msg.result) {
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

    _connectWs() {
        if (this._ws) return;

        const ws = new SyncWsService();
        this._ws = ws;
        ServiceRegistry.register('syncWs', ws);

        ws.onOpen(() => {
            SyncStore.setWsState('open');
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
                <sync-sidebar></sync-sidebar>
            </div>

            <div class="main">
                <platform-island>
                    <chat-view></chat-view>
                </platform-island>
            </div>

            <space-settings-modal></space-settings-modal>
        `;
    }
}

customElements.define('sync-app', SyncApp);
