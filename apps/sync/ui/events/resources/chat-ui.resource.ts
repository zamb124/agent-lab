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
    extraReducer: (state, event) => {
        const s = state as SyncChatUiSlice;
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
                const p = event.payload as Record<string, any> | null;
                if (!p || typeof p.messageId !== 'string' || p.messageId === '') return state;
                const cur = s.selectedMessageIds;
                const next = cur.includes(p.messageId)
                    ? cur.filter((x: unknown) => x !== p.messageId)
                    : [...cur, p.messageId];
                return { ...s, selectedMessageIds: Object.freeze(next) };
            }
            case 'sync/chat_ui/selection_cleared':
                return { ...s, selectionMode: false, selectedMessageIds: Object.freeze([]) };
            case 'sync/chat_ui/deletion_started': {
                const p = event.payload as Record<string, any> | null;
                if (!p || !Array.isArray(p.messageIds) || p.messageIds.length === 0) return state;
                const cur = s.deletingMessageIds;
                const seen = new Set(cur);
                const merged = [...cur];
                for (const id of p.messageIds as unknown[]) {
                    if (typeof id === 'string' && id !== '' && !seen.has(id)) {
                        merged.push(id);
                    }
                }
                return { ...s, deletingMessageIds: Object.freeze(merged) };
            }
            case 'sync/chat_ui/deletion_finished': {
                const p = event.payload as Record<string, any> | null;
                if (!p || !Array.isArray(p.messageIds) || p.messageIds.length === 0) return state;
                const remove = new Set(p.messageIds as unknown[]);
                return {
                    ...s,
                    deletingMessageIds: Object.freeze(s.deletingMessageIds.filter((x: unknown) => !remove.has(x))),
                };
            }
            case 'sync/chat_ui/forward_opened': {
                const p = event.payload as Record<string, any> | null;
                if (!p || !p.message) return state;
                return { ...s, forwardModal: Object.freeze({ open: true, message: p.message }) };
            }
            case 'sync/chat_ui/forward_closed':
                return { ...s, forwardModal: null };
            case 'sync/chat_ui/pinned_index_set': {
                const p = event.payload as Record<string, any> | null;
                if (!p || typeof p.index !== 'number') return state;
                return { ...s, pinnedNavigateIndex: p.index };
            }
            case 'sync/chat_ui/section_toggled': {
                const p = event.payload as Record<string, any> | null;
                if (!p || typeof p.section !== 'string') return state;
                if (!Object.prototype.hasOwnProperty.call(EMPTY_SECTIONS, p.section)) return state;
                const cur = s.sidebarSectionOpen;
                const next = { ...cur, [p.section]: !cur[p.section] };
                return { ...s, sidebarSectionOpen: Object.freeze(next) };
            }
            case 'sync/chat_ui/section_hydrated': {
                const p = event.payload as Record<string, any> | null;
                if (!p || !p.sections || typeof p.sections !== 'object') return state;
                const sections = p.sections as Record<string, unknown>;
                const next = { ...s.sidebarSectionOpen };
                for (const key of Object.keys(EMPTY_SECTIONS)) {
                    if (typeof sections[key] === 'boolean') next[key] = sections[key] as boolean;
                }
                return { ...s, sidebarSectionOpen: Object.freeze(next) };
            }
            case 'sync/chat_ui/sidebar_search_set': {
                const p = event.payload as Record<string, any> | null;
                if (!p || typeof p.query !== 'string') return state;
                return { ...s, sidebarSearchQuery: p.query };
            }
            case 'sync/chat_ui/sidebar_search_scope_set': {
                const p = event.payload as Record<string, any> | null;
                if (!p || typeof p.scope !== 'string') return state;
                if (p.scope !== 'all' && p.scope !== 'groups' && p.scope !== 'direct') return state;
                return { ...s, sidebarSearchScope: p.scope };
            }
            default:
                return state;
        }
    },
});
