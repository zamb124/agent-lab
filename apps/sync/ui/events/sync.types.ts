/**
 * Типы контроллеров и slice Sync UI.
 *
 * Динамические actions фабрик (`useSlice`/`useOp`/`useResource`) видны на
 * контроллере только через index-signature `[action: string]: unknown` —
 * не вызываемы без сужения. Здесь — типизированные интерфейсы контроллеров
 * и shape slice'ов, чтобы компоненты не размножали `Record<string, unknown>`-касты.
 */

import type {
    OpController,
    ResourceController,
    SliceController,
} from '@platform/lib/base/use-resource.js';
import type {
    ResourceCollectionSlice,
    ResourceItem,
} from '@platform/lib/events/factories/resource-collection.js';
import type { ChannelRead } from '@platform/lib/events/wire/sync.gen.js';

export type SyncAction = (payload?: unknown) => void;

/** Элементы sync-ресурсов (канал/сообщение/участник) — свободная форма payload. */
export type SyncItem = ResourceItem;

// ============================================================================
// sync/chat_ui (chat-ui.resource.ts)
// ============================================================================

export interface SyncChatUiSlice extends Record<string, unknown> {
    selectionMode: boolean;
    selectedMessageIds: readonly unknown[];
    deletingMessageIds: readonly unknown[];
    forwardModal: unknown;
    pinnedNavigateIndex: number;
    sidebarSectionOpen: Readonly<Record<string, boolean>>;
    sidebarSearchQuery: string;
    sidebarSearchScope: string;
}


// ============================================================================
// sync/messages_store (messages.resource.ts)
// ============================================================================

/** Данные ленты сообщений одного канала внутри messages_store. */
export interface SyncChannelMessagesData extends Record<string, unknown> {
    items: readonly Record<string, unknown>[];
    pendingByLocalId: Readonly<Record<string, Record<string, unknown>>>;
    loading: boolean;
    loadingOlder: boolean;
    loadingNewer: boolean;
    error: unknown;
    pagination: {
        hasOlder: boolean;
        oldestCursor: string | null;
        hasNewer: boolean;
        newestCursor: string | null;
    };
}

export interface SyncMessagesStoreSlice extends Record<string, unknown> {
    byChannelId: Readonly<Record<string, SyncChannelMessagesData>>;
    replyToMessageId: string | null;
    editMessageId: string | null;
    contextMenuTarget: unknown;
    flashMessageId: string | null;
    flashSeq: number;
}


// ============================================================================
// sync/call_ui (calls.resource.ts)
// ============================================================================

export interface SyncCallUiSlice extends Record<string, unknown> {
    activeCall: Record<string, unknown> | null;
    incomingCall: Record<string, unknown> | null;
    overlayMinimized: boolean;
    bannerHangupGuardUntil: number;
    overlayChatOpen: boolean;
    recordingStatus: string;
    recordingError: unknown;
    activeCallChannels: Readonly<Record<string, { call_id: string; call_type: string }>>;
    callParticipants: Readonly<Record<string, readonly string[]>>;
    lastSignal: unknown;
}


// ============================================================================
// sync/presence (presence.resource.ts)
// ============================================================================

export interface SyncPresenceSlice extends Record<string, unknown> {
    typingByChannel: Readonly<Record<string, Readonly<Record<string, { thread_id: string | null; ts: number }>>>>;
}

// ============================================================================
// sync/call_prefs (call-prefs.resource.ts)
// ============================================================================

export interface SyncCallPrefsSlice extends Record<string, unknown> {
    cameraEnabled: boolean;
    noiseSuppression: boolean;
    echoCancellation: boolean;
    autoGainControl: boolean;
    deviceIds: Readonly<{ audioinput: string; videoinput: string; audiooutput: string }>;
    hydrated: boolean;
}


// ============================================================================
// sync/threads (threads.resource.ts)
// ============================================================================

export interface SyncThreadsSlice extends ResourceCollectionSlice {
    selectedThreadId: string | null;
    byChannelId: Readonly<Record<string, readonly SyncItem[]>>;
}


// ============================================================================
// Общие alias для `useOp`/`useResource` без специальных actions.
// ============================================================================

// ============================================================================
// sync/channels (channels.resource.ts)
// ============================================================================

export interface SyncChannelsSlice extends ResourceCollectionSlice<ChannelRead> {
    selectedChannelId: string | null;
    readByChannelUser: Readonly<Record<string, Readonly<Record<string, string>>>>;
    typingByChannel: Readonly<Record<string, Readonly<Record<string, { thread_id: string | null; ts: number }>>>>;
    membersByChannel: Readonly<Record<string, readonly SyncItem[]>>;
}


