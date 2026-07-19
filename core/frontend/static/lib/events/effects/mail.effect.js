/**
 * Эффект mail — bindings, connection, messages, send.
 */

import { httpRequest } from '../http.js';
import { MAIL_EVENTS } from '../reducers/mail.js';

function errorMessage(err) {
    return String(err && err.message ? err.message : err);
}

export function createMailEffect({ baseUrl }) {
    const base = baseUrl || '';
    return async function mailEffect(event, ctx) {
        switch (event.type) {
            case MAIL_EVENTS.BOOTSTRAP_REQUESTED: {
                ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                    causation_id: event.id,
                    source: 'local',
                });
                ctx.dispatch(MAIL_EVENTS.CONNECTION_LOAD_REQUESTED, null, {
                    causation_id: event.id,
                    source: 'local',
                });
                return;
            }
            case MAIL_EVENTS.BINDINGS_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/bindings/me`,
                    });
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.bindings.me: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.BINDINGS_LOADED,
                        { items: data.items },
                        { causation_id: event.id, source: 'http' },
                    );
                    const state = ctx.getState();
                    const activeId = state.mail && state.mail.activeMailboxBindingId;
                    if (typeof activeId === 'string' && activeId.length > 0) {
                        ctx.dispatch(
                            MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                            { mailbox_binding_id: activeId },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDINGS_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/bindings`,
                    });
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.bindings: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.COMPANY_BINDINGS_LOADED,
                        { items: data.items },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.COMPANY_BINDINGS_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.CONNECTION_LOAD_REQUESTED: {
                try {
                    const connection = await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/connection`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_LOADED,
                        { connection },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    const status = err && typeof err.status === 'number' ? err.status : 0;
                    if (status === 404) {
                        ctx.dispatch(
                            MAIL_EVENTS.CONNECTION_LOADED,
                            { connection: null },
                            { causation_id: event.id, source: 'http' },
                        );
                        return;
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.CONNECTION_SAVE_REQUESTED: {
                try {
                    const connection = await httpRequest({
                        method: 'PUT',
                        url: `${base}/api/mail/connection`,
                        body: event.payload,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_SAVED,
                        { connection },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_SAVE_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_CREATE_REQUESTED: {
                try {
                    const binding = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings`,
                        body: event.payload,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_CREATED,
                        { binding },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                    ctx.dispatch(MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_CREATE_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_PATCH_REQUESTED: {
                const id = event.payload && event.payload.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                const { mailbox_binding_id: _id, ...body } = event.payload;
                try {
                    const binding = await httpRequest({
                        method: 'PATCH',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(id)}`,
                        body,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_PATCHED,
                        { binding },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_PATCH_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_DELETE_REQUESTED: {
                const id = event.payload && event.payload.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    await httpRequest({
                        method: 'DELETE',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(id)}`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_DELETED,
                        { mailbox_binding_id: id },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_DELETE_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.DEFAULT_SET_REQUESTED: {
                const id = event.payload && event.payload.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const binding = await httpRequest({
                        method: 'PUT',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(id)}/default`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.DEFAULT_SET,
                        { binding },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.DEFAULT_SET_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.OPEN_FROM_NOTIFICATION: {
                const mailboxBindingId = event.payload && event.payload.mailbox_binding_id;
                if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
                    throw new Error('mail.effect: mailbox_binding_id required');
                }
                ctx.dispatch(
                    MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                    { mailbox_binding_id: mailboxBindingId },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case MAIL_EVENTS.MAILBOX_SELECT: {
                const state = ctx.getState();
                const activeId = state.mail && state.mail.activeMailboxBindingId;
                if (typeof activeId !== 'string' || activeId.length === 0) return;
                ctx.dispatch(
                    MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                    { mailbox_binding_id: activeId },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case MAIL_EVENTS.FOLDERS_LOAD_REQUESTED: {
                const mailboxBindingId = event.payload && event.payload.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const data = await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/folders?mailbox_binding_id=${encodeURIComponent(mailboxBindingId)}`,
                    });
                    if (!data || !Array.isArray(data.folders)) {
                        throw new Error('mail.folders: folders must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_LOADED,
                        {
                            folders: data.folders,
                            missing_standard_roles: Array.isArray(data.missing_standard_roles)
                                ? data.missing_standard_roles
                                : [],
                            namespace_prefix: data.namespace_prefix,
                            capabilities: Array.isArray(data.capabilities) ? data.capabilities : [],
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                    const state = ctx.getState();
                    const folder = state.mail && state.mail.folder;
                    if (typeof folder === 'string' && folder.length > 0) {
                        ctx.dispatch(
                            MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                            {
                                mailbox_binding_id: mailboxBindingId,
                                folder,
                            },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED: {
                const mailboxBindingId = event.payload && event.payload.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const data = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/folders/ensure`,
                        body: { mailbox_binding_id: mailboxBindingId },
                    });
                    if (!data || !Array.isArray(data.folders)) {
                        throw new Error('mail.folders.ensure: folders must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_LOADED,
                        {
                            folders: data.folders,
                            missing_standard_roles: Array.isArray(data.missing_standard_roles)
                                ? data.missing_standard_roles
                                : [],
                            namespace_prefix: data.namespace_prefix,
                            capabilities: Array.isArray(data.capabilities) ? data.capabilities : [],
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                    const state = ctx.getState();
                    const folder = state.mail && state.mail.folder;
                    if (typeof folder === 'string' && folder.length > 0) {
                        ctx.dispatch(
                            MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                            {
                                mailbox_binding_id: mailboxBindingId,
                                folder,
                            },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_ENSURE_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.FOLDER_SELECT: {
                const state = ctx.getState();
                const activeId = state.mail && state.mail.activeMailboxBindingId;
                if (typeof activeId !== 'string' || activeId.length === 0) return;
                const folder = state.mail.folder;
                if (typeof folder !== 'string' || folder.length === 0) return;
                ctx.dispatch(
                    MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                    {
                        mailbox_binding_id: activeId,
                        folder,
                    },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case MAIL_EVENTS.MESSAGES_LOAD_REQUESTED: {
                const payload = event.payload || {};
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : null;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                if (!folder) throw new Error('mail.effect: folder required');
                try {
                    const data = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/list`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            limit: 50,
                        },
                    });
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.messages.list: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOADED,
                        { items: data.items },
                        { causation_id: event.id, source: 'http' },
                    );
                    const state = ctx.getState();
                    const pendingUid = state.mail && state.mail.pendingOpenUid;
                    if (typeof pendingUid === 'string' && pendingUid.length > 0) {
                        ctx.dispatch(
                            MAIL_EVENTS.THREAD_LOAD_REQUESTED,
                            {
                                uid: pendingUid,
                                mailbox_binding_id: mailboxBindingId,
                                folder,
                            },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.THREAD_SELECT:
            case MAIL_EVENTS.MESSAGE_SELECT: {
                const uid = event.payload && event.payload.uid;
                const state = ctx.getState();
                const activeId = state.mail && state.mail.activeMailboxBindingId;
                if (!uid || !activeId) return;
                ctx.dispatch(
                    MAIL_EVENTS.THREAD_LOAD_REQUESTED,
                    {
                        uid,
                        mailbox_binding_id: activeId,
                        folder: state.mail.folder,
                        thread_id: event.payload && event.payload.thread_id
                            ? event.payload.thread_id
                            : null,
                    },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case MAIL_EVENTS.THREAD_LOAD_REQUESTED: {
                const payload = event.payload || {};
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required for thread');
                }
                try {
                    const thread = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/thread`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            uid,
                        },
                    });
                    if (!thread || !Array.isArray(thread.items)) {
                        throw new Error('mail.messages.thread: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.THREAD_LOADED,
                        { thread },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.THREAD_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_LOAD_REQUESTED: {
                const payload = event.payload || {};
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required');
                }
                try {
                    const q = new URLSearchParams({
                        mailbox_binding_id: mailboxBindingId,
                        folder,
                    });
                    const message = await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/messages/${encodeURIComponent(uid)}?${q.toString()}`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_LOADED,
                        { message },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_LOAD_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_MARK_UNSEEN_REQUESTED: {
                const payload = event.payload || {};
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required for mark_unseen');
                }
                try {
                    const result = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/mark_unseen`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            uid,
                        },
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED,
                        { uid: result.uid, unread: result.unread === true },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_MARK_UNSEEN_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_SEND_REQUESTED: {
                try {
                    const result = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/send`,
                        body: event.payload,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_SENT,
                        { result },
                        { causation_id: event.id, source: 'http' },
                    );
                    const state = ctx.getState();
                    if (state.mail && state.mail.activeMailboxBindingId) {
                        ctx.dispatch(
                            MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                            {
                                mailbox_binding_id: state.mail.activeMailboxBindingId,
                                folder: state.mail.folder,
                            },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_SEND_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.HEALTHCHECK_REQUESTED: {
                try {
                    const health = await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/connection/healthcheck`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.HEALTHCHECK_COMPLETED,
                        { health },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.HEALTHCHECK_FAILED,
                        { message: errorMessage(err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case 'notify/mail/mail_new_message_received': {
                const state = ctx.getState();
                const mail = state.mail;
                if (!mail || typeof mail.activeMailboxBindingId !== 'string') {
                    return;
                }
                if (!mail.folder || typeof mail.folder !== 'string') {
                    return;
                }
                const data = event.payload && event.payload.data && typeof event.payload.data === 'object'
                    ? event.payload.data
                    : {};
                const notifyBindingId = typeof data.mailbox_binding_id === 'string'
                    ? data.mailbox_binding_id
                    : '';
                if (
                    notifyBindingId.length > 0
                    && notifyBindingId !== mail.activeMailboxBindingId
                ) {
                    return;
                }
                ctx.dispatch(
                    MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                    { mailbox_binding_id: mail.activeMailboxBindingId },
                    { causation_id: event.id, source: 'ws' },
                );
                ctx.dispatch(
                    MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                    {
                        mailbox_binding_id: mail.activeMailboxBindingId,
                        folder: mail.folder,
                    },
                    { causation_id: event.id, source: 'ws' },
                );
                return;
            }
            default:
                return;
        }
    };
}
