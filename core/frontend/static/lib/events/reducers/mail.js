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
            return {
                ...state,
                loading: false,
                sending: false,
                errorMessage: event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'mail error',
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
            };
        }
        case MAIL_EVENTS.MESSAGES_LOADED:
            return {
                ...state,
                loading: false,
                messages: requireItems(event.payload, event.type),
            };
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
            return {
                ...state,
                messageLoading: false,
                pendingOpenUid: null,
                selectedThreadId: threadId,
                selectedThreadMessages: Object.freeze(items.map((item) => Object.freeze(item))),
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
            const bindings = state.bindings.map((item) => ({
                ...item,
                is_default: item.mailbox_binding_id === binding.mailbox_binding_id,
            }));
            return {
                ...state,
                bindings,
                activeMailboxBindingId: binding.mailbox_binding_id,
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
            return {
                ...state,
                loading: false,
                companyBindings: state.companyBindings.filter(
                    (item) => item.mailbox_binding_id !== id,
                ),
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
        default:
            return state;
    }
}

export const mailSlice = { reducer: mailReducer, initial: initialMailState };
