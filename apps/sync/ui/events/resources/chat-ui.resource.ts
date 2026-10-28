/**
 * UI чата Sync — UI-only state без HTTP/WS.
 *
 * Хранит локальное состояние интерфейса чата:
 *   - selectionMode / selectedMessageIds — режим выбора нескольких сообщений
 *     для пакетных действий (forward / delete);
 *   - deletingMessageIds — id сообщений, которые сейчас анимируются как
 *     удаляемые (для CSS-перехода до того, как backend пришлёт push delete);
 *   - forwardModal — { open, message } | null для модалки forward;
 *   - pinnedNavigateIndex — текущий индекс при цикле по pinned messages;
 *   - sidebarSectionOpen — состояние раскрытых секций sidebar (хранится в
 *     localStorage через sync-persist.effect.js);
 *   - sidebarSearchScope — фильтр списка чатов при поиске: все каналы и личные,
 *     только групповые каналы, только личные (direct) и контакты для нового DM.
 *
 * Все мутации — через actions слайс-контроллера (`useSlice('sync/chat_ui')`).
 */

import { createSlice } from '@platform/lib/events/index.js';
import type { SyncChatUiSlice } from '../sync.types.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function eventRecord(payload: unknown): Record<string, unknown> | null {
    return isPlainRecord(payload) ? payload : null;
}

const EMPTY_SECTIONS = Object.freeze({ spaces: true, channels: true, direct: true });

export const chatUiResource = createSlice({
    name: 'sync/chat_ui',
    extraInitial: {
        selectionMode: false,
        selectedMessageIds: Object.freeze([]),
        deletingMessageIds: Object.freeze([]),
        forwardModal: null,
        pinnedNavigateIndex: 0,
        sidebarSectionOpen: EMPTY_SECTIONS,
        sidebarSearchQuery: '',
        sidebarSearchScope: 'all',
    },
    extraEvents: {
        SELECTION_TOGGLED: 'selection_toggled',
        MESSAGE_SELECTION_TOGGLED: 'message_selection_toggled',
        SELECTION_CLEARED: 'selection_cleared',
        DELETION_STARTED: 'deletion_started',
        DELETION_FINISHED: 'deletion_finished',
        FORWARD_OPENED: 'forward_opened',
        FORWARD_CLOSED: 'forward_closed',
        PINNED_INDEX_SET: 'pinned_index_set',
        SECTION_TOGGLED: 'section_toggled',
        SECTION_HYDRATED: 'section_hydrated',
        SIDEBAR_SEARCH_SET: 'sidebar_search_set',
        SIDEBAR_SEARCH_SCOPE_SET: 'sidebar_search_scope_set',
    },
    actions: {
        toggleSelectionMode: 'selection_toggled',
        toggleMessageSelection: 'message_selection_toggled',
        clearSelection: 'selection_cleared',
        startDeletion: 'deletion_started',
        finishDeletion: 'deletion_finished',
        openForward: 'forward_opened',
        closeForward: 'forward_closed',
        setPinnedIndex: 'pinned_index_set',
        toggleSection: 'section_toggled',
        hydrateSections: 'section_hydrated',
        setSidebarSearch: 'sidebar_search_set',
        setSidebarSearchScope: 'sidebar_search_scope_set',
    },
    extraReducer: (state: SyncChatUiSlice, event) => {
        const s = state;
        switch (event.type) {
            case 'sync/context/company_cleared': {
                return {
                    ...s,
                    selectionMode: false,
                    selectedMessageIds: Object.freeze([]),
                    deletingMessageIds: Object.freeze([]),
                    forwardModal: null,
                    pinnedNavigateIndex: 0,
                    sidebarSearchQuery: '',
                    sidebarSearchScope: 'all',
                };
            }
            case 'sync/chat_ui/selection_toggled': {
                const next = !s.selectionMode;
                return {
                    ...s,
                    selectionMode: next,
                    selectedMessageIds: next ? s.selectedMessageIds : Object.freeze([]),
                };
            }
            case 'sync/chat_ui/message_selection_toggled': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.messageId !== 'string' || p.messageId === '') return state;
                const cur = s.selectedMessageIds;
                const next = cur.includes(p.messageId)
                    ? cur.filter((x: unknown) => x !== p.messageId)
                    : [...cur, p.messageId];
                return { ...s, selectedMessageIds: Object.freeze(next) };
            }
            case 'sync/chat_ui/selection_cleared':
                return { ...s, selectionMode: false, selectedMessageIds: Object.freeze([]) };
            case 'sync/chat_ui/deletion_started': {
                const p = eventRecord(event.payload);
                if (p === null || !Array.isArray(p.messageIds) || p.messageIds.length === 0) return state;
                const cur = s.deletingMessageIds;
                const seen = new Set(cur);
                const merged = [...cur];
                for (const id of p.messageIds) {
                    if (typeof id === 'string' && id !== '' && !seen.has(id)) {
                        merged.push(id);
                    }
                }
                return { ...s, deletingMessageIds: Object.freeze(merged) };
            }
            case 'sync/chat_ui/deletion_finished': {
                const p = eventRecord(event.payload);
                if (p === null || !Array.isArray(p.messageIds) || p.messageIds.length === 0) return state;
                const remove = new Set(p.messageIds);
                return {
                    ...s,
                    deletingMessageIds: Object.freeze(s.deletingMessageIds.filter((x: unknown) => !remove.has(x))),
                };
            }
            case 'sync/chat_ui/forward_opened': {
                const p = eventRecord(event.payload);
                if (p === null || p.message == null) return state;
                return { ...s, forwardModal: Object.freeze({ open: true, message: p.message }) };
            }
            case 'sync/chat_ui/forward_closed':
                return { ...s, forwardModal: null };
            case 'sync/chat_ui/pinned_index_set': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.index !== 'number') return state;
                return { ...s, pinnedNavigateIndex: p.index };
            }
            case 'sync/chat_ui/section_toggled': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.section !== 'string') return state;
                if (!Object.prototype.hasOwnProperty.call(EMPTY_SECTIONS, p.section)) return state;
                const cur = s.sidebarSectionOpen;
                const next = { ...cur, [p.section]: !cur[p.section] };
                return { ...s, sidebarSectionOpen: Object.freeze(next) };
            }
            case 'sync/chat_ui/section_hydrated': {
                const p = eventRecord(event.payload);
                if (p === null || !isPlainRecord(p.sections)) return state;
                const sections = p.sections;
                const next = { ...s.sidebarSectionOpen };
                for (const key of Object.keys(EMPTY_SECTIONS)) {
                    const value = sections[key];
                    if (typeof value === 'boolean') next[key] = value;
                }
                return { ...s, sidebarSectionOpen: Object.freeze(next) };
            }
            case 'sync/chat_ui/sidebar_search_set': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.query !== 'string') return state;
                return { ...s, sidebarSearchQuery: p.query };
            }
            case 'sync/chat_ui/sidebar_search_scope_set': {
                const p = eventRecord(event.payload);
                if (p === null || typeof p.scope !== 'string') return state;
                if (p.scope !== 'all' && p.scope !== 'groups' && p.scope !== 'direct') return state;
                return { ...s, sidebarSearchScope: p.scope };
            }
            default:
                return state;
        }
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'sync/chat_ui': typeof chatUiResource;
    }
}
