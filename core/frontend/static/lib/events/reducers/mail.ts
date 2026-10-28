import { formatPlatformError } from '../../utils/platform-error-message.js';
import type { PlatformEvent } from '../contract.js';
import { isPlainRecord, payloadFields } from '../payload.js';

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
    PERSONAL_CONNECT_REQUESTED: 'mail/binding/personal_connect_requested',
    PERSONAL_CONNECT_FAILED: 'mail/binding/personal_connect_failed',
    PERSONAL_HEALTHCHECK_REQUESTED: 'mail/binding/personal_healthcheck_requested',
    PERSONAL_HEALTHCHECK_COMPLETED: 'mail/binding/personal_healthcheck_completed',
    PERSONAL_HEALTHCHECK_FAILED: 'mail/binding/personal_healthcheck_failed',
    BINDING_PATCH_REQUESTED: 'mail/binding/patch_requested',
    BINDING_PATCHED: 'mail/binding/patched',
    BINDING_PATCH_FAILED: 'mail/binding/patch_failed',
    BINDING_CALENDAR_AUTOLINK_REQUESTED: 'mail/binding/calendar_autolink_requested',
    BINDING_CALENDAR_UNLINK_REQUESTED: 'mail/binding/calendar_unlink_requested',
    BINDING_HEALTHCHECK_REQUESTED: 'mail/binding/healthcheck_requested',
    BINDING_HEALTHCHECK_COMPLETED: 'mail/binding/healthcheck_completed',
    BINDING_HEALTHCHECK_FAILED: 'mail/binding/healthcheck_failed',
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
    FOLDERS_REORDER_REQUESTED: 'mail/folders/reorder_requested',
    FOLDERS_REORDER_FAILED: 'mail/folders/reorder_failed',
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
    MESSAGE_RAG_INDEX_REQUESTED: 'mail/message/rag_index_requested',
    MESSAGE_RAG_INDEX_ACCEPTED: 'mail/message/rag_index_accepted',
    MESSAGE_RAG_INDEX_FAILED: 'mail/message/rag_index_failed',
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

export interface MailFolderRecord extends Record<string, unknown> {
    name?: string;
    role?: string;
    unseen_count?: number;
    selectable?: boolean;
}

export interface MailBindingRecord extends Record<string, unknown> {
    mailbox_binding_id?: string;
    is_default?: boolean;
    user_id?: string;
}

export interface MailMessageRecord extends Record<string, unknown> {
    uid?: string;
    folder?: string;
    unread?: boolean;
    flagged?: boolean;
    rag_index_status?: string;
}

export interface MailAttachment {
    filename: string;
    content_type: string;
    file_id: string;
    url: string | null;
    size: number;
}

export interface MailCompose {
    to: string;
    subject: string;
    body: string;
    body_html: string;
    in_reply_to: string | null;
    references: string | null;
    attachments: readonly MailAttachment[];
}

export interface MailState {
    bindings: readonly MailBindingRecord[];
    companyBindings: readonly MailBindingRecord[];
    activeMailboxBindingId: string | null;
    connection: Record<string, unknown> | null;
    folder: string | null;
    folders: readonly MailFolderRecord[];
    missingStandardRoles: readonly string[];
    messages: readonly MailMessageRecord[];
    messagesNextCursor: string | null;
    messagesHasMore: boolean;
    needsSync: boolean;
    syncInProgress: boolean;
    searchQuery: string;
    selectedUid: string | null;
    selectedThreadId: string | null;
    selectedThreadMessages: readonly MailMessageRecord[];
    selectedMessage: MailMessageRecord | null;
    pendingOpenUid: string | null;
    loading: boolean;
    messageLoading: boolean;
    sending: boolean;
    adminMode: boolean;
    canAdmin: boolean;
    health: Record<string, unknown> | null;
    compose: MailCompose;
    draftUid: string | null;
    bindingMembers: Readonly<Record<string, readonly Record<string, unknown>[]>>;
    errorMessage: string | null;
}

const EMPTY_COMPOSE: MailCompose = Object.freeze({
    to: '',
    subject: '',
    body: '',
    body_html: '',
    in_reply_to: null,
    references: null,
    attachments: Object.freeze([]),
});

export const initialMailState: MailState = Object.freeze({
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
    canAdmin: false,
    health: null,
    compose: EMPTY_COMPOSE,
    draftUid: null,
    bindingMembers: Object.freeze({}),
    errorMessage: null,
});

function copyFields(blank: Record<string, unknown>, value: Record<string, unknown>): void {
    for (const [key, field] of Object.entries(value)) {
        blank[key] = field;
    }
}

function mailMessage(value: unknown, label: string): MailMessageRecord {
    if (!isPlainRecord(value)) {
        throw new Error(`${label}: message must be an object`);
    }
    const message: MailMessageRecord = {};
    copyFields(message, value);
    if (message.uid !== undefined && typeof message.uid !== 'string') {
        throw new Error(`${label}: uid must be a string`);
    }
    if (message.folder !== undefined && typeof message.folder !== 'string') {
        throw new Error(`${label}: folder must be a string`);
    }
    if (message.unread !== undefined && typeof message.unread !== 'boolean') {
        throw new Error(`${label}: unread must be a boolean`);
    }
    if (message.flagged !== undefined && typeof message.flagged !== 'boolean') {
        throw new Error(`${label}: flagged must be a boolean`);
    }
    if (message.rag_index_status !== undefined && typeof message.rag_index_status !== 'string') {
        throw new Error(`${label}: rag_index_status must be a string`);
    }
    return message;
}

function messageWith(item: MailMessageRecord, patch: { unread?: boolean; flagged?: boolean; folder?: string | null; rag_index_status?: string }): MailMessageRecord {
    const next = mailMessage(item, 'mail message');
    if (patch.unread !== undefined) next.unread = patch.unread;
    if (patch.flagged !== undefined) next.flagged = patch.flagged;
    if (patch.folder === null) {
        next.folder = undefined;
    } else if (typeof patch.folder === 'string') {
        next.folder = patch.folder;
    }
    if (patch.rag_index_status !== undefined) next.rag_index_status = patch.rag_index_status;
    Object.freeze(next);
    return next;
}

function mailFolder(value: unknown, label: string): MailFolderRecord {
    if (!isPlainRecord(value)) {
        throw new Error(`${label}: folder must be an object`);
    }
    const folder: MailFolderRecord = {};
    copyFields(folder, value);
    if (folder.name !== undefined && typeof folder.name !== 'string') {
        throw new Error(`${label}: name must be a string`);
    }
    if (folder.role !== undefined && typeof folder.role !== 'string') {
        throw new Error(`${label}: role must be a string`);
    }
    if (folder.unseen_count !== undefined && typeof folder.unseen_count !== 'number') {
        throw new Error(`${label}: unseen_count must be a number`);
    }
    if (folder.selectable !== undefined && typeof folder.selectable !== 'boolean') {
        throw new Error(`${label}: selectable must be a boolean`);
    }
    return folder;
}

function mailFolders(items: readonly unknown[], label: string): MailFolderRecord[] {
    return items.map((item, index) => mailFolder(item, `${label}[${index}]`));
}

function mailBinding(value: unknown, label: string): MailBindingRecord {
    if (!isPlainRecord(value)) {
        throw new Error(`${label}: binding must be an object`);
    }
    const binding: MailBindingRecord = {};
    copyFields(binding, value);
    if (binding.mailbox_binding_id !== undefined && typeof binding.mailbox_binding_id !== 'string') {
        throw new Error(`${label}: mailbox_binding_id must be a string`);
    }
    if (binding.is_default !== undefined && typeof binding.is_default !== 'boolean') {
        throw new Error(`${label}: is_default must be a boolean`);
    }
    if (binding.user_id !== undefined && typeof binding.user_id !== 'string') {
        throw new Error(`${label}: user_id must be a string`);
    }
    return binding;
}

function messageBindingDefault(item: MailBindingRecord, isDefault: boolean): MailBindingRecord {
    const next = mailBinding(item, 'mail binding');
    next.is_default = isDefault;
    Object.freeze(next);
    return next;
}

function requireItems<T extends Record<string, unknown>>(
    payload: unknown,
    eventType: string,
    read: (value: unknown, label: string) => T,
): T[] {
    if (!isPlainRecord(payload)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    const items = payload.items;
    if (!Array.isArray(items)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    return items.map((item, index) => read(item, `${eventType}.items[${index}]`));
}

function mailErrorParams(value: unknown): Record<string, string | number | boolean> | null {
    if (!isPlainRecord(value)) {
        return null;
    }
    const params: Record<string, string | number | boolean> = {};
    for (const [key, field] of Object.entries(value)) {
        if (typeof field !== 'string' && typeof field !== 'number' && typeof field !== 'boolean') {
            throw new Error('mail failure: error_params values must be string, number, or boolean');
        }
        params[key] = field;
    }
    return params;
}

function adjustFolderUnseen(folders: readonly MailFolderRecord[], folderName: unknown, delta: number): readonly MailFolderRecord[] {
    if (typeof folderName !== 'string' || folderName.length === 0) {
        return folders;
    }
    if (!Array.isArray(folders) || delta === 0) {
        return folders;
    }
    return Object.freeze(folders.map((folder): MailFolderRecord => {
        if (folder.name !== folderName) {
            return folder;
        }
        const current = typeof folder.unseen_count === 'number' ? folder.unseen_count : 0;
        const next = Math.max(0, current + delta);
        return Object.freeze({ ...folder, unseen_count: next });
    }));
}

function pickActiveId(bindings: readonly MailBindingRecord[], preferredId: string | null): string | null {
    if (preferredId && bindings.some((b) => b.mailbox_binding_id === preferredId)) {
        return preferredId;
    }
    const def = bindings.find((b) => b.is_default === true);
    if (def && typeof def.mailbox_binding_id === 'string') return def.mailbox_binding_id;
    const first = bindings[0];
    if (first && typeof first.mailbox_binding_id === 'string') return first.mailbox_binding_id;
    return null;
}

function pickDefaultFolderName(folders: readonly MailFolderRecord[], preferredName: string | null): string | null {
    if (preferredName && folders.some((f) => f.name === preferredName && f.selectable !== false)) {
        return preferredName;
    }
    const inbox = folders.find((f) => f.role === 'inbox' && f.selectable !== false);
    if (inbox && typeof inbox.name === 'string') return inbox.name;
    const first = folders.find((f) => f.selectable !== false);
    if (first && typeof first.name === 'string') return first.name;
    return null;
}

function normalizeAttachments(raw: unknown): readonly MailAttachment[] {
    if (!Array.isArray(raw)) {
        throw new Error('mail.compose: attachments must be an array');
    }
    return Object.freeze(raw.map((rawItem): MailAttachment => {
        if (!isPlainRecord(rawItem)) {
            throw new Error('mail.compose: attachment must be object');
        }
        const item = rawItem;
        if (typeof item.filename !== 'string' || item.filename.length === 0) {
            throw new Error('mail.compose: attachment.filename required');
        }
        if (typeof item.content_type !== 'string' || item.content_type.length === 0) {
            throw new Error('mail.compose: attachment.content_type required');
        }
        if (typeof item.file_id !== 'string' || item.file_id.length === 0) {
            throw new Error('mail.compose: attachment.file_id required');
        }
        if (Object.prototype.hasOwnProperty.call(item, 'content_base64')) {
            throw new Error('mail.compose: attachment.content_base64 forbidden; use file_id');
        }
        if (typeof item.size !== 'number') {
            throw new Error('mail.compose: attachment.size required');
        }
        const url =
            typeof item.url === 'string' && item.url.length > 0 ? item.url : null;
        return Object.freeze({
            filename: item.filename,
            content_type: item.content_type,
            file_id: item.file_id,
            url,
            size: item.size,
        });
    }));
}

function _mailFailureMessage(payload: unknown): string {
    if (!isPlainRecord(payload)) {
        throw new Error('mail failure payload required');
    }
    if (typeof payload.error_code === 'string' && payload.error_code.length > 0) {
        return formatPlatformError(payload.error_code, mailErrorParams(payload.error_params));
    }
    throw new Error('mail failure payload.error_code required');
}

export function mailReducer(state: MailState = initialMailState, event: PlatformEvent): MailState {
    const p = payloadFields(event);
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
            const items = requireItems(p, event.type, mailBinding);
            if (typeof p?.can_admin !== 'boolean') {
                throw new Error(`${event.type}: payload.can_admin must be a boolean`);
            }
            const activeMailboxBindingId = pickActiveId(items, state.activeMailboxBindingId);
            return {
                ...state,
                loading: false,
                bindings: items,
                canAdmin: p.can_admin,
                activeMailboxBindingId,
            };
        }
        case MAIL_EVENTS.BINDINGS_LOAD_FAILED:
        case MAIL_EVENTS.FOLDERS_LOAD_FAILED:
        case MAIL_EVENTS.FOLDERS_ENSURE_FAILED:
        case MAIL_EVENTS.FOLDERS_REORDER_FAILED:
        case MAIL_EVENTS.MESSAGES_LOAD_FAILED:
        case MAIL_EVENTS.CONNECTION_LOAD_FAILED:
        case MAIL_EVENTS.COMPANY_BINDINGS_LOAD_FAILED:
        case MAIL_EVENTS.CONNECTION_SAVE_FAILED:
        case MAIL_EVENTS.BINDING_CREATE_FAILED:
        case MAIL_EVENTS.PERSONAL_CONNECT_FAILED:
        case MAIL_EVENTS.PERSONAL_HEALTHCHECK_FAILED:
        case MAIL_EVENTS.BINDING_PATCH_FAILED:
        case MAIL_EVENTS.BINDING_HEALTHCHECK_FAILED:
        case MAIL_EVENTS.BINDING_DELETE_FAILED:
        case MAIL_EVENTS.DEFAULT_SET_FAILED:
        case MAIL_EVENTS.MESSAGE_SEND_FAILED:
        case MAIL_EVENTS.HEALTHCHECK_FAILED:
        case MAIL_EVENTS.SYNC_FAILED:
        case MAIL_EVENTS.MESSAGE_TRASH_FAILED:
        case MAIL_EVENTS.MESSAGE_ARCHIVE_FAILED:
        case MAIL_EVENTS.MESSAGE_DELETE_FAILED:
        case MAIL_EVENTS.MESSAGE_STAR_FAILED:
        case MAIL_EVENTS.MESSAGE_RAG_INDEX_FAILED:
        case MAIL_EVENTS.DRAFT_SAVE_FAILED:
        case MAIL_EVENTS.BINDING_MEMBERS_LOAD_FAILED:
        case MAIL_EVENTS.BINDING_MEMBER_ADD_FAILED:
        case MAIL_EVENTS.BINDING_MEMBER_REMOVE_FAILED:
            return {
                ...state,
                loading: false,
                sending: false,
                syncInProgress: false,
                errorMessage: _mailFailureMessage(p),
            };
        case MAIL_EVENTS.MESSAGE_LOAD_FAILED:
            return {
                ...state,
                messageLoading: false,
                errorMessage: _mailFailureMessage(p),
            };
        case MAIL_EVENTS.COMPANY_BINDINGS_LOADED:
            return {
                ...state,
                loading: false,
                companyBindings: requireItems(p, event.type, mailBinding),
            };
        case MAIL_EVENTS.CONNECTION_LOADED:
        case MAIL_EVENTS.CONNECTION_SAVED:
            return {
                ...state,
                loading: false,
                connection: isPlainRecord(p.connection) ? p.connection : null,
            };
        case MAIL_EVENTS.OPEN_FROM_NOTIFICATION: {
            const id = p && p.mailbox_binding_id;
            const uid = p && p.uid;
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
            const id = p && p.mailbox_binding_id;
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
            const payload = p;
            if (!payload || !Array.isArray(payload.folders)) {
                throw new Error(`${event.type}: payload.folders must be an array`);
            }
            const folders = mailFolders(payload.folders, `${event.type}.folders`);
            const missing = Array.isArray(payload.missing_standard_roles)
                ? payload.missing_standard_roles as string[]
                : [];
            const folder = pickDefaultFolderName(folders, state.folder);
            const keepList = folder === state.folder && state.pendingOpenUid == null;
            return {
                ...state,
                loading: false,
                folders: Object.freeze(folders),
                missingStandardRoles: Object.freeze(missing),
                folder,
                needsSync: payload.needs_sync === true,
                selectedUid: keepList ? state.selectedUid : state.pendingOpenUid,
                selectedThreadId: keepList ? state.selectedThreadId : null,
                selectedThreadMessages: keepList ? state.selectedThreadMessages : Object.freeze([]),
                selectedMessage: keepList ? state.selectedMessage : null,
                messages: keepList ? state.messages : Object.freeze([]),
            };
        }
        case MAIL_EVENTS.FOLDERS_REORDER_REQUESTED: {
            const payload = p;
            if (!payload || !Array.isArray(payload.folders)) {
                throw new Error(`${event.type}: payload.folders must be an array`);
            }
            if (typeof payload.mailbox_binding_id !== 'string' || !payload.mailbox_binding_id) {
                throw new Error(`${event.type}: mailbox_binding_id required`);
            }
            return {
                ...state,
                folders: Object.freeze(mailFolders(payload.folders, `${event.type}.folders`)),
            };
        }
        case MAIL_EVENTS.FOLDER_SELECT: {
            const folder = p && p.folder;
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
            const items = requireItems(p, event.type, mailMessage);
            return {
                ...state,
                loading: false,
                messages: Object.freeze(items),
                messagesNextCursor: typeof p?.next_cursor === 'string'
                    ? p.next_cursor
                    : null,
                messagesHasMore: p?.has_more === true,
                needsSync: p?.needs_sync === true,
            };
        }
        case MAIL_EVENTS.MESSAGES_APPEND_LOADED: {
            const items = requireItems(p, event.type, mailMessage);
            const existingUids = new Set(state.messages.map((item) => item.uid));
            const merged = [
                ...state.messages,
                ...items.filter((item) => item && typeof item.uid === 'string' && !existingUids.has(item.uid)),
            ];
            return {
                ...state,
                loading: false,
                messages: Object.freeze(merged),
                messagesNextCursor: typeof p?.next_cursor === 'string'
                    ? p.next_cursor
                    : null,
                messagesHasMore: p?.has_more === true,
            };
        }
        case MAIL_EVENTS.SYNC_REQUESTED:
            return { ...state, syncInProgress: true, errorMessage: null };
        case MAIL_EVENTS.SYNC_ACCEPTED:
            return { ...state, syncInProgress: true, needsSync: false };
        case MAIL_EVENTS.THREAD_SELECT:
        case MAIL_EVENTS.MESSAGE_SELECT: {
            const uid = p && p.uid;
            if (typeof uid !== 'string' || uid.length === 0) return state;
            const threadId = p && typeof p.thread_id === 'string'
                ? p.thread_id
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
            const thread = isPlainRecord(p.thread) ? p.thread : null;
            if (!thread || !Array.isArray(thread.items)) {
                throw new Error(`${event.type}: payload.thread.items must be an array`);
            }
            const items = thread.items.map((item, index) => mailMessage(item, `${event.type}.thread.items[${index}]`));
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
            const messages = state.messages.map((item): MailMessageRecord => {
                if (!inboxUnreadUids.has(item.uid) || item.unread !== true) {
                    return item;
                }
                newlyRead += 1;
                return messageWith(item, { unread: false });
            });
            const focusUid = typeof state.selectedUid === 'string' ? state.selectedUid : null;
            const focus = focusUid
                ? items.find((item) => item.uid === focusUid) || items[items.length - 1]
                : items[items.length - 1];
            const selectedMessage = focus
                ? messageWith(focus, { unread: false })
                : null;
            const threadMessages = items.map((item) => {
                if (
                    item
                    && item.folder === folderName
                    && item.unread === true
                ) {
                    return messageWith(item, { unread: false });
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
            return {
                ...state,
                messageLoading: false,
                errorMessage: p && typeof p.message === 'string'
                    ? p.message
                    : 'mail thread load failed',
            };
        case MAIL_EVENTS.MESSAGE_LOADED: {
            const loaded = p.message === undefined || p.message === null ? null : mailMessage(p.message, `${event.type}.message`);
            const loadedUid = loaded && typeof loaded.uid === 'string' ? loaded.uid : null;
            const previous = loadedUid
                ? state.messages.find((item) => item.uid === loadedUid)
                : null;
            const wasUnread = Boolean(previous && previous.unread === true);
            const messages = loadedUid
                ? state.messages.map((item): MailMessageRecord => (
                    item.uid === loadedUid
                        ? messageWith(item, { unread: false })
                        : item
                ))
                : state.messages;
            return {
                ...state,
                messageLoading: false,
                pendingOpenUid: null,
                selectedMessage: loaded,
                selectedThreadMessages: loaded
                    ? Object.freeze([messageWith(loaded, { folder: state.folder })])
                    : Object.freeze([]),
                messages: Object.freeze(messages),
                folders: wasUnread
                    ? adjustFolderUnseen(state.folders, state.folder, -1)
                    : state.folders,
            };
        }
        case MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED: {
            const uid = p && p.uid;
            if (typeof uid !== 'string' || uid.length === 0) return state;
            const previous = state.messages.find((item) => item.uid === uid);
            const alreadyUnread = Boolean(previous && previous.unread === true);
            const messages = state.messages.map((item): MailMessageRecord => (
                item.uid === uid
                    ? messageWith(item, { unread: true })
                    : item
            ));
            const selectedMessage = state.selectedMessage && state.selectedMessage.uid === uid
                ? messageWith(state.selectedMessage, { unread: true })
                : state.selectedMessage;
            const selectedThreadMessages = state.selectedThreadMessages.map((item): MailMessageRecord => (
                item.uid === uid
                    ? messageWith(item, { unread: true })
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
            const draft = p;
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
                        ? (draft.in_reply_to as string | null)
                        : state.compose.in_reply_to,
                    references: Object.prototype.hasOwnProperty.call(draft, 'references')
                        ? (draft.references as string | null)
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
            const binding = p.binding === undefined || p.binding === null ? null : mailBinding(p.binding, `${event.type}.binding`);
            if (!binding || typeof binding.mailbox_binding_id !== 'string') return state;
            const ownerUserId = typeof binding.user_id === 'string' ? binding.user_id : null;
            const applyDefaultFlags = (items: readonly MailBindingRecord[]): MailBindingRecord[] => items.map((item) => {
                if (ownerUserId !== null) {
                    if (item.user_id !== ownerUserId) return item;
                    return messageBindingDefault(item, item.mailbox_binding_id === binding.mailbox_binding_id);
                }
                return messageBindingDefault(item, item.mailbox_binding_id === binding.mailbox_binding_id);
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
            const binding = p.binding === undefined || p.binding === null ? null : mailBinding(p.binding, `${event.type}.binding`);
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
            const id = p && p.mailbox_binding_id;
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
                adminMode: Boolean(p && p.open),
            };
        case MAIL_EVENTS.HEALTHCHECK_COMPLETED:
            return {
                ...state,
                loading: false,
                health: isPlainRecord(p.health) ? p.health : null,
            };
        case MAIL_EVENTS.MESSAGE_UPSERTED: {
            const payload = p;
            if (!payload || typeof payload !== 'object') {
                throw new Error('mail/message/upserted: payload required');
            }
            const mailboxBindingId = payload.mailbox_binding_id;
            const folder = payload.folder;
            const listItem = payload.list_item === undefined || payload.list_item === null
                ? null
                : mailMessage(payload.list_item, 'mail/message/upserted.list_item');
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
                messages = Object.freeze(state.messages.map((item): MailMessageRecord => (
                    item.uid === payload.uid
                        ? messageWith(item, { flagged: payload.flagged === true })
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
            const payload = p;
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
            const payload = p;
            const uid = typeof payload.uid === 'string' ? payload.uid : null;
            if (!uid) return state;
            return {
                ...state,
                messages: Object.freeze(state.messages.filter((item) => item.uid !== uid)),
            };
        }
        case MAIL_EVENTS.MESSAGE_STAR_COMPLETED: {
            const uid = p && p.uid;
            const flagged = p && p.flagged === true;
            if (typeof uid !== 'string') return state;
            return {
                ...state,
                messages: Object.freeze(state.messages.map((item): MailMessageRecord => (
                    item.uid === uid ? messageWith(item, { flagged }) : item
                ))),
                selectedMessage: state.selectedMessage && state.selectedMessage.uid === uid
                    ? messageWith(state.selectedMessage, { flagged })
                    : state.selectedMessage,
            };
        }
        case MAIL_EVENTS.MESSAGE_RAG_INDEX_ACCEPTED: {
            const uid = p && p.uid;
            const status = p && p.rag_index_status;
            if (typeof uid !== 'string' || typeof status !== 'string') return state;
            return {
                ...state,
                messages: Object.freeze(state.messages.map((item): MailMessageRecord => (
                    item.uid === uid
                        ? messageWith(item, { rag_index_status: status })
                        : item
                ))),
            };
        }
        case MAIL_EVENTS.DRAFT_SAVED: {
            const uid = p && p.uid;
            return {
                ...state,
                draftUid: typeof uid === 'string' ? uid : state.draftUid,
            };
        }
        case MAIL_EVENTS.BINDING_MEMBERS_LOADED: {
            const mailboxBindingId = p && p.mailbox_binding_id;
            const items = requireItems(p, event.type, (value, label) => {
                if (!isPlainRecord(value)) {
                    throw new Error(`${label}: member must be an object`);
                }
                return value;
            });
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
            const member = p.member === undefined || p.member === null ? null : mailBinding(p.member, `${event.type}.member`);
            if (!member || typeof member.mailbox_binding_id !== 'string') return state;
            const currentRaw = state.bindingMembers[member.mailbox_binding_id];
            const current = Array.isArray(currentRaw) ? currentRaw : [];
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
            const mailboxBindingId = p && p.mailbox_binding_id;
            const userId = p && p.user_id;
            if (typeof mailboxBindingId !== 'string' || typeof userId !== 'string') return state;
            const currentRaw = state.bindingMembers[mailboxBindingId];
            const current = Array.isArray(currentRaw) ? currentRaw : [];
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
