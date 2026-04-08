/**
 * SyncStore — состояние Sync Chat
 * Следует паттерну RagStore / BaseStore.
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';
import { i18n, t } from '@platform/services/i18n/i18n.service.js';

import { formatPeerPresenceLine } from '../utils/presence-format.js';


let _flashMessageTimer = null;

/** Таймеры удаления сообщения после анимации разрушения (message.deleted). */
const _messageDeleteTimers = new Map();

function _clearAllMessageDeleteTimers() {
    for (const tid of _messageDeleteTimers.values()) {
        clearTimeout(tid);
    }
    _messageDeleteTimers.clear();
}

const MESSAGE_DELETE_ANIM_MS = 580;
const MESSAGES_PAGE_SIZE = 20;

function _emptyPaginationState() {
    return {
        olderCursor: null,
        hasMoreOlder: false,
        loadingOlder: false,
    };
}

function _emptyOverlayChannelState() {
    return {
        list: [],
        pending: {},
        loading: false,
        pagination: _emptyPaginationState(),
    };
}

/** UUID канала в событиях и в UI должны совпадать; сравнение без учёта регистра. */
function normalizeSyncChannelId(channelId) {
    if (typeof channelId !== 'string' || channelId === '') {
        throw new Error(t('channel_settings.err_channel_id', {}));
    }
    return channelId.trim().toLowerCase();
}

/** Каналы встреч: имя с префикса `_` не показываем в сайдбаре и в выборе канала. */
function isHiddenSyncChannelName(name) {
    return typeof name === 'string' && name.startsWith('_');
}

/** Свежие каналы наверху: по last_message_at desc, без сообщений — по created_at desc. */
function _sortChannelsByRecent(channels) {
    return [...channels].sort((a, b) => {
        const ta = a.last_message_at || a.created_at || '';
        const tb = b.last_message_at || b.created_at || '';
        if (tb > ta) return 1;
        if (tb < ta) return -1;
        return 0;
    });
}

const baseStore = new BaseStore('sync', {
    spaces: {
        list: [],
        loading: false,
    },
    channels: {
        list: [],
        loading: false,
    },
    peerReadAtByChannel: {},
    typingPeersByChannel: {},
    peerPresenceByUserId: {},
    companyMembers: {
        list: [],
        loading: false,
    },
    messages: {
        list: [],
        pending: {},
        loading: false,
    },
    messagePaginationByChannel: {},
    callOverlayChat: {
        channels: {},
    },
    chat: {
        selectedSpaceId: null,
        selectedChannelId: null,
        focusedThreadId: null,
        replyToMessage: null,
        editMessage: null,
        pinnedNavigateIndex: 0,
    },
    ws: {
        state: 'closed',
    },
    ui: {
        mobileSidebarOpen: false,
        threadDrawerOpen: false,
        spaceSettingsCreate: false,
        channelSettingsCreate: false,
        sidebarSectionOpen: {
            direct: true,
            spaces: true,
            channels: true,
        },
        selectionMode: false,
        selectedMessageIds: [],
        forwardModalOpen: false,
        forwardMessage: null,
        flashMessageId: null,
        flashMessageSeq: 0,
        deletingMessageIds: [],
        channelSettingsChannelId: null,
        /** space_id при открытии модалки создания канала (зафиксирован при open). */
        channelSettingsCreateSpaceId: null,
        spaceSettingsSpaceId: null,
        /** Пустой массив = показать все topic-каналы; иначе только каналы выбранных пространств (ИЛИ). */
        sidebarSpaceFilterIds: [],
        /**
         * Активный звонок в основном приложении: полоса в шапке канала при свёрнутом оверлее.
         * Не персистится (partialize).
         * @type {null | { call_id: string, channel_id: string, minimized: boolean }}
         */
        activeCallOverlay: null,
    },
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        chat: {
            selectedSpaceId: state.chat.selectedSpaceId,
            selectedChannelId: state.chat.selectedChannelId,
        },
        ui: {
            sidebarSectionOpen: state.ui.sidebarSectionOpen,
            sidebarSpaceFilterIds: state.ui.sidebarSpaceFilterIds ?? [],
        },
    }),
});

export const SyncStore = {
    normalizeSyncChannelId,
    isHiddenSyncChannelName,

    /**
     * Заголовок канала в списках: DM — peer, иначе имя или id.
     * @param {object} channel
     * @returns {string}
     */
    channelDisplayTitle(channel) {
        if (!channel || typeof channel !== 'object') {
            throw new Error(t('sync_store.err_channel_display_title', {}));
        }
        if (channel.type === 'direct' && channel.peer) {
            const p = channel.peer;
            if (typeof p.display_name === 'string' && p.display_name.trim() !== '') {
                return p.display_name;
            }
            if (typeof p.user_id === 'string' && p.user_id !== '') {
                return p.user_id;
            }
        }
        if (typeof channel.name === 'string' && channel.name !== '') {
            return channel.name;
        }
        if (typeof channel.id === 'string' && channel.id !== '') {
            return channel.id;
        }
        throw new Error(t('sync_store.err_channel_display_empty', {}));
    },

    /**
     * Каналы, куда можно переслать (без текущего и без служебных `_...`).
     * @param {string} excludeChannelId
     * @returns {object[]}
     */
    getForwardDestinationChannels(excludeChannelId) {
        if (typeof excludeChannelId !== 'string' || excludeChannelId === '') {
            throw new Error(t('sync_store.err_exclude_channel_id', {}));
        }
        const all = baseStore.state.channels.list;
        return all.filter((c) => {
            if (c.id === excludeChannelId) return false;
            return !isHiddenSyncChannelName(c.name);
        });
    },

    get state() {
        return baseStore.state;
    },

    subscribe(callback) {
        return baseStore.subscribe(callback);
    },

    setState(updater) {
        return baseStore.setState(updater);
    },

    setSpaces(list) {
        baseStore.setState(s => ({
            spaces: { ...s.spaces, list, loading: false },
        }));
    },

    setSpacesLoading(loading) {
        baseStore.setState(s => ({
            spaces: { ...s.spaces, loading },
        }));
    },

    setChannels(list) {
        const peerReadAt = {};
        for (const ch of list) {
            if (ch.type === 'direct' && ch.peer_last_read_at) {
                peerReadAt[ch.id] = ch.peer_last_read_at;
            }
        }
        baseStore.setState(s => ({
            channels: { ...s.channels, list, loading: false },
            peerReadAtByChannel: { ...s.peerReadAtByChannel, ...peerReadAt },
        }));
    },

    setChannelsLoading(loading) {
        baseStore.setState(s => ({
            channels: { ...s.channels, loading },
        }));
    },

    setMessages(list) {
        _clearAllMessageDeleteTimers();
        baseStore.setState(s => ({
            messages: { ...s.messages, list, loading: false, pending: {} },
            ui: { ...s.ui, deletingMessageIds: [] },
        }));
    },

    setMessagesLoading(loading) {
        baseStore.setState(s => ({
            messages: { ...s.messages, loading },
        }));
    },

    _getMessagePaginationState(source, channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        return source.messagePaginationByChannel[norm] ?? _emptyPaginationState();
    },

    _setMessagePaginationState(channelId, pagination) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (!pagination || typeof pagination !== 'object') {
            throw new Error(t('sync_store.err_pagination_required', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => ({
            messagePaginationByChannel: {
                ...s.messagePaginationByChannel,
                [norm]: {
                    ...this._getMessagePaginationState(s, channelId),
                    ...pagination,
                },
            },
        }));
    },

    _applyMessagePage(channelId, payload) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (!payload || typeof payload !== 'object') {
            throw new Error(t('sync_store.err_payload_required', {}));
        }
        if (!Array.isArray(payload.items)) {
            throw new Error(t('sync_store.err_payload_items_array', {}));
        }
        baseStore.setState((s) => ({
            messages: { ...s.messages, list: payload.items, loading: false, pending: {} },
            messagePaginationByChannel: {
                ...s.messagePaginationByChannel,
                [normalizeSyncChannelId(channelId)]: {
                    olderCursor: payload.next_cursor ?? null,
                    hasMoreOlder: typeof payload.next_cursor === 'string' && payload.next_cursor !== '',
                    loadingOlder: false,
                },
            },
            ui: { ...s.ui, deletingMessageIds: [] },
        }));
    },

    canLoadOlderMessages(channelId) {
        const p = this._getMessagePaginationState(baseStore.state, channelId);
        return p.hasMoreOlder && !p.loadingOlder;
    },

    getMessageHistoryState(channelId) {
        const p = this._getMessagePaginationState(baseStore.state, channelId);
        return {
            olderCursor: p.olderCursor,
            hasMoreOlder: p.hasMoreOlder,
            loadingOlder: p.loadingOlder,
        };
    },

    async loadOlderMessages(syncApi, channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const current = this._getMessagePaginationState(baseStore.state, channelId);
        if (!current.hasMoreOlder) {
            return [];
        }
        if (current.loadingOlder) {
            return [];
        }
        if (typeof current.olderCursor !== 'string' || current.olderCursor === '') {
            throw new Error(t('sync_store.err_older_cursor_older_messages', {}));
        }
        this._setMessagePaginationState(channelId, { loadingOlder: true });
        try {
            const payload = await syncApi.getMessages(channelId, {
                limit: MESSAGES_PAGE_SIZE,
                before: current.olderCursor,
            });
            baseStore.setState((s) => {
                const ids = new Set(s.messages.list.map((m) => m.id));
                const older = payload.items.filter((m) => !ids.has(m.id));
                return {
                    messages: {
                        ...s.messages,
                        list: [...older, ...s.messages.list],
                    },
                    messagePaginationByChannel: {
                        ...s.messagePaginationByChannel,
                        [normalizeSyncChannelId(channelId)]: {
                            ...this._getMessagePaginationState(s, channelId),
                            olderCursor: payload.next_cursor ?? null,
                            hasMoreOlder: typeof payload.next_cursor === 'string' && payload.next_cursor !== '',
                            loadingOlder: false,
                        },
                    },
                };
            });
            return payload.items;
        } catch (e) {
            this._setMessagePaginationState(channelId, { loadingOlder: false });
            throw e;
        }
    },

    _getOverlayChannelState(source, channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        const current = source.callOverlayChat.channels[norm];
        return current ?? _emptyOverlayChannelState();
    },

    setCallOverlayMessages(channelId, list) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (!Array.isArray(list)) {
            throw new Error(t('sync_store.err_list_array', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = {
                ..._emptyOverlayChannelState(),
                ...this._getOverlayChannelState(s, channelId),
                list,
                pending: {},
                loading: false,
            };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    setCallOverlayLoading(channelId, loading) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = {
                ..._emptyOverlayChannelState(),
                ...this._getOverlayChannelState(s, channelId),
                loading: !!loading,
            };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    upsertCallOverlayMessage(channelId, message) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (!message || typeof message !== 'object') {
            throw new Error(t('sync_store.err_message_required', {}));
        }
        if (typeof message.id !== 'string' || message.id === '') {
            throw new Error(t('sync_store.err_message_dot_id', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const current = this._getOverlayChannelState(s, channelId);
            const idx = current.list.findIndex((m) => m.id === message.id);
            const list = idx === -1
                ? [...current.list, message]
                : current.list.map((m, i) => (i === idx ? message : m));
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = { ...current, list };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    addCallOverlayPending(channelId, commandId, message) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof commandId !== 'string' || commandId === '') {
            throw new Error(t('sync_api.err_command_id', {}));
        }
        if (!message || typeof message !== 'object') {
            throw new Error(t('sync_store.err_message_required', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const current = this._getOverlayChannelState(s, channelId);
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = {
                ...current,
                pending: { ...current.pending, [commandId]: message },
            };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    resolveCallOverlayPending(channelId, commandId, confirmedMessage) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof commandId !== 'string' || commandId === '') {
            throw new Error(t('sync_api.err_command_id', {}));
        }
        if (!confirmedMessage || typeof confirmedMessage !== 'object') {
            throw new Error(t('sync_store.err_confirmed_message_required', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const current = this._getOverlayChannelState(s, channelId);
            const pending = { ...current.pending };
            delete pending[commandId];
            const idx = current.list.findIndex((m) => m.id === confirmedMessage.id);
            const list = idx === -1
                ? [...current.list, confirmedMessage]
                : current.list.map((m, i) => (i === idx ? confirmedMessage : m));
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = { ...current, list, pending };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    failCallOverlayPending(channelId, commandId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof commandId !== 'string' || commandId === '') {
            throw new Error(t('sync_api.err_command_id', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const current = this._getOverlayChannelState(s, channelId);
            const pendingMsg = current.pending[commandId];
            if (!pendingMsg) {
                return s;
            }
            const channels = { ...s.callOverlayChat.channels };
            channels[norm] = {
                ...current,
                pending: {
                    ...current.pending,
                    [commandId]: { ...pendingMsg, status: 'failed' },
                },
            };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
    },

    getCallOverlayDisplayMessages(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            return [];
        }
        const current = this._getOverlayChannelState(baseStore.state, channelId);
        const pending = Object.values(current.pending);
        const merged = [...current.list, ...pending];
        merged.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
        return merged;
    },

    getCallOverlayLoading(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            return false;
        }
        const current = this._getOverlayChannelState(baseStore.state, channelId);
        return current.loading;
    },

    getCallOverlayHistoryState(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            return _emptyPaginationState();
        }
        const current = this._getOverlayChannelState(baseStore.state, channelId);
        return {
            olderCursor: current.pagination?.olderCursor ?? null,
            hasMoreOlder: !!current.pagination?.hasMoreOlder,
            loadingOlder: !!current.pagination?.loadingOlder,
        };
    },

    async loadOlderCallOverlayMessages(syncApi, channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const history = this.getCallOverlayHistoryState(channelId);
        if (!history.hasMoreOlder || history.loadingOlder) {
            return [];
        }
        if (typeof history.olderCursor !== 'string' || history.olderCursor === '') {
            throw new Error(t('sync_store.err_older_cursor_overlay', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState((s) => {
            const channels = { ...s.callOverlayChat.channels };
            const current = this._getOverlayChannelState(s, channelId);
            channels[norm] = {
                ...current,
                pagination: { ...current.pagination, loadingOlder: true },
            };
            return { callOverlayChat: { ...s.callOverlayChat, channels } };
        });
        try {
            const payload = await syncApi.getMessages(channelId, {
                limit: MESSAGES_PAGE_SIZE,
                before: history.olderCursor,
            });
            baseStore.setState((s) => {
                const channels = { ...s.callOverlayChat.channels };
                const current = this._getOverlayChannelState(s, channelId);
                const ids = new Set(current.list.map((m) => m.id));
                const older = payload.items.filter((m) => !ids.has(m.id));
                channels[norm] = {
                    ...current,
                    list: [...older, ...current.list],
                    pagination: {
                        olderCursor: payload.next_cursor ?? null,
                        hasMoreOlder: typeof payload.next_cursor === 'string' && payload.next_cursor !== '',
                        loadingOlder: false,
                    },
                };
                return { callOverlayChat: { ...s.callOverlayChat, channels } };
            });
            return payload.items;
        } catch (e) {
            baseStore.setState((s) => {
                const channels = { ...s.callOverlayChat.channels };
                const current = this._getOverlayChannelState(s, channelId);
                channels[norm] = {
                    ...current,
                    pagination: { ...current.pagination, loadingOlder: false },
                };
                return { callOverlayChat: { ...s.callOverlayChat, channels } };
            });
            throw e;
        }
    },

    async loadCallOverlayMessages(syncApi, channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        this.setCallOverlayLoading(channelId, true);
        try {
            const payload = await syncApi.getMessages(channelId, { limit: MESSAGES_PAGE_SIZE });
            this.setCallOverlayMessages(channelId, payload.items);
            const norm = normalizeSyncChannelId(channelId);
            baseStore.setState((s) => {
                const channels = { ...s.callOverlayChat.channels };
                const current = channels[norm] ?? _emptyOverlayChannelState();
                channels[norm] = {
                    ...current,
                    pagination: {
                        olderCursor: payload.next_cursor ?? null,
                        hasMoreOlder: typeof payload.next_cursor === 'string' && payload.next_cursor !== '',
                        loadingOlder: false,
                    },
                };
                return { callOverlayChat: { ...s.callOverlayChat, channels } };
            });
            return payload.items;
        } catch (e) {
            this.setCallOverlayLoading(channelId, false);
            throw e;
        }
    },

    upsertMessage(message) {
        baseStore.setState(s => {
            const list = s.messages.list;
            const idx = list.findIndex(m => m.id === message.id);
            const next = idx === -1
                ? [...list, message]
                : list.map((m, i) => i === idx ? message : m);
            return { messages: { ...s.messages, list: next } };
        });
    },

    /**
     * Обрабатывает broadcast message.created для собственного сообщения.
     * Атомарно убирает pending и добавляет подтверждённое сообщение —
     * предотвращает кратковременный дубликат (pending + confirmed в одном рендере).
     * @param {object} confirmedMessage
     */
    resolveOwnMessageBroadcast(confirmedMessage) {
        baseStore.setState(s => {
            const pending = { ...s.messages.pending };
            for (const cmdId of Object.keys(pending)) {
                const pm = pending[cmdId];
                if (pm.channel_id === confirmedMessage.channel_id) {
                    delete pending[cmdId];
                    break;
                }
            }
            const list = s.messages.list;
            const idx = list.findIndex(m => m.id === confirmedMessage.id);
            const next = idx === -1
                ? [...list, confirmedMessage]
                : list.map((m, i) => i === idx ? confirmedMessage : m);
            return { messages: { ...s.messages, list: next, pending } };
        });
    },

    mergeMessageFields(messageId, fields) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(t('sync_api.err_message_id', {}));
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error(t('sync_store.err_fields_required', {}));
        }
        baseStore.setState(s => ({
            messages: {
                ...s.messages,
                list: s.messages.list.map(m => (m.id === messageId ? { ...m, ...fields } : m)),
            },
        }));
    },

    removeMessage(messageId) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(t('sync_api.err_message_id', {}));
        }
        const pending = _messageDeleteTimers.get(messageId);
        if (pending !== undefined) {
            clearTimeout(pending);
            _messageDeleteTimers.delete(messageId);
        }
        baseStore.setState(s => ({
            messages: {
                ...s.messages,
                list: s.messages.list.filter(m => m.id !== messageId),
            },
            ui: {
                ...s.ui,
                deletingMessageIds: s.ui.deletingMessageIds.filter(id => id !== messageId),
            },
        }));
    },

    /**
     * После message.deleted: анимация разрушения, затем удаление из списка.
     * @param {string} messageId
     */
    scheduleMessageRemovalAfterDeleteAnimation(messageId) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(t('sync_api.err_message_id', {}));
        }
        if (_messageDeleteTimers.has(messageId)) {
            return;
        }
        baseStore.setState(s => {
            if (s.ui.deletingMessageIds.includes(messageId)) {
                return s;
            }
            return {
                ui: {
                    ...s.ui,
                    deletingMessageIds: [...s.ui.deletingMessageIds, messageId],
                },
            };
        });
        const tid = setTimeout(() => {
            _messageDeleteTimers.delete(messageId);
            SyncStore.removeMessage(messageId);
        }, MESSAGE_DELETE_ANIM_MS);
        _messageDeleteTimers.set(messageId, tid);
    },

    mergeChannel(channel) {
        baseStore.setState(s => {
            const list = s.channels.list;
            const norm = normalizeSyncChannelId(channel.id);
            const idx = list.findIndex(c => normalizeSyncChannelId(c.id) === norm);
            const next = idx === -1
                ? [...list, channel]
                : list.map((c, i) => i === idx ? channel : c);
            return { channels: { ...s.channels, list: next } };
        });
    },

    /**
     * Частичное обновление полей канала в списке (превью, непрочитанные).
     * @param {string} channelId
     * @param {Record<string, unknown>} fields
     */
    patchChannelFields(channelId, fields) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error(t('sync_store.err_fields_required', {}));
        }
        const norm = normalizeSyncChannelId(channelId);
        baseStore.setState(s => ({
            channels: {
                ...s.channels,
                list: s.channels.list.map(c => (
                    normalizeSyncChannelId(c.id) === norm ? { ...c, ...fields } : c
                )),
            },
        }));
    },

    /**
     * @param {string} spaceId
     * @param {Record<string, unknown>} fields
     */
    patchSpaceFields(spaceId, fields) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error(t('channel_settings.err_space_id', {}));
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error(t('sync_store.err_fields_required', {}));
        }
        baseStore.setState(s => ({
            spaces: {
                ...s.spaces,
                list: s.spaces.list.map(sp => (sp.id === spaceId ? { ...sp, ...fields } : sp)),
            },
        }));
    },

    openChannelSettings(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                channelSettingsChannelId: channelId,
                channelSettingsCreate: false,
                channelSettingsCreateSpaceId: null,
            },
        }));
    },

    /**
     * space_id для создания канала: одно выделенное в фильтре, иначе selectedSpaceId, иначе первое пространство.
     * Учитываются только id из текущего списка пространств (устаревшие из persist отбрасываются).
     * @returns {string}
     */
    resolveSpaceIdForNewChannel() {
        const s = baseStore.state;
        const filtersRaw = s.ui.sidebarSpaceFilterIds ?? [];
        const valid = new Set(s.spaces.list.map(x => x.id));
        const filters = filtersRaw.filter(
            id => typeof id === 'string' && id !== '' && valid.has(id),
        );
        if (filters.length === 1) {
            return filters[0];
        }
        if (filters.length > 1) {
            throw new Error(t('sync_store.err_channel_filter_multi', {}));
        }
        const sel = s.chat.selectedSpaceId;
        if (typeof sel === 'string' && sel !== '' && valid.has(sel)) {
            return sel;
        }
        const first = s.spaces.list[0];
        if (first && typeof first.id === 'string' && first.id !== '') {
            return first.id;
        }
        throw new Error(t('sync_store.err_create_space_first', {}));
    },

    openChannelSettingsCreate() {
        const spaceId = this.resolveSpaceIdForNewChannel();
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                channelSettingsChannelId: null,
                channelSettingsCreate: true,
                channelSettingsCreateSpaceId: spaceId,
            },
        }));
    },

    /**
     * Переключить пространство в фильтре сайдбара (мультивыбор). Пустой фильтр = все каналы.
     * @param {string} spaceId
     */
    toggleSidebarSpaceFilter(spaceId) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error(t('sync_store.err_toggle_sidebar_space_id', {}));
        }
        baseStore.setState(s => {
            const prev = [...(s.ui.sidebarSpaceFilterIds ?? [])];
            const i = prev.indexOf(spaceId);
            if (i >= 0) {
                prev.splice(i, 1);
            } else {
                prev.push(spaceId);
            }
            return { ui: { ...s.ui, sidebarSpaceFilterIds: prev } };
        });
    },

    /**
     * Подпись справа от названия канала в строке: имя пространства или «Личный» для DM.
     * @param {object} channel
     * @returns {string}
     */
    channelRowMetaLabel(channel) {
        if (!channel || typeof channel !== 'object') {
            throw new Error(t('sync_store.err_channel_row_channel', {}));
        }
        if (channel.type === 'direct') {
            return t('sync_store.channel_meta_direct', {});
        }
        const sid = channel.space_id;
        if (typeof sid !== 'string' || sid === '') {
            if (channel.type === 'calendar_meeting') {
                return t('sync_store.channel_meta_calendar_meeting', {});
            }
            if (channel.type === 'group') {
                return t('sync_store.channel_meta_group', {});
            }
            throw new Error(t('sync_store.err_channel_row_no_space_id', {}));
        }
        const sp = baseStore.state.spaces.list.find(x => x.id === sid);
        if (!sp) {
            return t('sync_store.channel_meta_space_unavailable', {});
        }
        if (typeof sp.name === 'string' && sp.name !== '') {
            return sp.name;
        }
        return t('sync_store.channel_meta_unnamed', {});
    },

    /**
     * Topic-каналы для сайдбара: по умолчанию все; при непустом sidebarSpaceFilterIds — только выбранные пространства (ИЛИ).
     * Сортировка: свежие (по last_message_at) наверху, без сообщений — по created_at.
     * @returns {object[]}
     */
    getChannelsForSidebarList() {
        const all = baseStore.state.channels.list;
        const visible = (c) => !isHiddenSyncChannelName(c.name);
        const topicInSpaces = all.filter(
            c => c.type !== 'direct' && c.space_id && visible(c),
        );
        const filters = baseStore.state.ui.sidebarSpaceFilterIds ?? [];
        let filtered;
        if (!Array.isArray(filters) || filters.length === 0) {
            filtered = topicInSpaces;
        } else {
            const set = new Set(filters);
            filtered = topicInSpaces.filter(c => c.space_id && set.has(c.space_id));
        }
        return _sortChannelsByRecent(filtered);
    },

    /**
     * Личные + topic-каналы с учётом фильтра сайдбара (для сетки выбора канала).
     * @returns {object[]}
     */
    getChannelsForPickerList() {
        const all = baseStore.state.channels.list;
        const visible = (c) => !isHiddenSyncChannelName(c.name);
        const direct = _sortChannelsByRecent(all.filter(c => c.type === 'direct' && visible(c)));
        const topic = this.getChannelsForSidebarList();
        return [...direct, ...topic];
    },

    closeChannelSettings() {
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                channelSettingsChannelId: null,
                channelSettingsCreate: false,
                channelSettingsCreateSpaceId: null,
            },
        }));
    },

    openSpaceSettings(spaceId) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error(t('channel_settings.err_space_id', {}));
        }
        baseStore.setState(s => ({
            ui: { ...s.ui, spaceSettingsSpaceId: spaceId, spaceSettingsCreate: false },
        }));
    },

    openSpaceSettingsCreate() {
        baseStore.setState(s => ({
            ui: { ...s.ui, spaceSettingsSpaceId: null, spaceSettingsCreate: true },
        }));
    },

    closeSpaceSettings() {
        baseStore.setState(s => ({
            ui: { ...s.ui, spaceSettingsSpaceId: null, spaceSettingsCreate: false },
        }));
    },

    setReplyToMessage(msg) {
        baseStore.setState(s => ({
            chat: { ...s.chat, replyToMessage: msg, editMessage: null },
        }));
    },

    clearReplyToMessage() {
        baseStore.setState(s => ({
            chat: { ...s.chat, replyToMessage: null },
        }));
    },

    setEditMessage(msg) {
        baseStore.setState(s => ({
            chat: { ...s.chat, editMessage: msg, replyToMessage: null },
        }));
    },

    clearEditMessage() {
        baseStore.setState(s => ({
            chat: { ...s.chat, editMessage: null },
        }));
    },

    setPinnedNavigateIndex(index) {
        baseStore.setState(s => ({
            chat: { ...s.chat, pinnedNavigateIndex: index },
        }));
    },

    setSelectionMode(on) {
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                selectionMode: !!on,
                selectedMessageIds: on ? s.ui.selectedMessageIds : [],
            },
        }));
    },

    toggleMessageSelection(messageId) {
        baseStore.setState(s => {
            const cur = s.ui.selectedMessageIds;
            const has = cur.includes(messageId);
            const selectedMessageIds = has
                ? cur.filter(id => id !== messageId)
                : [...cur, messageId];
            return { ui: { ...s.ui, selectedMessageIds } };
        });
    },

    clearMessageSelection() {
        baseStore.setState(s => ({
            ui: { ...s.ui, selectedMessageIds: [] },
        }));
    },

    setForwardModal(open, message) {
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                forwardModalOpen: !!open,
                forwardMessage: open ? message : null,
            },
        }));
    },

    /**
     * Краткая подсветка пузыря по id (навигация к ответу, закрепам).
     * @param {string} messageId
     */
    flashMessageHighlight(messageId) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(t('sync_api.err_message_id', {}));
        }
        if (_flashMessageTimer !== null) {
            clearTimeout(_flashMessageTimer);
            _flashMessageTimer = null;
        }
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                flashMessageId: messageId,
                flashMessageSeq: (s.ui.flashMessageSeq ?? 0) + 1,
            },
        }));
        _flashMessageTimer = setTimeout(() => {
            _flashMessageTimer = null;
            baseStore.setState(s => ({
                ui: { ...s.ui, flashMessageId: null },
            }));
        }, 2800);
    },

    addPending(commandId, message) {
        baseStore.setState(s => ({
            messages: {
                ...s.messages,
                pending: { ...s.messages.pending, [commandId]: message },
            },
        }));
    },

    resolvePending(commandId, confirmedMessage) {
        baseStore.setState(s => {
            const pending = { ...s.messages.pending };
            delete pending[commandId];
            const list = s.messages.list;
            const idx = list.findIndex(m => m.id === confirmedMessage.id);
            const next = idx === -1
                ? [...list, confirmedMessage]
                : list.map((m, i) => i === idx ? confirmedMessage : m);
            return { messages: { ...s.messages, list: next, pending } };
        });
    },

    failPending(commandId) {
        baseStore.setState(s => {
            const pendingMsg = s.messages.pending[commandId];
            if (!pendingMsg) return s;
            return {
                messages: {
                    ...s.messages,
                    pending: {
                        ...s.messages.pending,
                        [commandId]: { ...pendingMsg, status: 'failed' },
                    },
                },
            };
        });
    },

    failAllPending() {
        baseStore.setState(s => {
            const pending = {};
            for (const [id, msg] of Object.entries(s.messages.pending)) {
                pending[id] = { ...msg, status: 'failed' };
            }
            return { messages: { ...s.messages, pending } };
        });
    },

    setPeerReadAt(channelId, isoStr) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof isoStr !== 'string' || isoStr === '') {
            throw new Error(t('sync_store.err_iso_str_required', {}));
        }
        baseStore.setState(s => ({
            peerReadAtByChannel: { ...s.peerReadAtByChannel, [channelId]: isoStr },
        }));
    },

    selectSpace(spaceId) {
        baseStore.setState(s => ({
            chat: {
                ...s.chat,
                selectedSpaceId: spaceId,
                selectedChannelId: null,
                focusedThreadId: null,
                replyToMessage: null,
                editMessage: null,
                pinnedNavigateIndex: 0,
            },
        }));
    },

    selectChannel(spaceId, channelId) {
        baseStore.setState(s => {
            const prevCh = s.chat.selectedChannelId;
            const typingPeersByChannel = { ...(s.typingPeersByChannel ?? {}) };
            if (typeof prevCh === 'string' && prevCh !== '' && prevCh !== channelId) {
                delete typingPeersByChannel[normalizeSyncChannelId(prevCh)];
            }
            return {
                chat: {
                    ...s.chat,
                    selectedSpaceId: spaceId,
                    selectedChannelId: channelId,
                    focusedThreadId: null,
                    replyToMessage: null,
                    editMessage: null,
                    pinnedNavigateIndex: 0,
                },
                typingPeersByChannel,
            };
        });
    },

    /**
     * @param {{ channel_id: string, thread_id: string | null | undefined, typing: boolean, user: { user_id: string, display_name?: string | null } }} payload
     */
    applyChannelTyping(payload) {
        const channelId = payload.channel_id;
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('sync_store.err_typing_channel_id', {}));
        }
        const u = payload.user;
        if (!u || typeof u.user_id !== 'string' || u.user_id === '') {
            throw new Error(t('sync_store.err_typing_user_user_id', {}));
        }
        const uid = u.user_id;
        const name = typeof u.display_name === 'string' && u.display_name.trim() !== ''
            ? u.display_name.trim()
            : uid;
        const tid = payload.thread_id === undefined || payload.thread_id === null || payload.thread_id === ''
            ? null
            : payload.thread_id;
        const typing = !!payload.typing;
        const mapKey = normalizeSyncChannelId(channelId);
        baseStore.setState(s => {
            const byCh = s.typingPeersByChannel ?? {};
            const prev = byCh[mapKey] ?? [];
            let next = [...prev];
            const until = typing ? Date.now() + 5000 : Date.now() + 3000;
            const idx = next.findIndex(
                row => row.user_id === uid && (row.thread_id ?? null) === tid,
            );
            const row = { user_id: uid, display_name: name, thread_id: tid, until };
            if (idx >= 0) {
                next[idx] = row;
            } else if (typing) {
                next.push(row);
            }
            return {
                ...s,
                typingPeersByChannel: {
                    ...byCh,
                    [mapKey]: next,
                },
            };
        });
    },

    pruneExpiredTypingPeers() {
        const now = Date.now();
        baseStore.setState(s => {
            const src = s.typingPeersByChannel ?? {};
            const nextMap = {};
            let changed = false;
            for (const [ch, rows] of Object.entries(src)) {
                const kept = rows.filter(r => r.until > now);
                if (kept.length !== rows.length) {
                    changed = true;
                }
                if (kept.length > 0) {
                    nextMap[ch] = kept;
                } else if (rows.length > 0) {
                    changed = true;
                }
            }
            if (!changed && Object.keys(nextMap).length === Object.keys(src).length) {
                return s;
            }
            return { ...s, typingPeersByChannel: nextMap };
        });
    },

    /**
     * Строка под заголовком: только другие участники (себя не показываем).
     * Без валидного myUserId нельзя отличить себя от собеседника — только raise.
     *
     * @param {string} channelId
     * @param {string | null} focusedThreadId
     * @param {string} myUserId
     * @returns {string}
     */
    getTypingIndicatorLine(channelId, focusedThreadId, myUserId) {
        if (typeof channelId !== 'string' || channelId === '') return '';
        if (typeof myUserId !== 'string' || myUserId === '') return '';
        const now = Date.now();
        const mapKey = normalizeSyncChannelId(channelId);
        const list = (baseStore.state.typingPeersByChannel ?? {})[mapKey] ?? [];
        const f = focusedThreadId != null && focusedThreadId !== '' ? focusedThreadId : null;
        const others = list.filter((row) => {
            if (row.until <= now) return false;
            const rt = row.thread_id ?? null;
            if (f === null ? rt !== null : (rt !== null && rt !== f)) return false;
            return row.user_id !== myUserId;
        });
        if (others.length === 0) return '';
        const sortLoc = i18n.getCurrentLocale() === 'ru' ? 'ru' : 'en';
        others.sort((a, b) => a.display_name.localeCompare(b.display_name, sortLoc));
        if (others.length === 1) {
            return t('sync_store.typing_one', { name: others[0].display_name });
        }
        if (others.length === 2) {
            return t('sync_store.typing_two', {
                name1: others[0].display_name,
                name2: others[1].display_name,
            });
        }
        const rest = others.length - 2;
        return t('sync_store.typing_many', {
            name1: others[0].display_name,
            name2: others[1].display_name,
            n: rest,
        });
    },

    /**
     * @param {{ company_id: string, user_id: string, online: boolean, last_seen_at: string | null }} payload
     */
    applyUserPresence(payload) {
        const uid = payload.user_id;
        if (typeof uid !== 'string' || uid === '') {
            throw new Error(t('sync_store.err_presence_user_id', {}));
        }
        const online = !!payload.online;
        const rawLast = payload.last_seen_at;
        const last_seen_at = rawLast === undefined || rawLast === null || rawLast === ''
            ? null
            : String(rawLast);
        baseStore.setState(s => ({
            peerPresenceByUserId: {
                ...s.peerPresenceByUserId,
                [uid]: {
                    online,
                    last_seen_at: online ? null : last_seen_at,
                },
            },
        }));
    },

    /**
     * @param {string} userId
     * @returns {string}
     */
    getPeerPresenceSubtitle(userId) {
        if (typeof userId !== 'string' || userId === '') {
            throw new Error(t('sync_store.err_peer_subtitle_user_id', {}));
        }
        const row = (baseStore.state.peerPresenceByUserId ?? {})[userId];
        if (!row) {
            return '';
        }
        return formatPeerPresenceLine(row.online, row.last_seen_at);
    },

    setFocusedThread(threadId) {
        baseStore.setState(s => ({
            chat: { ...s.chat, focusedThreadId: threadId },
        }));
    },

    setWsState(state) {
        baseStore.setState(s => ({ ws: { ...s.ws, state } }));
    },

    setMobileSidebarOpen(open) {
        baseStore.setState(s => ({ ui: { ...s.ui, mobileSidebarOpen: open } }));
    },

    setThreadDrawerOpen(open) {
        baseStore.setState(s => ({ ui: { ...s.ui, threadDrawerOpen: open } }));
    },

    /**
     * Состояние оверлея звонка для шапки чата (свёрнут / полный экран).
     * @param {null | { call_id: string, channel_id: string, minimized: boolean }} overlay
     */
    setUiActiveCallOverlay(overlay) {
        if (overlay === null) {
            baseStore.setState(s => ({ ui: { ...s.ui, activeCallOverlay: null } }));
            return;
        }
        if (typeof overlay !== 'object') {
            throw new Error(t('sync_store.err_active_call_overlay_payload', {}));
        }
        const callId = overlay.call_id;
        const channelId = overlay.channel_id;
        const minimized = overlay.minimized;
        if (typeof callId !== 'string' || callId === '') {
            throw new Error(t('sync_store.err_active_call_overlay_call_id', {}));
        }
        if (typeof channelId !== 'string') {
            throw new Error(t('sync_store.err_active_call_overlay_channel_id', {}));
        }
        if (typeof minimized !== 'boolean') {
            throw new Error(t('sync_store.err_active_call_overlay_minimized', {}));
        }
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                activeCallOverlay: { call_id: callId, channel_id: channelId, minimized },
            },
        }));
    },

    /**
     * @param {'direct'|'spaces'|'channels'} key
     * @param {boolean} open
     */
    setSidebarSectionOpen(key, open) {
        const allowed = ['direct', 'spaces', 'channels'];
        if (!allowed.includes(key)) {
            throw new Error(t('sync_store.err_unknown_sidebar_section', { key }));
        }
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                sidebarSectionOpen: {
                    ...s.ui.sidebarSectionOpen,
                    [key]: !!open,
                },
            },
        }));
    },

    collapseAllSidebarSections() {
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                sidebarSectionOpen: { direct: false, spaces: false, channels: false },
            },
        }));
    },

    expandAllSidebarSections() {
        baseStore.setState(s => ({
            ui: {
                ...s.ui,
                sidebarSectionOpen: { direct: true, spaces: true, channels: true },
            },
        }));
    },

    getDirectChannels() {
        const all = baseStore.state.channels.list;
        return all.filter(c => c.type === 'direct');
    },

    getDisplayMessages() {
        const s = baseStore.state;
        const pending = Object.values(s.messages.pending);
        const merged = [...s.messages.list, ...pending];
        merged.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
        return merged;
    },

    /**
     * Каналы пространства без личных. Без spaceId — все каналы пользователя (picker).
     * @param {string|null} spaceId
     */
    getChannelsForSpace(spaceId) {
        const all = baseStore.state.channels.list;
        const visible = (c) => !isHiddenSyncChannelName(c.name);
        if (!spaceId) {
            return all.filter(visible);
        }
        return all.filter(c => c.space_id === spaceId && c.type !== 'direct' && visible(c));
    },

    getThreadIds() {
        const msgs = SyncStore.getDisplayMessages();
        const set = new Set();
        for (const m of msgs) {
            if (m.thread_id) set.add(m.thread_id);
        }
        return Array.from(set);
    },

    async loadSpaces(syncApi) {
        baseStore.setState(s => ({ spaces: { ...s.spaces, loading: true } }));
        try {
            const items = await syncApi.getSpaces();
            this.setSpaces(items);
            const validSpaceIds = new Set(items.map(x => x.id));
            baseStore.setState(s => {
                const prev = s.ui.sidebarSpaceFilterIds ?? [];
                const pruned = prev.filter(
                    id => typeof id === 'string' && id !== '' && validSpaceIds.has(id),
                );
                const same =
                    pruned.length === prev.length
                    && pruned.every((v, i) => v === prev[i]);
                if (same) {
                    return s;
                }
                return { ui: { ...s.ui, sidebarSpaceFilterIds: pruned } };
            });
            return items;
        } catch (e) {
            baseStore.setState(s => ({ spaces: { ...s.spaces, loading: false } }));
            throw e;
        }
    },

    async loadChannels(syncApi) {
        baseStore.setState(s => ({ channels: { ...s.channels, loading: true } }));
        try {
            const items = await syncApi.getChannels();
            this.setChannels(items);
            return items;
        } catch (e) {
            baseStore.setState(s => ({ channels: { ...s.channels, loading: false } }));
            throw e;
        }
    },

    async loadCompanyMembers(syncApi) {
        baseStore.setState(s => ({ companyMembers: { ...s.companyMembers, loading: true } }));
        try {
            const items = await syncApi.getCompanyMembers();
            baseStore.setState(s => {
                const nextPresence = { ...s.peerPresenceByUserId };
                for (const m of items) {
                    if (typeof m.user_id !== 'string' || m.user_id === '') {
                        throw new Error(t('sync_store.err_company_member_user_id', {}));
                    }
                    const ls = m.last_seen_at;
                    nextPresence[m.user_id] = {
                        online: !!m.is_online,
                        last_seen_at: ls === undefined || ls === null || ls === ''
                            ? null
                            : String(ls),
                    };
                }
                return {
                    companyMembers: { list: items, loading: false },
                    peerPresenceByUserId: nextPresence,
                };
            });
            return items;
        } catch (e) {
            baseStore.setState(s => ({ companyMembers: { ...s.companyMembers, loading: false } }));
            throw e;
        }
    },

    /**
     * После загрузки списков: выровнять выбранное пространство с каналами пользователя.
     * Persist `selectedSpaceId` не привязан к аккаунту — возможен выбор пространства без topic-каналов у этого юзера (пустой список в сайдбаре).
     */
    sanitizeChatSelectionAfterLoad() {
        baseStore.setState(s => {
            const spaces = s.spaces.list;
            const channels = s.channels.list;
            let selectedSpaceId = s.chat.selectedSpaceId;
            let selectedChannelId = s.chat.selectedChannelId;

            const validSpaceIds = new Set(spaces.map(x => x.id));
            if (selectedSpaceId != null && selectedSpaceId !== '' && !validSpaceIds.has(selectedSpaceId)) {
                selectedSpaceId = null;
            }

            if (selectedChannelId != null && selectedChannelId !== '') {
                const ch = channels.find(c => c.id === selectedChannelId);
                if (!ch) {
                    selectedChannelId = null;
                } else if (ch.type !== 'direct' && ch.space_id) {
                    selectedSpaceId = ch.space_id;
                }
            }

            const topicChannels = channels.filter(
                c => c.type !== 'direct' && c.space_id && !isHiddenSyncChannelName(c.name),
            );
            if (topicChannels.length > 0) {
                const inSelected = selectedSpaceId
                    ? topicChannels.filter(c => c.space_id === selectedSpaceId).length
                    : 0;
                if (inSelected === 0) {
                    selectedSpaceId = topicChannels[0].space_id;
                }
            } else if (selectedChannelId) {
                const chKeep = channels.find(c => c.id === selectedChannelId);
                if (chKeep && chKeep.space_id && isHiddenSyncChannelName(chKeep.name)) {
                    selectedSpaceId = chKeep.space_id;
                } else {
                    selectedSpaceId = null;
                }
            } else {
                selectedSpaceId = null;
            }

            if (
                selectedSpaceId === s.chat.selectedSpaceId
                && selectedChannelId === s.chat.selectedChannelId
            ) {
                return s;
            }
            return {
                chat: {
                    ...s.chat,
                    selectedSpaceId,
                    selectedChannelId,
                },
            };
        });
    },

    /**
     * @param {string} peerUserId
     */
    findDirectChannelForPeer(peerUserId) {
        if (typeof peerUserId !== 'string' || peerUserId === '') {
            throw new Error(t('sync_api.err_peer_user_id', {}));
        }
        const want = String(peerUserId);
        return (
            this.getDirectChannels().find(c => c.peer && String(c.peer.user_id) === want) ?? null
        );
    },

    async loadMessages(syncApi, channelId) {
        baseStore.setState(s => ({ messages: { ...s.messages, loading: true } }));
        const payload = await syncApi.getMessages(channelId, { limit: MESSAGES_PAGE_SIZE });
        this._applyMessagePage(channelId, payload);
        await syncApi.markChannelRead(channelId);
        this.patchChannelFields(channelId, { unread_count: 0, mention_unread_count: 0 });
        return payload.items;
    },

    async selectChannelAndLoadMessages(syncApi, spaceId, channelId) {
        this.selectChannel(spaceId, channelId);
        this.patchChannelFields(channelId, { unread_count: 0, mention_unread_count: 0 });
        await this.loadMessages(syncApi, channelId);
    },

};
