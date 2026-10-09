/**
 * Типы контроллеров и slice Sync UI.
 *
 * Динамические actions фабрик (`useSlice`/`useOp`/`useResource`) видны на
 * контроллере только через index-signature `[action: string]: unknown` —
 * не вызываемы без сужения. Здесь — типизированные интерфейсы контроллеров
 * и shape slice'ов, чтобы компоненты не размножали `Record<string, any>`-касты.
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

export interface SyncChatUiController extends SliceController {
    readonly value: SyncChatUiSlice | undefined;
    toggleSelectionMode: SyncAction;
    toggleMessageSelection: SyncAction;
    clearSelection: SyncAction;
    startDeletion: SyncAction;
    finishDeletion: SyncAction;
    openForward: SyncAction;
    closeForward: SyncAction;
    setPinnedIndex: SyncAction;
    toggleSection: SyncAction;
    hydrateSections: SyncAction;
    setSidebarSearch: SyncAction;
    setSidebarSearchScope: SyncAction;
}

// ============================================================================
// sync/messages_store (messages.resource.ts)
// ============================================================================

/** Данные ленты сообщений одного канала внутри messages_store. */
export interface SyncChannelMessagesData extends Record<string, unknown> {
    items: readonly Record<string, any>[];
    pendingByLocalId: Readonly<Record<string, Record<string, any>>>;
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

export interface SyncMessagesStoreController extends SliceController {
    readonly value: SyncMessagesStoreSlice | undefined;
    setReplyMode: SyncAction;
    setEditMode: SyncAction;
    showContextMenu: SyncAction;
    dismissContextMenu: SyncAction;
    addOptimistic: SyncAction;
    failOptimistic: SyncAction;
    resendOptimistic: SyncAction;
    flash: SyncAction;
    clearFlash: SyncAction;
    startInitial: SyncAction;
    loadedInitial: SyncAction;
    failInitial: SyncAction;
    startOlder: SyncAction;
    startNewer: SyncAction;
    loadedOlder: SyncAction;
    loadedNewer: SyncAction;
}

// ============================================================================
// sync/call_ui (calls.resource.ts)
// ============================================================================

export interface SyncCallUiSlice extends Record<string, unknown> {
    activeCall: Record<string, any> | null;
    incomingCall: Record<string, any> | null;
    overlayMinimized: boolean;
    bannerHangupGuardUntil: number;
    overlayChatOpen: boolean;
    recordingStatus: string;
    recordingError: unknown;
    activeCallChannels: Readonly<Record<string, { call_id: string; call_type: string }>>;
    callParticipants: Readonly<Record<string, readonly string[]>>;
    lastSignal: unknown;
}

export interface SyncCallUiController extends SliceController {
    readonly value: SyncCallUiSlice | undefined;
    openOverlay: SyncAction;
    minimizeOverlay: SyncAction;
    expandOverlay: SyncAction;
    closeOverlay: SyncAction;
    setOverlayChatOpen: SyncAction;
    dismissIncoming: SyncAction;
    setRecordingStatus: SyncAction;
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

export interface SyncCallPrefsController extends SliceController {
    readonly value: SyncCallPrefsSlice | undefined;
    setCamera: SyncAction;
    setNoiseSuppression: SyncAction;
    setEchoCancellation: SyncAction;
    setAutoGain: SyncAction;
    setDeviceId: SyncAction;
    setHydrated: SyncAction;
}

// ============================================================================
// sync/threads (threads.resource.ts)
// ============================================================================

export interface SyncThreadsSlice extends ResourceCollectionSlice {
    selectedThreadId: string | null;
    byChannelId: Readonly<Record<string, readonly SyncItem[]>>;
}

export interface SyncThreadsController extends ResourceController {
    readonly state: SyncThreadsSlice;
    openThread: SyncAction;
    closeThread: SyncAction;
}

// ============================================================================
// Общие alias для `useOp`/`useResource` без специальных actions.
// ============================================================================

// ============================================================================
// sync/channels (channels.resource.ts)
// ============================================================================

export interface SyncChannelsSlice extends ResourceCollectionSlice {
    selectedChannelId: string | null;
    readByChannelUser: Readonly<Record<string, Readonly<Record<string, string>>>>;
    typingByChannel: Readonly<Record<string, Readonly<Record<string, { thread_id: string | null; ts: number }>>>>;
    membersByChannel: Readonly<Record<string, readonly SyncItem[]>>;
}

export interface SyncChannelsController extends ResourceController {
    readonly state: SyncChannelsSlice;
    selectChannel: SyncAction;
    setOwnRead: SyncAction;
}

export type SyncOpController = OpController;
export type SyncResourceController = ResourceController;
