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
        _callUiMinimized: { state: true },
        _incomingCall: { state: true },
        _activeCallChannels: { state: true },
        _mobileShell: { state: true },
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
             * Полноэкранный оверлей звонка: иначе iOS WebKit оставляет hit-testing на .main под overlay.
             * При свёрнутом звонке атрибут снят — чат и сайдбар снова кликабельны.
             */
            :host([data-call-overlay-expanded]) {
                overflow: visible;
            }

            :host([data-call-overlay-expanded]) .sidebar,
            :host([data-call-overlay-expanded]) .main {
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
        /** id WS-команд call.hangup — ack тоже содержит CallRead с call_id, без фильтра открыл бы оверлей снова */
        this._callHangupRequestIds = new Set();
        this._callUiMinimized = false;
        this._boundSyncCallOverlayExpand = () => {
            if (this._activeCall == null) return;
            this._callUiMinimized = false;
            this._syncUiActiveCallOverlay();
            this.requestUpdate();
        };
        this._boundSyncCallBannerHangup = () => {
            const id = this._activeCall?.call_id;
            if (typeof id !== 'string' || id === '') {
                return;
            }
            this._sendCallHangupWs(id);
        };
        this._boundJoinCallFromBoundary = (e) => {
            const d = e.detail;
            if (d == null || typeof d !== 'object') return;
            const channelId = d.channelId;
            const callId = d.callId;
            if (typeof channelId !== 'string' || channelId === '') return;
            if (typeof callId !== 'string' || callId === '') return;
            void this._joinCallInChannel(channelId, callId);
        };
        this._mqMobileShell = window.matchMedia('(max-width: 767px)');
        this._mobileShell = this._mqMobileShell.matches;
    }

    _syncUiActiveCallOverlay() {
        if (this._activeCall == null) {
            this._callUiMinimized = false;
            SyncStore.setUiActiveCallOverlay(null);
            return;
        }
        const ch = this._activeCall.channel_id;
        const channelId = typeof ch === 'string' ? ch : '';
        SyncStore.setUiActiveCallOverlay({
            call_id: this._activeCall.call_id,
            channel_id: channelId,
            minimized: this._callUiMinimized,
        });
    }

    _blurCallOverlayFocus() {
        const host = this.renderRoot?.querySelector('call-overlay');
        const sr = host?.shadowRoot;
        const inner = sr?.activeElement;
        if (inner && typeof inner.blur === 'function') {
            inner.blur();
        }
        if (host && document.activeElement === host && typeof host.blur === 'function') {
            host.blur();
        }
    }

    _onCallMinimizeRequest() {
        if (this._activeCall == null) return;
        this._blurCallOverlayFocus();
        this._callUiMinimized = true;
        this._syncUiActiveCallOverlay();
        this.requestUpdate();
    }

    _localeTag() {
        const loc = this.i18n.getCurrentLocale();
        return loc === 'en' ? 'en-US' : 'ru-RU';
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
            this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
            window.addEventListener('sync-call-overlay-expand', this._boundSyncCallOverlayExpand);
            window.addEventListener('sync-call-banner-hangup', this._boundSyncCallBannerHangup);
            window.addEventListener('join-call-from-boundary', this._boundJoinCallFromBoundary);

            if (!this._mobileShellMqBound) {
                this._mobileShellMqBound = true;
                this._onMobileShellChange = (e) => {
                    this._mobileShell = e.matches;
                    this.requestUpdate();
                };
                this._mqMobileShell.addEventListener('change', this._onMobileShellChange);
            }

            if (!this._isAuthenticated) return;

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
            console.error('[SyncApp] initialization failed:', err);
            this.redirectToAuth();
        }
    }

    disconnectedCallback() {
        window.removeEventListener('sync-call-overlay-expand', this._boundSyncCallOverlayExpand);
        window.removeEventListener('sync-call-banner-hangup', this._boundSyncCallBannerHangup);
        window.removeEventListener('join-call-from-boundary', this._boundJoinCallFromBoundary);
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback?.();
        if (this._mobileShellMqBound) {
            this._mobileShellMqBound = false;
            this._mqMobileShell?.removeEventListener('change', this._onMobileShellChange);
        }
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
            throw new Error(this.i18n.t('sync_app.ws_json_expected'));
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
        throw new Error(this.i18n.t('sync_app.ws_unknown_frame', { detail: JSON.stringify(msg) }));
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
                throw new Error(this.i18n.t('sync_app.ws_user_presence_company_id'));
            }
            if (p.company_id !== companyId) return;
            SyncStore.applyUserPresence(p);
            return;
        }

        const p = msg.payload;
        if (!p || typeof p !== 'object') {
            throw new Error(this.i18n.t('sync_app.ws_payload_required', { type: msg.type }));
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
                throw new Error(this.i18n.t('sync_app.ws_channel_read_user_id'));
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
                    throw new Error(this.i18n.t('sync_app.ws_message_created_user_id'));
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
                throw new Error(this.i18n.t('sync_app.ws_no_user_id_channel_list'));
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
                if (typeof mid !== 'string') throw new Error(this.i18n.t('sync_app.ws_reaction_no_message_id'));
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
                if (typeof mid !== 'string') throw new Error(this.i18n.t('sync_app.ws_status_no_message_id'));
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
                this._syncUiActiveCallOverlay();
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
                overlay?.setRecordingStatus?.(
                    'failed',
                    p.error || this.i18n.t('recording_error_default', {}),
                );
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

        throw new Error(this.i18n.t('sync_app.ws_unknown_realtime', { type: msg.type }));
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

    async _joinCallInChannel(channelId, explicitCallId) {
        const fromMap = this._activeCallChannels[channelId];
        const callId =
            typeof explicitCallId === 'string' && explicitCallId !== ''
                ? explicitCallId
                : (fromMap && typeof fromMap.call_id === 'string' ? fromMap.call_id : '');
        if (callId === '') return;

        if (this._activeCall?.call_id === callId && !this._callUiMinimized) {
            return;
        }
        if (this._activeCall?.call_id === callId && this._callUiMinimized) {
            this._callUiMinimized = false;
            this._syncUiActiveCallOverlay();
            this.requestUpdate();
            return;
        }

        const syncApi = this.services.get('syncApi');
        const [callData, tokenData] = await Promise.all([
            syncApi.get(`/calls/${callId}`),
            syncApi.get(`/calls/${callId}/token`),
        ]);
        const ws = this.services.get('syncWs');
        if (ws) {
            const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
                (c ^ (Math.random() * 16 >> c / 4)).toString(16));
            ws.sendJson({ id, type: 'call.accept', payload: { call_id: callId } });
        }
        this._callUiMinimized = false;
        this._activeCall = { ...callData, livekit_token: tokenData.token, livekit_url: tokenData.livekit_url };
        this._syncUiActiveCallOverlay();
    }

    async _openCallOverlay(callData) {
        this._callUiMinimized = false;
        this._activeCall = callData;
        this._syncUiActiveCallOverlay();
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
        this._syncUiActiveCallOverlay();
        const overlay = this.renderRoot?.querySelector('call-overlay');
        if (overlay && activeRecording) {
            overlay.setRecordingStatus('recording');
        }
    }

    async _acceptCall(callId) {
        this._incomingCall = null;
        const ws = this.services.get('syncWs');
        if (!ws) throw new Error(this.i18n.t('sync_app.err_sync_ws_not_initialized'));
        const id = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16));
        ws.sendJson({ id, type: 'call.accept', payload: { call_id: callId } });

        const syncApi = this.services.get('syncApi');
        const callData = await syncApi.get(`/calls/${callId}`);
        this._callUiMinimized = false;
        if (callData.mode === 'sfu') {
            const tokenData = await syncApi.get(`/calls/${callId}/token`);
            this._activeCall = { ...callData, livekit_token: tokenData.token, livekit_url: tokenData.livekit_url };
        } else {
            this._activeCall = callData;
        }
        this._syncUiActiveCallOverlay();
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
            throw new Error(this.i18n.t('sync_app.err_recording_action'));
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
                console.error('[sync-ws] frame handler error:', e, { raw: data });
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

        const callUiLocked = this._activeCall != null && !this._callUiMinimized;

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
                    ?minimized=${this._callUiMinimized}
                    ?inert=${this._callUiMinimized}
                    @call-minimize-request=${() => this._onCallMinimizeRequest()}
                    @call-ended=${() => {
        this._activeCall = null;
        this._callUiMinimized = false;
        this._syncUiActiveCallOverlay();
    }}
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
        this.toggleAttribute('data-call-active', this._activeCall != null);
        this.toggleAttribute(
            'data-call-overlay-expanded',
            this._activeCall != null && !this._callUiMinimized,
        );
    }
}

customElements.define('sync-app', SyncApp);
