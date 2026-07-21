/**
 * Слайс mail (кроссервисный, как calendar).
 *
 * state.mail:
 *   bindings, activeMailboxBindingId, connection, folder, folders,
 *   missingStandardRoles, messages, selectedUid, selectedThreadId,
 *   selectedThreadMessages, selectedMessage,
 *   loading, messageLoading, sending, adminMode, companyBindings, compose, pendingOpenUid,
 *   errorMessage
 */

export const MAIL_EVENTS = Object.freeze({
    BOOTSTRAP_REQUESTED: 'mail/session/bootstrap_requested',
    BINDINGS_LOAD_REQUESTED: 'mail/bindings/load_requested',
    BINDINGS_LOADED: 'mail/bindings/loaded',
    BINDINGS_LOAD_FAILED: 'mail/bindings/load_failed',
    COMPANY_BINDINGS_LOAD_REQUESTED: 'mail/company_bindings/load_requested',
    COMPANY_BINDINGS_LOADED: 'mail/company_bindings/loaded',
    COMPANY_BINDINGS_LOAD_FAILED: 'mail/company_bindings/load_failed',
    CONNECTION_LOAD_REQUESTED: 'mail/connection/load_requested',
    CONNECTION_LOADED: 'mail/connection/loaded',
    CONNECTION_LOAD_FAILED: 'mail/connection/load_failed',
    CONNECTION_SAVE_REQUESTED: 'mail/connection/save_requested',
    CONNECTION_SAVED: 'mail/connection/saved',
    CONNECTION_SAVE_FAILED: 'mail/connection/save_failed',
    BINDING_CREATE_REQUESTED: 'mail/binding/create_requested',
    BINDING_CREATED: 'mail/binding/created',
    BINDING_CREATE_FAILED: 'mail/binding/create_failed',
    BINDING_PATCH_REQUESTED: 'mail/binding/patch_requested',
    BINDING_PATCHED: 'mail/binding/patched',
    BINDING_PATCH_FAILED: 'mail/binding/patch_failed',
    BINDING_DELETE_REQUESTED: 'mail/binding/delete_requested',
    BINDING_DELETED: 'mail/binding/deleted',
    BINDING_DELETE_FAILED: 'mail/binding/delete_failed',
    DEFAULT_SET_REQUESTED: 'mail/binding/default_set_requested',
    DEFAULT_SET: 'mail/binding/default_set',
    DEFAULT_SET_FAILED: 'mail/binding/default_set_failed',
    MAILBOX_SELECT: 'mail/mailbox/select',
    FOLDER_SELECT: 'mail/folder/select',
    FOLDERS_LOAD_REQUESTED: 'mail/folders/load_requested',
    FOLDERS_LOADED: 'mail/folders/loaded',
    FOLDERS_LOAD_FAILED: 'mail/folders/load_failed',
    FOLDERS_ENSURE_REQUESTED: 'mail/folders/ensure_requested',
    FOLDERS_ENSURE_FAILED: 'mail/folders/ensure_failed',
    SYNC_REQUESTED: 'mail/sync/requested',
    SYNC_ACCEPTED: 'mail/sync/accepted',
    SYNC_FAILED: 'mail/sync/failed',
    MESSAGES_LOAD_REQUESTED: 'mail/messages/load_requested',
    MESSAGES_LOADED: 'mail/messages/loaded',
    MESSAGES_LOAD_FAILED: 'mail/messages/load_failed',
    THREAD_SELECT: 'mail/thread/select',
    THREAD_LOAD_REQUESTED: 'mail/thread/load_requested',
    THREAD_LOADED: 'mail/thread/loaded',
    THREAD_LOAD_FAILED: 'mail/thread/load_failed',
    MESSAGE_SELECT: 'mail/message/select',
    MESSAGE_LOAD_REQUESTED: 'mail/message/load_requested',
    MESSAGE_LOADED: 'mail/message/loaded',
    MESSAGE_LOAD_FAILED: 'mail/message/load_failed',
    MESSAGE_MARK_UNSEEN_REQUESTED: 'mail/message/mark_unseen_requested',
    MESSAGE_MARK_UNSEEN_COMPLETED: 'mail/message/mark_unseen_completed',
    MESSAGE_MARK_UNSEEN_FAILED: 'mail/message/mark_unseen_failed',
    OPEN_FROM_NOTIFICATION: 'mail/session/open_from_notification',
    COMPOSE_DRAFT_SET: 'mail/compose/draft_set',
    MESSAGE_SEND_REQUESTED: 'mail/message/send_requested',
    MESSAGE_SENT: 'mail/message/sent',
    MESSAGE_SEND_FAILED: 'mail/message/send_failed',
    ADMIN_MODE_SET: 'mail/admin/mode_set',
    HEALTHCHECK_REQUESTED: 'mail/connection/healthcheck_requested',
    HEALTHCHECK_COMPLETED: 'mail/connection/healthcheck_completed',
    HEALTHCHECK_FAILED: 'mail/connection/healthcheck_failed',
    MESSAGE_UPSERTED: 'mail/message/upserted',
    MESSAGE_MOVED: 'mail/message/moved',
    MESSAGE_REMOVED: 'mail/message/removed',
    MESSAGE_SEND_SUCCEEDED: 'mail/message/send_succeeded',
    MESSAGE_TRASH_REQUESTED: 'mail/message/trash_requested',
    MESSAGE_TRASH_COMPLETED: 'mail/message/trash_completed',
    MESSAGE_TRASH_FAILED: 'mail/message/trash_failed',
    MESSAGE_ARCHIVE_REQUESTED: 'mail/message/archive_requested',
    MESSAGE_ARCHIVE_COMPLETED: 'mail/message/archive_completed',
    MESSAGE_ARCHIVE_FAILED: 'mail/message/archive_failed',
    MESSAGE_DELETE_REQUESTED: 'mail/message/delete_requested',
    MESSAGE_DELETE_COMPLETED: 'mail/message/delete_completed',
    MESSAGE_DELETE_FAILED: 'mail/message/delete_failed',
    MESSAGE_STAR_REQUESTED: 'mail/message/star_requested',
    MESSAGE_STAR_COMPLETED: 'mail/message/star_completed',
    MESSAGE_STAR_FAILED: 'mail/message/star_failed',
    MESSAGES_SEARCH_REQUESTED: 'mail/messages/search_requested',
    MESSAGES_LOAD_MORE_REQUESTED: 'mail/messages/load_more_requested',
    MESSAGES_APPEND_LOADED: 'mail/messages/append_loaded',
    DRAFT_SAVE_REQUESTED: 'mail/draft/save_requested',
    DRAFT_SAVED: 'mail/draft/saved',
    DRAFT_SAVE_FAILED: 'mail/draft/save_failed',
    BINDING_MEMBERS_LOAD_REQUESTED: 'mail/binding_members/load_requested',
    BINDING_MEMBERS_LOADED: 'mail/binding_members/loaded',
    BINDING_MEMBERS_LOAD_FAILED: 'mail/binding_members/load_failed',
    BINDING_MEMBER_ADD_REQUESTED: 'mail/binding_member/add_requested',
    BINDING_MEMBER_ADDED: 'mail/binding_member/added',
    BINDING_MEMBER_ADD_FAILED: 'mail/binding_member/add_failed',
    BINDING_MEMBER_REMOVE_REQUESTED: 'mail/binding_member/remove_requested',
    BINDING_MEMBER_REMOVED: 'mail/binding_member/removed',
    BINDING_MEMBER_REMOVE_FAILED: 'mail/binding_member/remove_failed',
});

const EMPTY_COMPOSE = Object.freeze({
    to: '',
    subject: '',
    body: '',
    body_html: '',
    in_reply_to: null,
    references: null,
    attachments: Object.freeze([]),
});

export const initialMailState = Object.freeze({
    bindings: Object.freeze([]),
    companyBindings: Object.freeze([]),
    activeMailboxBindingId: null,
    connection: null,
    folder: null,
    folders: Object.freeze([]),
    missingStandardRoles: Object.freeze([]),
    messages: Object.freeze([]),
    messagesNextCursor: null,
    messagesHasMore: false,
    needsSync: false,
    syncInProgress: false,
    searchQuery: '',
    selectedUid: null,
    selectedThreadId: null,
    selectedThreadMessages: Object.freeze([]),
    selectedMessage: null,
    pendingOpenUid: null,
    loading: false,
    messageLoading: false,
    sending: false,
    adminMode: false,
    health: null,
    compose: EMPTY_COMPOSE,
    draftUid: null,
    bindingMembers: Object.freeze({}),
    errorMessage: null,
});

function requireItems(payload, eventType) {
    if (!payload || !Array.isArray(payload.items)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    return payload.items;
}

function adjustFolderUnseen(folders, folderName, delta) {
    if (typeof folderName !== 'string' || folderName.length === 0) {
        return folders;
    }
    if (!Array.isArray(folders) || delta === 0) {
        return folders;
    }
    return Object.freeze(folders.map((folder) => {
        if (folder.name !== folderName) {
            return folder;
        }
        const current = typeof folder.unseen_count === 'number' ? folder.unseen_count : 0;
        const next = Math.max(0, current + delta);
        return Object.freeze({ ...folder, unseen_count: next });
    }));
}

function pickActiveId(bindings, preferredId) {
    if (preferredId && bindings.some((b) => b.mailbox_binding_id === preferredId)) {
        return preferredId;
    }
    const def = bindings.find((b) => b.is_default === true);
    if (def) return def.mailbox_binding_id;
    if (bindings.length > 0) return bindings[0].mailbox_binding_id;
    return null;
}

function pickDefaultFolderName(folders, preferredName) {
    if (preferredName && folders.some((f) => f.name === preferredName && f.selectable !== false)) {
        return preferredName;
    }
    const inbox = folders.find((f) => f.role === 'inbox' && f.selectable !== false);
    if (inbox) return inbox.name;
    const first = folders.find((f) => f.selectable !== false);
    if (first) return first.name;
    return null;
}

function normalizeAttachments(raw) {
    if (!Array.isArray(raw)) {
        throw new Error('mail.compose: attachments must be an array');
    }
    return Object.freeze(raw.map((item) => {
        if (!item || typeof item !== 'object') {
            throw new Error('mail.compose: attachment must be object');
        }
        if (typeof item.filename !== 'string' || item.filename.length === 0) {
            throw new Error('mail.compose: attachment.filename required');
        }
        if (typeof item.content_type !== 'string' || item.content_type.length === 0) {
            throw new Error('mail.compose: attachment.content_type required');
        }
        if (typeof item.content_base64 !== 'string' || item.content_base64.length === 0) {
            throw new Error('mail.compose: attachment.content_base64 required');
        }
        if (typeof item.size !== 'number') {
            throw new Error('mail.compose: attachment.size required');
        }
        return Object.freeze({
            filename: item.filename,
            content_type: item.content_type,
            content_base64: item.content_base64,
            size: item.size,
        });
    }));
}

export function mailReducer(state = initialMailState, event) {
    switch (event.type) {
        case MAIL_EVENTS.BINDINGS_LOAD_REQUESTED:
        case MAIL_EVENTS.FOLDERS_LOAD_REQUESTED:
        case MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED:
        case MAIL_EVENTS.MESSAGES_LOAD_REQUESTED:
        case MAIL_EVENTS.CONNECTION_LOAD_REQUESTED:
        case MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED:
            return { ...state, loading: true, errorMessage: null };
        case MAIL_EVENTS.MESSAGE_LOAD_REQUESTED:
            return {
                ...state,
                messageLoading: true,
                selectedMessage: null,
                errorMessage: null,
            };
        case MAIL_EVENTS.BINDINGS_LOADED: {
            const items = requireItems(event.payload, event.type);
            const activeMailboxBindingId = pickActiveId(items, state.activeMailboxBindingId);
            return {
                ...state,
                loading: false,
                bindings: items,
                activeMailboxBindingId,
            };
        }
        case MAIL_EVENTS.BINDINGS_LOAD_FAILED:
        case MAIL_EVENTS.FOLDERS_LOAD_FAILED:
        case MAIL_EVENTS.FOLDERS_ENSURE_FAILED:
        case MAIL_EVENTS.MESSAGES_LOAD_FAILED:
        case MAIL_EVENTS.CONNECTION_LOAD_FAILED:
        case MAIL_EVENTS.COMPANY_BINDINGS_LOAD_FAILED:
        case MAIL_EVENTS.CONNECTION_SAVE_FAILED:
        case MAIL_EVENTS.BINDING_CREATE_FAILED:
        case MAIL_EVENTS.BINDING_PATCH_FAILED:
        case MAIL_EVENTS.BINDING_DELETE_FAILED:
        case MAIL_EVENTS.DEFAULT_SET_FAILED:
        case MAIL_EVENTS.MESSAGE_SEND_FAILED:
        case MAIL_EVENTS.HEALTHCHECK_FAILED:
        case MAIL_EVENTS.SYNC_FAILED:
        case MAIL_EVENTS.MESSAGE_TRASH_FAILED:
        case MAIL_EVENTS.MESSAGE_ARCHIVE_FAILED:
        case MAIL_EVENTS.MESSAGE_DELETE_FAILED:
        case MAIL_EVENTS.MESSAGE_STAR_FAILED:
        case MAIL_EVENTS.DRAFT_SAVE_FAILED:
        case MAIL_EVENTS.BINDING_MEMBERS_LOAD_FAILED:
        case MAIL_EVENTS.BINDING_MEMBER_ADD_FAILED:
        case MAIL_EVENTS.BINDING_MEMBER_REMOVE_FAILED:
            return {
                ...state,
                loading: false,
                sending: false,
                syncInProgress: false,
                errorMessage: (
                    event.payload && typeof event.payload.message === 'string'
                        ? event.payload.message
                        : (event.payload && typeof event.payload.error_detail === 'string'
                            ? event.payload.error_detail
                            : 'mail error')
                ),
            };
        case MAIL_EVENTS.MESSAGE_LOAD_FAILED:
            return {
                ...state,
                messageLoading: false,
                errorMessage: event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'mail error',
            };
        case MAIL_EVENTS.COMPANY_BINDINGS_LOADED:
            return {
                ...state,
                loading: false,
                companyBindings: requireItems(event.payload, event.type),
            };
        case MAIL_EVENTS.CONNECTION_LOADED:
        case MAIL_EVENTS.CONNECTION_SAVED:
            return {
                ...state,
                loading: false,
                connection: event.payload && event.payload.connection
                    ? event.payload.connection
                    : null,
            };
        case MAIL_EVENTS.OPEN_FROM_NOTIFICATION: {
            const id = event.payload && event.payload.mailbox_binding_id;
            const uid = event.payload && event.payload.uid;
            if (typeof id !== 'string' || id.length === 0) {
                throw new Error('mail/open_from_notification: mailbox_binding_id required');
            }
            if (typeof uid !== 'string' || uid.length === 0) {
                throw new Error('mail/open_from_notification: uid required');
            }
            return {
                ...state,
                activeMailboxBindingId: id,
                pendingOpenUid: uid,
                selectedUid: uid,
                selectedThreadId: null,
                selectedThreadMessages: Object.freeze([]),
                selectedMessage: null,
                folder: null,
                folders: Object.freeze([]),
                missingStandardRoles: Object.freeze([]),
                messages: Object.freeze([]),
                errorMessage: null,
            };
        }
        case MAIL_EVENTS.MAILBOX_SELECT: {
            const id = event.payload && event.payload.mailbox_binding_id;
            if (typeof id !== 'string' || id.length === 0) return state;
            return {
                ...state,
                activeMailboxBindingId: id,
                pendingOpenUid: null,
                folder: null,
                folders: Object.freeze([]),
                missingStandardRoles: Object.freeze([]),
                selectedUid: null,
                selectedThreadId: null,
                selectedThreadMessages: Object.freeze([]),
                selectedMessage: null,
                messages: Object.freeze([]),
                messagesNextCursor: null,
                messagesHasMore: false,
                needsSync: false,
                searchQuery: '',
            };
        }
        case MAIL_EVENTS.FOLDERS_LOADED: {
            const payload = event.payload;
            if (!payload || !Array.isArray(payload.folders)) {
                throw new Error(`${event.type}: payload.folders must be an array`);
            }
            const folders = payload.folders;
            const missing = Array.isArray(payload.missing_standard_roles)
                ? payload.missing_standard_roles
                : [];
            const folder = pickDefaultFolderName(folders, state.folder);
            const keepList = folder === state.folder && state.pendingOpenUid == null;
            return {
                ...state,
                loading: false,
                folders: Object.freeze(folders),
                missingStandardRoles: Object.freeze(missing),
                folder,
                selectedUid: keepList ? state.selectedUid : state.pendingOpenUid,
                selectedThreadId: keepList ? state.selectedThreadId : null,
                selectedThreadMessages: keepList ? state.selectedThreadMessages : Object.freeze([]),
                selectedMessage: keepList ? state.selectedMessage : null,
                messages: keepList ? state.messages : Object.freeze([]),
            };
        }
        case MAIL_EVENTS.FOLDER_SELECT: {
            const folder = event.payload && event.payload.folder;
            if (typeof folder !== 'string' || folder.length === 0) return state;
            return {
                ...state,
                folder,
                pendingOpenUid: null,
                selectedUid: null,
                selectedThreadId: null,
                selectedThreadMessages: Object.freeze([]),
                selectedMessage: null,
                messageLoading: false,
                messages: Object.freeze([]),
                messagesNextCursor: null,
                messagesHasMore: false,
                searchQuery: '',
            };
        }
        case MAIL_EVENTS.MESSAGES_LOADED: {
            const items = requireItems(event.payload, event.type);
            return {
                ...state,
                loading: false,
                messages: Object.freeze(items),
                messagesNextCursor: typeof event.payload.next_cursor === 'string'
                    ? event.payload.next_cursor
                    : null,
                messagesHasMore: event.payload.has_more === true,
                needsSync: event.payload.needs_sync === true,
            };
        }
        case MAIL_EVENTS.MESSAGES_APPEND_LOADED: {
            const items = requireItems(event.payload, event.type);
            const existingUids = new Set(state.messages.map((item) => item.uid));
            const merged = [
                ...state.messages,
                ...items.filter((item) => item && typeof item.uid === 'string' && !existingUids.has(item.uid)),
            ];
            return {
                ...state,
                loading: false,
                messages: Object.freeze(merged),
                messagesNextCursor: typeof event.payload.next_cursor === 'string'
                    ? event.payload.next_cursor
                    : null,
                messagesHasMore: event.payload.has_more === true,
            };
        }
        case MAIL_EVENTS.SYNC_REQUESTED:
            return { ...state, syncInProgress: true, errorMessage: null };
        case MAIL_EVENTS.SYNC_ACCEPTED:
            return { ...state, syncInProgress: true, needsSync: false };
        case MAIL_EVENTS.THREAD_SELECT:
        case MAIL_EVENTS.MESSAGE_SELECT: {
            const uid = event.payload && event.payload.uid;
            if (typeof uid !== 'string' || uid.length === 0) return state;
            const threadId = event.payload && typeof event.payload.thread_id === 'string'
                ? event.payload.thread_id
                : null;
            return {
                ...state,
                selectedUid: uid,
                selectedThreadId: threadId,
                selectedThreadMessages: Object.freeze([]),
                selectedMessage: null,
                messageLoading: true,
            };
        }
        case MAIL_EVENTS.THREAD_LOADED: {
            const thread = event.payload && event.payload.thread
                ? event.payload.thread
                : null;
            if (!thread || !Array.isArray(thread.items)) {
                throw new Error(`${event.type}: payload.thread.items must be an array`);
            }
            const items = thread.items;
            const threadId = typeof thread.thread_id === 'string' ? thread.thread_id : null;
            const folderName = state.folder;
            const inboxUnreadUids = new Set(
                items
                    .filter((item) => (
                        item
                        && item.folder === folderName
                        && typeof item.uid === 'string'
                    ))
                    .map((item) => item.uid),
            );
            let newlyRead = 0;
            const messages = state.messages.map((item) => {
                if (!inboxUnreadUids.has(item.uid) || item.unread !== true) {
                    return item;
                }
                newlyRead += 1;
                return Object.freeze({ ...item, unread: false });
            });
            const focusUid = typeof state.selectedUid === 'string' ? state.selectedUid : null;
            const focus = focusUid
                ? items.find((item) => item.uid === focusUid) || items[items.length - 1]
                : items[items.length - 1];
            const selectedMessage = focus
                ? Object.freeze({ ...focus, unread: false })
                : null;
            const threadMessages = items.map((item) => {
                if (
                    item
                    && item.folder === folderName
                    && item.unread === true
                ) {
                    return Object.freeze({ ...item, unread: false });
                }
                return Object.freeze(item);
            });
            return {
                ...state,
                messageLoading: false,
                pendingOpenUid: null,
                selectedThreadId: threadId,
                selectedThreadMessages: Object.freeze(threadMessages),
                selectedMessage,
                selectedUid: selectedMessage && typeof selectedMessage.uid === 'string'
                    ? selectedMessage.uid
                    : state.selectedUid,
                messages: Object.freeze(messages),
                folders: newlyRead > 0
                    ? adjustFolderUnseen(state.folders, state.folder, -newlyRead)
                    : state.folders,
            };
        }
        case MAIL_EVENTS.THREAD_LOAD_FAILED:
        case MAIL_EVENTS.MESSAGE_LOAD_FAILED:
            return {
                ...state,
                messageLoading: false,
                errorMessage: event.payload && event.payload.message
                    ? event.payload.message
                    : 'mail thread load failed',
            };
        case MAIL_EVENTS.MESSAGE_LOADED: {
            const loaded = event.payload && event.payload.message
                ? event.payload.message
                : null;
            const loadedUid = loaded && typeof loaded.uid === 'string' ? loaded.uid : null;
            const previous = loadedUid
                ? state.messages.find((item) => item.uid === loadedUid)
                : null;
            const wasUnread = Boolean(previous && previous.unread === true);
            const messages = loadedUid
                ? state.messages.map((item) => (
                    item.uid === loadedUid
                        ? Object.freeze({ ...item, unread: false })
                        : item
                ))
                : state.messages;
            return {
                ...state,
                messageLoading: false,
                pendingOpenUid: null,
                selectedMessage: loaded,
                selectedThreadMessages: loaded
                    ? Object.freeze([Object.freeze({ ...loaded, folder: state.folder })])
                    : Object.freeze([]),
                messages: Object.freeze(messages),
                folders: wasUnread
                    ? adjustFolderUnseen(state.folders, state.folder, -1)
                    : state.folders,
            };
        }
        case MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED: {
            const uid = event.payload && event.payload.uid;
            if (typeof uid !== 'string' || uid.length === 0) return state;
            const previous = state.messages.find((item) => item.uid === uid);
            const alreadyUnread = Boolean(previous && previous.unread === true);
            const messages = state.messages.map((item) => (
                item.uid === uid
                    ? Object.freeze({ ...item, unread: true })
                    : item
            ));
            const selectedMessage = state.selectedMessage && state.selectedMessage.uid === uid
                ? Object.freeze({ ...state.selectedMessage, unread: true })
                : state.selectedMessage;
            const selectedThreadMessages = state.selectedThreadMessages.map((item) => (
                item.uid === uid
                    ? Object.freeze({ ...item, unread: true })
                    : item
            ));
            return {
                ...state,
                messages: Object.freeze(messages),
                selectedMessage,
                selectedThreadMessages: Object.freeze(selectedThreadMessages),
                folders: alreadyUnread
                    ? state.folders
                    : adjustFolderUnseen(state.folders, state.folder, 1),
            };
        }
        case MAIL_EVENTS.COMPOSE_DRAFT_SET: {
            const draft = event.payload;
            if (!draft || typeof draft !== 'object') return state;
            return {
                ...state,
                compose: Object.freeze({
                    to: typeof draft.to === 'string' ? draft.to : state.compose.to,
                    subject: typeof draft.subject === 'string' ? draft.subject : state.compose.subject,
                    body: typeof draft.body === 'string' ? draft.body : state.compose.body,
                    body_html: typeof draft.body_html === 'string'
                        ? draft.body_html
                        : state.compose.body_html,
                    in_reply_to: Object.prototype.hasOwnProperty.call(draft, 'in_reply_to')
                        ? draft.in_reply_to
                        : state.compose.in_reply_to,
                    references: Object.prototype.hasOwnProperty.call(draft, 'references')
                        ? draft.references
                        : state.compose.references,
                    attachments: Object.prototype.hasOwnProperty.call(draft, 'attachments')
                        ? normalizeAttachments(draft.attachments)
                        : state.compose.attachments,
                }),
            };
        }
        case MAIL_EVENTS.MESSAGE_SEND_REQUESTED:
            return { ...state, sending: true, errorMessage: null };
        case MAIL_EVENTS.MESSAGE_SENT:
            return {
                ...state,
                sending: false,
                compose: EMPTY_COMPOSE,
            };
        case MAIL_EVENTS.DEFAULT_SET: {
            const binding = event.payload && event.payload.binding;
            if (!binding || typeof binding.mailbox_binding_id !== 'string') return state;
            const ownerUserId = typeof binding.user_id === 'string' ? binding.user_id : null;
            const applyDefaultFlags = (items) => items.map((item) => {
                if (ownerUserId !== null) {
                    if (item.user_id !== ownerUserId) return item;
                    return {
                        ...item,
                        is_default: item.mailbox_binding_id === binding.mailbox_binding_id,
                    };
                }
                return {
                    ...item,
                    is_default: item.mailbox_binding_id === binding.mailbox_binding_id,
                };
            });
            const bindings = applyDefaultFlags(state.bindings);
            const companyBindings = applyDefaultFlags(state.companyBindings);
            const mine = state.bindings.some(
                (item) => item.mailbox_binding_id === binding.mailbox_binding_id,
            );
            return {
                ...state,
                bindings,
                companyBindings,
                activeMailboxBindingId: mine
                    ? binding.mailbox_binding_id
                    : state.activeMailboxBindingId,
            };
        }
        case MAIL_EVENTS.BINDING_CREATED:
        case MAIL_EVENTS.BINDING_PATCHED: {
            const binding = event.payload && event.payload.binding;
            if (!binding || typeof binding.mailbox_binding_id !== 'string') return state;
            const exists = state.companyBindings.some(
                (item) => item.mailbox_binding_id === binding.mailbox_binding_id,
            );
            const companyBindings = exists
                ? state.companyBindings.map((item) => (
                    item.mailbox_binding_id === binding.mailbox_binding_id ? binding : item
                ))
                : [...state.companyBindings, binding];
            const bindingsExist = state.bindings.some(
                (item) => item.mailbox_binding_id === binding.mailbox_binding_id,
            );
            const bindings = bindingsExist
                ? state.bindings.map((item) => (
                    item.mailbox_binding_id === binding.mailbox_binding_id ? binding : item
                ))
                : state.bindings;
            return { ...state, loading: false, companyBindings, bindings };
        }
        case MAIL_EVENTS.BINDING_DELETED: {
            const id = event.payload && event.payload.mailbox_binding_id;
            if (typeof id !== 'string') return state;
            const bindings = state.bindings.filter((item) => item.mailbox_binding_id !== id);
            const companyBindings = state.companyBindings.filter(
                (item) => item.mailbox_binding_id !== id,
            );
            const activeMailboxBindingId = state.activeMailboxBindingId === id
                ? pickActiveId(bindings, null)
                : state.activeMailboxBindingId;
            return {
                ...state,
                loading: false,
                bindings,
                companyBindings,
                activeMailboxBindingId,
            };
        }
        case MAIL_EVENTS.ADMIN_MODE_SET:
            return {
                ...state,
                adminMode: Boolean(event.payload && event.payload.open),
            };
        case MAIL_EVENTS.HEALTHCHECK_COMPLETED:
            return {
                ...state,
                loading: false,
                health: event.payload && event.payload.health ? event.payload.health : null,
            };
        case MAIL_EVENTS.MESSAGE_UPSERTED: {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object') {
                throw new Error('mail/message/upserted: payload required');
            }
            const mailboxBindingId = payload.mailbox_binding_id;
            const folder = payload.folder;
            const listItem = payload.list_item;
            if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
                throw new Error('mail/message/upserted: mailbox_binding_id required');
            }
            if (mailboxBindingId !== state.activeMailboxBindingId) {
                return state;
            }
            const unreadDelta = typeof payload.unread_delta === 'number' ? payload.unread_delta : 0;
            let messages = state.messages;
            if (
                typeof folder === 'string'
                && folder === state.folder
                && listItem
                && typeof listItem === 'object'
                && typeof listItem.uid === 'string'
            ) {
                const without = state.messages.filter((item) => item.uid !== listItem.uid);
                messages = Object.freeze([listItem, ...without]);
            } else if (
                typeof payload.uid === 'string'
                && typeof payload.flagged === 'boolean'
            ) {
                messages = Object.freeze(state.messages.map((item) => (
                    item.uid === payload.uid
                        ? Object.freeze({ ...item, flagged: payload.flagged })
                        : item
                )));
            }
            return {
                ...state,
                messages,
                syncInProgress: false,
                folders: adjustFolderUnseen(
                    state.folders,
                    typeof folder === 'string' ? folder : state.folder,
                    unreadDelta,
                ),
            };
        }
        case MAIL_EVENTS.MESSAGE_REMOVED:
        case MAIL_EVENTS.MESSAGE_TRASH_COMPLETED:
        case MAIL_EVENTS.MESSAGE_ARCHIVE_COMPLETED:
        case MAIL_EVENTS.MESSAGE_DELETE_COMPLETED: {
            const payload = event.payload || {};
            const uid = typeof payload.uid === 'string' ? payload.uid : null;
            if (!uid) return state;
            const messages = state.messages.filter((item) => item.uid !== uid);
            const clearSelected = state.selectedUid === uid;
            return {
                ...state,
                messages: Object.freeze(messages),
                selectedUid: clearSelected ? null : state.selectedUid,
                selectedThreadId: clearSelected ? null : state.selectedThreadId,
                selectedThreadMessages: clearSelected
                    ? Object.freeze([])
                    : state.selectedThreadMessages,
                selectedMessage: clearSelected ? null : state.selectedMessage,
            };
        }
        case MAIL_EVENTS.MESSAGE_MOVED: {
            const payload = event.payload || {};
            const uid = typeof payload.uid === 'string' ? payload.uid : null;
            if (!uid) return state;
            return {
                ...state,
                messages: Object.freeze(state.messages.filter((item) => item.uid !== uid)),
            };
        }
        case MAIL_EVENTS.MESSAGE_STAR_COMPLETED: {
            const uid = event.payload && event.payload.uid;
            const flagged = event.payload && event.payload.flagged === true;
            if (typeof uid !== 'string') return state;
            return {
                ...state,
                messages: Object.freeze(state.messages.map((item) => (
                    item.uid === uid ? Object.freeze({ ...item, flagged }) : item
                ))),
                selectedMessage: state.selectedMessage && state.selectedMessage.uid === uid
                    ? Object.freeze({ ...state.selectedMessage, flagged })
                    : state.selectedMessage,
            };
        }
        case MAIL_EVENTS.DRAFT_SAVED: {
            const uid = event.payload && event.payload.uid;
            return {
                ...state,
                draftUid: typeof uid === 'string' ? uid : state.draftUid,
            };
        }
        case MAIL_EVENTS.BINDING_MEMBERS_LOADED: {
            const mailboxBindingId = event.payload && event.payload.mailbox_binding_id;
            const items = requireItems(event.payload, event.type);
            if (typeof mailboxBindingId !== 'string') return state;
            return {
                ...state,
                bindingMembers: Object.freeze({
                    ...state.bindingMembers,
                    [mailboxBindingId]: Object.freeze(items),
                }),
            };
        }
        case MAIL_EVENTS.BINDING_MEMBER_ADDED: {
            const member = event.payload && event.payload.member;
            if (!member || typeof member.mailbox_binding_id !== 'string') return state;
            const current = Array.isArray(state.bindingMembers[member.mailbox_binding_id])
                ? state.bindingMembers[member.mailbox_binding_id]
                : [];
            const without = current.filter((item) => item.user_id !== member.user_id);
            return {
                ...state,
                bindingMembers: Object.freeze({
                    ...state.bindingMembers,
                    [member.mailbox_binding_id]: Object.freeze([...without, member]),
                }),
            };
        }
        case MAIL_EVENTS.BINDING_MEMBER_REMOVED: {
            const mailboxBindingId = event.payload && event.payload.mailbox_binding_id;
            const userId = event.payload && event.payload.user_id;
            if (typeof mailboxBindingId !== 'string' || typeof userId !== 'string') return state;
            const current = Array.isArray(state.bindingMembers[mailboxBindingId])
                ? state.bindingMembers[mailboxBindingId]
                : [];
            return {
                ...state,
                bindingMembers: Object.freeze({
                    ...state.bindingMembers,
                    [mailboxBindingId]: Object.freeze(
                        current.filter((item) => item.user_id !== userId),
                    ),
                }),
            };
        }
        case MAIL_EVENTS.MESSAGE_SEND_SUCCEEDED:
            return { ...state, syncInProgress: false };
        default:
            return state;
    }
}

export const mailSlice = { reducer: mailReducer, initial: initialMailState };
