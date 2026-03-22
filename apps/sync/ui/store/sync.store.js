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

const baseStore = new BaseStore('sync', {
    spaces: {
        list: [],
        loading: false,
    },
    channels: {
        list: [],
        loading: false,
    },
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
        showCreateSpace: false,
        showCreateChannel: false,
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
        baseStore.setState(s => ({
            channels: { ...s.channels, list, loading: false },
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
            ui: { ...s.ui, channelSettingsChannelId: channelId },
        }));
    },

    closeChannelSettings() {
        baseStore.setState(s => ({
            ui: { ...s.ui, channelSettingsChannelId: null },
        }));
    },

    openSpaceSettings(spaceId) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error('spaceId обязателен.');
        }
        baseStore.setState(s => ({
            ui: { ...s.ui, spaceSettingsSpaceId: spaceId },
        }));
    },

    closeSpaceSettings() {
        baseStore.setState(s => ({
            ui: { ...s.ui, spaceSettingsSpaceId: null },
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
            ui: { ...s.ui, flashMessageId: messageId },
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
        baseStore.setState(s => ({
            chat: {
                ...s.chat,
                selectedSpaceId: spaceId,
                selectedChannelId: channelId,
                focusedThreadId: null,
                replyToMessage: null,
                editMessage: null,
                pinnedNavigateIndex: 0,
            },
        }));
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

    setShowCreateSpace(show) {
        baseStore.setState(s => ({ ui: { ...s.ui, showCreateSpace: show } }));
    },

    setShowCreateChannel(show) {
        baseStore.setState(s => ({ ui: { ...s.ui, showCreateChannel: show } }));
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
        if (!spaceId) {
            return all;
        }
        return all.filter(c => c.space_id === spaceId && c.type !== 'direct');
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

            const topicChannels = channels.filter(c => c.type !== 'direct' && c.space_id);
            if (topicChannels.length > 0) {
                const inSelected = selectedSpaceId
                    ? topicChannels.filter(c => c.space_id === selectedSpaceId).length
                    : 0;
                if (inSelected === 0) {
                    selectedSpaceId = topicChannels[0].space_id;
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
            this.getDirectChannels().find(c => c.peer && String(c.peer.id) === want) ?? null
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
