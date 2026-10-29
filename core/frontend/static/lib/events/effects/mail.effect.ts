/**
 * Эффект mail — bindings, connection, messages, send.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { isPlainRecord, payloadFields } from '../payload.js';
import { MAIL_EVENTS } from '../reducers/mail.js';

function cursorOrNull(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

function mailFailurePayload(err: unknown): {
    error_code: string;
    error_params: Record<string, string | number | boolean> | null;
} {
    if (isPlainRecord(err)) {
        const code = err.error_code !== undefined ? err.error_code : err.code;
        if (typeof code === 'string' && code.length > 0) {
            let params: Record<string, string | number | boolean> | null = null;
            if (isPlainRecord(err.error_params)) {
                params = {};
                for (const [key, value] of Object.entries(err.error_params)) {
                    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
                        params[key] = value;
                    }
                }
            }
            return { error_code: code, error_params: params };
        }
    }
    return { error_code: 'unknown', error_params: null };
}

function httpStatus(err: unknown): number {
    if (isPlainRecord(err) && typeof err.status === 'number') {
        return err.status;
    }
    return 0;
}

function httpObject(value: unknown): Record<string, unknown> | null {
    if (value === null) {
        return null;
    }
    if (!isPlainRecord(value)) {
        throw new Error('mail effect: HTTP response must be an object');
    }
    return value;
}

// Троттлинг авто-синка: needs_sync от folders/list мог бы дёргать SYNC в тугом
// цикле (list -> sync -> folders -> list ...). Авто-синк на ящик — не чаще
// AUTO_SYNC_COOLDOWN_MS. Ручной SYNC_REQUESTED (кнопка) не троттлится.
const AUTO_SYNC_COOLDOWN_MS = 15000;
const lastAutoSyncAt = new Map();

function shouldAutoSync(mailboxBindingId: unknown): boolean {
    const now = Date.now();
    const stored = lastAutoSyncAt.get(mailboxBindingId);
    const prev = typeof stored === 'number' ? stored : 0;
    if (now - prev < AUTO_SYNC_COOLDOWN_MS) return false;
    lastAutoSyncAt.set(mailboxBindingId, now);
    return true;
}

/** @internal vitest */
export function resetMailAutoSyncCooldownForTests(): void {
    lastAutoSyncAt.clear();
}

interface MailStateView {
    mail?: {
        activeMailboxBindingId?: string | null;
        folder?: string | null;
        messages?: readonly Record<string, unknown>[];
        messagesNextCursor?: string | null;
        messagesHasMore?: boolean;
        searchQuery?: string;
        selectedUid?: string | null;
        selectedThreadId?: string | null;
        bindings?: readonly Record<string, unknown>[];
        adminMode?: boolean;
        compose?: Record<string, unknown>;
        needsSync?: boolean;
        syncInProgress?: boolean;
        pendingOpenUid?: string | null;
        selectedMessage?: Record<string, unknown> | null;
        selectedThreadMessages?: readonly Record<string, unknown>[];
        draftUid?: string | null;
    };
}

export function createMailEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx<MailStateView>) => Promise<void> {
    const base = baseUrl === undefined ? '' : baseUrl;
    return async function mailEffect(event: PlatformEvent, ctx: EffectCtx<MailStateView>): Promise<void> {
        const p = payloadFields(event);
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
                    const data = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/bindings/me`,
                    }));
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.bindings.me: items must be array');
                    }
                    if (typeof data.can_admin !== 'boolean') {
                        throw new Error('mail.bindings.me: can_admin must be boolean');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.BINDINGS_LOADED,
                        { items: data.items, can_admin: data.can_admin },
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED: {
                try {
                    const data = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/bindings`,
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.CONNECTION_LOAD_REQUESTED: {
                try {
                    const connection = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/connection`,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_LOADED,
                        { connection },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    const status = httpStatus(err);
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.CONNECTION_SAVE_REQUESTED: {
                try {
                    const connection = httpObject(await httpRequest({
                        method: 'PUT',
                        url: `${base}/api/mail/connection`,
                        body: p,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_SAVED,
                        { connection },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.CONNECTION_SAVE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_CREATE_REQUESTED: {
                try {
                    const binding = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings`,
                        body: p,
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.PERSONAL_CONNECT_REQUESTED: {
                try {
                    const binding = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings/personal`,
                        body: p,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_CREATED,
                        { binding },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.PERSONAL_CONNECT_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.PERSONAL_HEALTHCHECK_REQUESTED: {
                try {
                    const health = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings/personal/healthcheck`,
                        body: p,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.PERSONAL_HEALTHCHECK_COMPLETED,
                        { health },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.PERSONAL_HEALTHCHECK_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_PATCH_REQUESTED: {
                const id = p && p.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                const { mailbox_binding_id: _id, ...body } = p;
                try {
                    const binding = httpObject(await httpRequest({
                        method: 'PATCH',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(id))}`,
                        body,
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_CALENDAR_AUTOLINK_REQUESTED:
            case MAIL_EVENTS.BINDING_CALENDAR_UNLINK_REQUESTED: {
                const id = p && p.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                const linking = event.type === MAIL_EVENTS.BINDING_CALENDAR_AUTOLINK_REQUESTED;
                try {
                    const binding = httpObject(await httpRequest({
                        method: linking ? 'POST' : 'DELETE',
                        url: linking
                            ? `${base}/api/mail/bindings/${encodeURIComponent(String(id))}/calendar/autolink`
                            : `${base}/api/mail/bindings/${encodeURIComponent(String(id))}/calendar`,
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_HEALTHCHECK_REQUESTED: {
                const id = p && p.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                const { mailbox_binding_id: _id, ...body } = p;
                try {
                    const health = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(id))}/healthcheck`,
                        body,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_HEALTHCHECK_COMPLETED,
                        { health, mailbox_binding_id: id },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_HEALTHCHECK_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_DELETE_REQUESTED: {
                const id = p && p.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    await httpRequest({
                        method: 'DELETE',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(id))}`,
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
                    ctx.dispatch(MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_DELETE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.DEFAULT_SET_REQUESTED: {
                const id = p && p.mailbox_binding_id;
                if (!id) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const binding = httpObject(await httpRequest({
                        method: 'PUT',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(id))}/default`,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.DEFAULT_SET,
                        { binding },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null, {
                        causation_id: event.id,
                        source: 'local',
                    });
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.DEFAULT_SET_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.OPEN_FROM_NOTIFICATION: {
                const mailboxBindingId = p && p.mailbox_binding_id;
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
                const mailboxBindingId = p && p.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                const skipAutoSync = p && p.skip_auto_sync === true;
                try {
                    const data = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/folders?mailbox_binding_id=${encodeURIComponent(String(mailboxBindingId))}`,
                    }));
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
                            needs_sync: data.needs_sync === true,
                            stale: data.stale === true,
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                    if (
                        !skipAutoSync
                        && data.needs_sync === true
                        && data.folders.length === 0
                        && shouldAutoSync(mailboxBindingId)
                    ) {
                        ctx.dispatch(
                            MAIL_EVENTS.SYNC_REQUESTED,
                            { mailbox_binding_id: mailboxBindingId },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.SYNC_REQUESTED: {
                const mailboxBindingId = p && p.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const data = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/sync`,
                        body: { mailbox_binding_id: mailboxBindingId },
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.SYNC_ACCEPTED,
                        data || { accepted: true, mailbox_binding_id: mailboxBindingId },
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                        {
                            mailbox_binding_id: mailboxBindingId,
                            skip_auto_sync: true,
                        },
                        { causation_id: event.id, source: 'local' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.SYNC_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED: {
                const mailboxBindingId = p && p.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const data = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/folders/ensure`,
                        body: { mailbox_binding_id: mailboxBindingId },
                    }));
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
                            needs_sync: data.needs_sync === true,
                            stale: data.stale === true,
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.FOLDERS_REORDER_REQUESTED: {
                const mailboxBindingId = p && p.mailbox_binding_id;
                const folders = p && p.folders;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                if (!Array.isArray(folders)) throw new Error('mail.effect: folders must be an array');
                const folderNames = folders.map((folder) => {
                    if (!folder || typeof folder.name !== 'string' || !folder.name) {
                        throw new Error('mail.effect: folder.name required');
                    }
                    return folder.name;
                });
                try {
                    const data = httpObject(await httpRequest({
                        method: 'PUT',
                        url: `${base}/api/mail/folders/order`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder_names: folderNames,
                        },
                    }));
                    if (!data || !Array.isArray(data.folders)) {
                        throw new Error('mail.folders.order: folders must be array');
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
                            needs_sync: data.needs_sync === true,
                            stale: data.stale === true,
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_REORDER_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                    ctx.dispatch(
                        MAIL_EVENTS.FOLDERS_LOAD_REQUESTED,
                        {
                            mailbox_binding_id: mailboxBindingId,
                            skip_auto_sync: true,
                        },
                        { causation_id: event.id, source: 'local' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.FOLDER_SELECT: {
                const state = ctx.getState();
                const mail = state.mail;
                const activeId = mail && mail.activeMailboxBindingId;
                if (typeof activeId !== 'string' || activeId.length === 0) return;
                const folder = mail?.folder;
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
                const payload = p;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : null;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                if (!folder) throw new Error('mail.effect: folder required');
                try {
                    const data = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/list`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            limit: 50,
                        },
                    }));
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.messages.list: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOADED,
                        {
                            items: data.items,
                            next_cursor: cursorOrNull(data.next_cursor),
                            has_more: data.has_more === true,
                            needs_sync: data.needs_sync === true,
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                    if (data.needs_sync === true && shouldAutoSync(mailboxBindingId)) {
                        ctx.dispatch(
                            MAIL_EVENTS.SYNC_REQUESTED,
                            { mailbox_binding_id: mailboxBindingId },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGES_LOAD_MORE_REQUESTED: {
                const payload = p;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : null;
                const cursor = typeof payload.cursor === 'string' ? payload.cursor : null;
                if (!mailboxBindingId || !folder || !cursor) {
                    throw new Error('mail.effect: mailbox_binding_id, folder, cursor required');
                }
                try {
                    const data = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/list`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            limit: 50,
                            cursor,
                        },
                    }));
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.messages.list: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_APPEND_LOADED,
                        {
                            items: data.items,
                            next_cursor: cursorOrNull(data.next_cursor),
                            has_more: data.has_more === true,
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOAD_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGES_SEARCH_REQUESTED: {
                const payload = p;
                const mailboxBindingId = payload.mailbox_binding_id;
                const q = typeof payload.q === 'string' ? payload.q.trim() : '';
                const folder = typeof payload.folder === 'string' ? payload.folder : null;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                if (!q) {
                    if (folder) {
                        ctx.dispatch(
                            MAIL_EVENTS.MESSAGES_LOAD_REQUESTED,
                            { mailbox_binding_id: mailboxBindingId, folder },
                            { causation_id: event.id, source: 'local' },
                        );
                    }
                    return;
                }
                try {
                    const body: { mailbox_binding_id: unknown; q: string; limit: number; folder?: string } = {
                        mailbox_binding_id: mailboxBindingId,
                        q,
                        limit: 50,
                    };
                    if (folder) body.folder = folder;
                    const data = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/search`,
                        body,
                    }));
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.messages.search: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOADED,
                        {
                            items: data.items,
                            next_cursor: cursorOrNull(data.next_cursor),
                            has_more: data.has_more === true,
                            needs_sync: false,
                        },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGES_LOAD_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.THREAD_SELECT:
            case MAIL_EVENTS.MESSAGE_SELECT: {
                const uid = p && p.uid;
                const state = ctx.getState();
                const mail = state.mail;
                const activeId = mail && mail.activeMailboxBindingId;
                if (!uid || !activeId) return;
                ctx.dispatch(
                    MAIL_EVENTS.THREAD_LOAD_REQUESTED,
                    {
                        uid,
                        mailbox_binding_id: activeId,
                        folder: mail?.folder,
                        thread_id: p && p.thread_id
                            ? p.thread_id
                            : null,
                    },
                    { causation_id: event.id, source: 'local' },
                );
                return;
            }
            case MAIL_EVENTS.THREAD_LOAD_REQUESTED: {
                const payload = p;
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required for thread');
                }
                try {
                    const thread = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/thread`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            uid,
                        },
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_LOAD_REQUESTED: {
                const payload = p;
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required');
                }
                try {
                    const q = new URLSearchParams({
                        mailbox_binding_id: String(mailboxBindingId),
                        folder: String(folder),
                    });
                    const message = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/messages/${encodeURIComponent(String(uid))}?${q.toString()}`,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_LOADED,
                        { message },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_LOAD_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_MARK_UNSEEN_REQUESTED: {
                const payload = p;
                const uid = payload.uid;
                const mailboxBindingId = payload.mailbox_binding_id;
                const folder = typeof payload.folder === 'string' ? payload.folder : 'INBOX';
                if (!uid || !mailboxBindingId) {
                    throw new Error('mail.effect: uid and mailbox_binding_id required for mark_unseen');
                }
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/mark_unseen`,
                        body: {
                            mailbox_binding_id: mailboxBindingId,
                            folder,
                            uid,
                        },
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED,
                        { uid: result?.uid, unread: result?.unread === true },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_MARK_UNSEEN_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_SEND_REQUESTED: {
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/send`,
                        body: p,
                    }));
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
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_TRASH_REQUESTED: {
                const payload = p;
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/trash`,
                        body: payload,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_TRASH_COMPLETED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_TRASH_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_ARCHIVE_REQUESTED: {
                const payload = p;
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/archive`,
                        body: payload,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_ARCHIVE_COMPLETED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_ARCHIVE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_DELETE_REQUESTED: {
                const payload = p;
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/delete`,
                        body: payload,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_DELETE_COMPLETED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_DELETE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_STAR_REQUESTED: {
                const payload = p;
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/star`,
                        body: payload,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_STAR_COMPLETED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_STAR_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.MESSAGE_RAG_INDEX_REQUESTED: {
                const payload = p;
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/rag-index`,
                        body: payload,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_RAG_INDEX_ACCEPTED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.MESSAGE_RAG_INDEX_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.DRAFT_SAVE_REQUESTED: {
                try {
                    const result = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/messages/drafts`,
                        body: p,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.DRAFT_SAVED,
                        result,
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.DRAFT_SAVE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_MEMBERS_LOAD_REQUESTED: {
                const mailboxBindingId = p && p.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const data = httpObject(await httpRequest({
                        method: 'GET',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(mailboxBindingId))}/members`,
                    }));
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('mail.binding_members: items must be array');
                    }
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBERS_LOADED,
                        { mailbox_binding_id: mailboxBindingId, items: data.items },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBERS_LOAD_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_MEMBER_ADD_REQUESTED: {
                const payload = p;
                const mailboxBindingId = payload.mailbox_binding_id;
                if (!mailboxBindingId) throw new Error('mail.effect: mailbox_binding_id required');
                try {
                    const member = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(mailboxBindingId))}/members`,
                        body: {
                            user_id: payload.user_id,
                            role: payload.role || 'member',
                        },
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBER_ADDED,
                        { member },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBER_ADD_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.BINDING_MEMBER_REMOVE_REQUESTED: {
                const payload = p;
                const mailboxBindingId = payload.mailbox_binding_id;
                const userId = payload.user_id;
                if (!mailboxBindingId || !userId) {
                    throw new Error('mail.effect: mailbox_binding_id and user_id required');
                }
                try {
                    await httpRequest({
                        method: 'DELETE',
                        url: `${base}/api/mail/bindings/${encodeURIComponent(String(mailboxBindingId))}/members/${encodeURIComponent(String(userId))}`,
                    });
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBER_REMOVED,
                        { mailbox_binding_id: mailboxBindingId, user_id: userId },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.BINDING_MEMBER_REMOVE_FAILED,
                        mailFailurePayload(err),
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            case MAIL_EVENTS.HEALTHCHECK_REQUESTED: {
                try {
                    const health = httpObject(await httpRequest({
                        method: 'POST',
                        url: `${base}/api/mail/connection/healthcheck`,
                    }));
                    ctx.dispatch(
                        MAIL_EVENTS.HEALTHCHECK_COMPLETED,
                        { health },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(
                        MAIL_EVENTS.HEALTHCHECK_FAILED,
                        mailFailurePayload(err),
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
                const data = isPlainRecord(p.data) ? p.data : {};
                const notifyBindingId = typeof data.mailbox_binding_id === 'string'
                    ? data.mailbox_binding_id
                    : '';
                if (
                    notifyBindingId.length > 0
                    && notifyBindingId !== mail.activeMailboxBindingId
                ) {
                    return;
                }
                // Local list refresh only — folders come from cache / upsert patch.
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
            case MAIL_EVENTS.MESSAGE_UPSERTED: {
                const state = ctx.getState();
                const mail = state.mail;
                if (!mail || typeof mail.activeMailboxBindingId !== 'string') {
                    return;
                }
                const payload = p && typeof p === 'object'
                    ? p
                    : {};
                const selectedUid = mail.selectedUid;
                const upsertUid = typeof payload.uid === 'string' ? payload.uid : '';
                const upsertFolder = typeof payload.folder === 'string' ? payload.folder : '';
                const upsertThreadId = typeof payload.thread_id === 'string'
                    ? payload.thread_id
                    : '';
                if (
                    !selectedUid
                    || !upsertUid
                    || !upsertFolder
                    || !(
                        selectedUid === upsertUid
                        || (
                            typeof mail.selectedThreadId === 'string'
                            && mail.selectedThreadId.length > 0
                            && upsertThreadId === mail.selectedThreadId
                        )
                    )
                ) {
                    return;
                }
                // UID уникален только в папке. Upsert другого письма треда
                // (INBOX↔Sent) не должен подменять folder якоря selectedUid.
                let anchorFolder = null;
                if (selectedUid === upsertUid) {
                    anchorFolder = upsertFolder;
                } else if (
                    mail.selectedMessage
                    && mail.selectedMessage.uid === selectedUid
                    && typeof mail.selectedMessage.folder === 'string'
                    && mail.selectedMessage.folder.length > 0
                ) {
                    anchorFolder = mail.selectedMessage.folder;
                } else if (Array.isArray(mail.selectedThreadMessages)) {
                    const anchor = mail.selectedThreadMessages.find(
                        (item) => item && item.uid === selectedUid,
                    );
                    if (anchor && typeof anchor.folder === 'string' && anchor.folder.length > 0) {
                        anchorFolder = anchor.folder;
                    }
                }
                if (!anchorFolder && typeof mail.folder === 'string' && mail.folder.length > 0) {
                    anchorFolder = mail.folder;
                }
                if (!anchorFolder) {
                    return;
                }
                ctx.dispatch(
                    MAIL_EVENTS.THREAD_LOAD_REQUESTED,
                    {
                        mailbox_binding_id: mail.activeMailboxBindingId,
                        folder: anchorFolder,
                        uid: selectedUid,
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
