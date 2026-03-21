/**
 * SyncStore — состояние Sync Chat
 * Следует паттерну RagStore / BaseStore.
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';

const baseStore = new BaseStore('sync', {
    spaces: {
        list: [],
        loading: false,
    },
    channels: {
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
    },
    ws: {
        state: 'closed',
    },
    ui: {
        mobileSidebarOpen: false,
        threadDrawerOpen: false,
        showCreateSpace: false,
        showCreateChannel: false,
    },
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        chat: {
            selectedSpaceId: state.chat.selectedSpaceId,
            selectedChannelId: state.chat.selectedChannelId,
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
        baseStore.setState(s => ({
            messages: { ...s.messages, list, loading: false, pending: {} },
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
            chat: { ...s.chat, selectedSpaceId: spaceId, selectedChannelId: null, focusedThreadId: null },
        }));
    },

    selectChannel(spaceId, channelId) {
        baseStore.setState(s => ({
            chat: { ...s.chat, selectedSpaceId: spaceId, selectedChannelId: channelId, focusedThreadId: null },
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

    getDisplayMessages() {
        const s = baseStore.state;
        const pending = Object.values(s.messages.pending);
        const merged = [...s.messages.list, ...pending];
        merged.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
        return merged;
    },

    getChannelsForSpace(spaceId) {
        const all = baseStore.state.channels.list;
        if (!spaceId) return all;
        return all.filter(c => c.space_id === spaceId);
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
        const items = await syncApi.getSpaces();
        this.setSpaces(items);
        return items;
    },

    async loadChannels(syncApi) {
        baseStore.setState(s => ({ channels: { ...s.channels, loading: true } }));
        const items = await syncApi.getChannels();
        this.setChannels(items);
        return items;
    },

    async loadMessages(syncApi, channelId) {
        baseStore.setState(s => ({ messages: { ...s.messages, loading: true } }));
        const items = await syncApi.getMessages(channelId);
        this.setMessages(items);
        return items;
    },
};
