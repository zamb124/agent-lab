/**
 * SyncStore — состояние Sync Chat
 * Следует паттерну RagStore / BaseStore.
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

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

/** UUID канала в событиях и в UI должны совпадать; сравнение без учёта регистра. */
function normalizeSyncChannelId(channelId) {
    if (typeof channelId !== 'string' || channelId === '') {
        throw new Error('normalizeSyncChannelId: channelId обязателен.');
    }
    return channelId.trim().toLowerCase();
}

/** Каналы встреч: имя с префикса `_` не показываем в сайдбаре и в выборе канала. */
function isHiddenSyncChannelName(name) {
    return typeof name === 'string' && name.startsWith('_');
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
    companyMembers: {
        list: [],
        loading: false,
    },
    messages: {
        list: [],
        pending: {},
        loading: false,
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
        spaceSettingsSpaceId: null,
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
        },
    }),
});

export const SyncStore = {
    normalizeSyncChannelId,
    isHiddenSyncChannelName,

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
            throw new Error('messageId обязателен.');
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error('fields обязателен.');
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
            throw new Error('messageId обязателен.');
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
            throw new Error('messageId обязателен.');
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
            const idx = list.findIndex(c => c.id === channel.id);
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
            throw new Error('channelId обязателен.');
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error('fields обязателен.');
        }
        baseStore.setState(s => ({
            channels: {
                ...s.channels,
                list: s.channels.list.map(c => (c.id === channelId ? { ...c, ...fields } : c)),
            },
        }));
    },

    /**
     * @param {string} spaceId
     * @param {Record<string, unknown>} fields
     */
    patchSpaceFields(spaceId, fields) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error('spaceId обязателен.');
        }
        if (!fields || typeof fields !== 'object') {
            throw new Error('fields обязателен.');
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
            throw new Error('channelId обязателен.');
        }
        baseStore.setState(s => ({
            ui: { ...s.ui, channelSettingsChannelId: channelId, channelSettingsCreate: false },
        }));
    },

    openChannelSettingsCreate() {
        baseStore.setState(s => ({
            ui: { ...s.ui, channelSettingsChannelId: null, channelSettingsCreate: true },
        }));
    },

    closeChannelSettings() {
        baseStore.setState(s => ({
            ui: { ...s.ui, channelSettingsChannelId: null, channelSettingsCreate: false },
        }));
    },

    openSpaceSettings(spaceId) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error('spaceId обязателен.');
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
            throw new Error('messageId обязателен.');
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
            throw new Error('channelId обязателен.');
        }
        if (typeof isoStr !== 'string' || isoStr === '') {
            throw new Error('isoStr обязателен.');
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
            throw new Error('channel.typing: channel_id обязателен.');
        }
        const u = payload.user;
        if (!u || typeof u.user_id !== 'string' || u.user_id === '') {
            throw new Error('channel.typing: user.user_id обязателен.');
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
        others.sort((a, b) => a.display_name.localeCompare(b.display_name, 'ru'));
        if (others.length === 1) return `${others[0].display_name} печатает…`;
        if (others.length === 2) return `${others[0].display_name}, ${others[1].display_name} печатают…`;
        const rest = others.length - 2;
        return `${others[0].display_name}, ${others[1].display_name} и ещё ${rest}…`;
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
     * @param {'direct'|'spaces'|'channels'} key
     * @param {boolean} open
     */
    setSidebarSectionOpen(key, open) {
        const allowed = ['direct', 'spaces', 'channels'];
        if (!allowed.includes(key)) {
            throw new Error(`Неизвестная секция сайдбара: ${key}`);
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
            baseStore.setState(s => ({
                companyMembers: { list: items, loading: false },
            }));
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
            throw new Error('peerUserId обязателен.');
        }
        const want = String(peerUserId);
        return (
            this.getDirectChannels().find(c => c.peer && String(c.peer.user_id) === want) ?? null
        );
    },

    async loadMessages(syncApi, channelId) {
        baseStore.setState(s => ({ messages: { ...s.messages, loading: true } }));
        const items = await syncApi.getMessages(channelId);
        this.setMessages(items);
        await syncApi.markChannelRead(channelId);
        this.patchChannelFields(channelId, { unread_count: 0 });
        return items;
    },

    async selectChannelAndLoadMessages(syncApi, spaceId, channelId) {
        this.selectChannel(spaceId, channelId);
        await this.loadMessages(syncApi, channelId);
    },
};
