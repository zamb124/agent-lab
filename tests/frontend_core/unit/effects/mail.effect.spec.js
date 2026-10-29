import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMailEffect, resetMailAutoSyncCooldownForTests } from '@platform/lib/events/effects/mail.effect.js';
import { MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => {
    fetchMock = installFetchMock();
    resetMailAutoSyncCooldownForTests();
});
afterEach(() => fetchMock.uninstall());

const ev = (type, payload) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('mailEffect', () => {
    it('BOOTSTRAP_REQUESTED cascades loads', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BOOTSTRAP_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.BINDINGS_LOAD_REQUESTED)).toBe(true);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.CONNECTION_LOAD_REQUESTED)).toBe(true);
    });

    it('BINDINGS_LOAD_REQUESTED → BINDINGS_LOADED + folders', async () => {
        fetchMock.respondJson('GET', '/svc/api/mail/bindings/me', {
            items: [{ mailbox_binding_id: 'b1', is_default: true }],
            can_admin: true,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        const loaded = dispatched.find((d) => d.type === MAIL_EVENTS.BINDINGS_LOADED);
        expect(loaded.payload.items).toHaveLength(1);
        expect(loaded.payload.can_admin).toBe(true);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED)).toBe(true);
    });

    it('BINDINGS_LOAD_REQUESTED bad shape → FAILED', async () => {
        fetchMock.respondJson('GET', '/svc/api/mail/bindings/me', { wrong: true });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDINGS_LOAD_FAILED)).toBeTruthy();
    });

    it('COMPANY_BINDINGS_LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/mail/bindings', { items: [{ mailbox_binding_id: 'c1' }] });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.COMPANY_BINDINGS_LOAD_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.COMPANY_BINDINGS_LOADED).payload.items).toEqual([
            { mailbox_binding_id: 'c1' },
        ]);
    });

    it('CONNECTION_LOAD_REQUESTED 404 → null connection', async () => {
        fetchMock.respondStatus('GET', '/svc/api/mail/connection', 404);
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.CONNECTION_LOAD_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.CONNECTION_LOADED).payload.connection).toBeNull();
    });

    it('CONNECTION_SAVE_REQUESTED → SAVED', async () => {
        fetchMock.respondJson('PUT', '/svc/api/mail/connection', { mail_domain: 'x.com' });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.CONNECTION_SAVE_REQUESTED, { mail_domain: 'x.com' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.CONNECTION_SAVED).payload.connection.mail_domain).toBe('x.com');
    });

    it('BINDING_CREATE_REQUESTED → CREATED + reload', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/bindings', { mailbox_binding_id: 'nb' });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_CREATE_REQUESTED, { local_part: 'a', user_id: 'u1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_CREATED)).toBeTruthy();
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.BINDINGS_LOAD_REQUESTED)).toBe(true);
    });

    it('BINDING_PATCH_REQUESTED requires id', async () => {
        await expect(
            createMailEffect({ baseUrl: '/svc' })(
                ev(MAIL_EVENTS.BINDING_PATCH_REQUESTED, {}),
                buildCtx(() => ({ mail: {} }), []),
            ),
        ).rejects.toThrow(/mailbox_binding_id/);
    });

    it('BINDING_PATCH_REQUESTED → PATCHED', async () => {
        fetchMock.respondJson('PATCH', '/svc/api/mail/bindings/b1', { mailbox_binding_id: 'b1', user_id: 'u2' });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_PATCH_REQUESTED, { mailbox_binding_id: 'b1', user_id: 'u2' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_PATCHED).payload.binding.user_id).toBe('u2');
    });

    it('BINDING_PATCH_REQUESTED with hosts → PATCHED', async () => {
        fetchMock.respondJson('PATCH', '/svc/api/mail/bindings/b1', {
            mailbox_binding_id: 'b1',
            imap_host: 'imap2.mail.ru',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_PATCH_REQUESTED, {
                mailbox_binding_id: 'b1',
                imap_host: 'imap2.mail.ru',
                smtp_host: 'smtp2.mail.ru',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_PATCHED).payload.binding.imap_host).toBe(
            'imap2.mail.ru',
        );
    });

    it('BINDING_HEALTHCHECK_REQUESTED → COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/bindings/b1/healthcheck', {
            imap_ok: true,
            smtp_ok: true,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_HEALTHCHECK_REQUESTED, {
                mailbox_binding_id: 'b1',
                imap_host: 'imap.mail.ru',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        const completed = dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_HEALTHCHECK_COMPLETED);
        expect(completed.payload.health.imap_ok).toBe(true);
        expect(completed.payload.mailbox_binding_id).toBe('b1');
    });

    it('BINDING_DELETE_REQUESTED → DELETED', async () => {
        fetchMock.respondStatus('DELETE', '/svc/api/mail/bindings/b1', 204);
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_DELETE_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_DELETED).payload.mailbox_binding_id).toBe('b1');
    });

    it('DEFAULT_SET_REQUESTED → DEFAULT_SET', async () => {
        fetchMock.respondJson('PUT', '/svc/api/mail/bindings/b1/default', { mailbox_binding_id: 'b1', is_default: true });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.DEFAULT_SET_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.DEFAULT_SET).payload.binding.is_default).toBe(true);
    });

    it('MAILBOX_SELECT triggers folders load', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MAILBOX_SELECT, { mailbox_binding_id: 'b1' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED).payload.mailbox_binding_id).toBe('b1');
    });

    it('MESSAGES_LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/list', { items: [{ uid: '1' }] });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_LOAD_REQUESTED, { mailbox_binding_id: 'b1', folder: 'INBOX' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOADED).payload.items).toEqual([{ uid: '1' }]);
    });

    it('THREAD_SELECT triggers thread load', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.THREAD_SELECT, { uid: '9', thread_id: '<a@x>' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload).toEqual({
            uid: '9',
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            thread_id: '<a@x>',
        });
    });

    it('THREAD_LOAD_REQUESTED → THREAD_LOADED without compose draft', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/thread', {
            thread_id: '<m1>',
            subject: 'Hello',
            participant_emails: ['a@b.c'],
            items: [
                {
                    folder: 'INBOX',
                    uid: '9',
                    from_address: 'a@b.c',
                    subject: 'Hello',
                    message_id: '<m1>',
                    references: null,
                },
            ],
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.THREAD_LOAD_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOADED).payload.thread.items[0].uid).toBe('9');
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.COMPOSE_DRAFT_SET)).toBeUndefined();
    });

    it('MESSAGE_MARK_UNSEEN_REQUESTED → COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/mark_unseen', {
            uid: '9',
            unread: true,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_MARK_UNSEEN_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED).payload).toEqual({
            uid: '9',
            unread: true,
        });
    });

    it('MESSAGE_SEND_REQUESTED → SENT + reload', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/send', { message_id: 'm1', accepted: ['a@b.c'] });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_SEND_REQUESTED, {
                mailbox_binding_id: 'b1',
                to_addresses: ['a@b.c'],
                subject: 's',
                body_text: 'b',
            }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_SENT)).toBeTruthy();
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED)).toBe(true);
    });

    it('HEALTHCHECK_REQUESTED → COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/connection/healthcheck', { imap_ok: true });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.HEALTHCHECK_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.HEALTHCHECK_COMPLETED).payload.health.imap_ok).toBe(true);
    });

    it('notify/mail/mail_new_message_received reloads list without IMAP folders', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev('notify/mail/mail_new_message_received', {
                data: { mailbox_binding_id: 'b1', uid: '99' },
            }),
            buildCtx(
                () => ({
                    mail: {
                        activeMailboxBindingId: 'b1',
                        folder: 'INBOX',
                    },
                }),
                dispatched,
            ),
        );
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED)).toBe(false);
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
        });
    });

    it('mail/message/upserted soft-reloads open thread', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_UPSERTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '99',
                thread_id: 't1',
            }),
            buildCtx(
                () => ({
                    mail: {
                        activeMailboxBindingId: 'b1',
                        folder: 'INBOX',
                        selectedUid: '99',
                        selectedThreadId: 't1',
                    },
                }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            uid: '99',
        });
    });

    it('SYNC_REQUESTED → SYNC_ACCEPTED + folders reload', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/sync', {
            accepted: true,
            mailbox_binding_id: 'b1',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.SYNC_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: { activeMailboxBindingId: 'b1' } }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.SYNC_ACCEPTED).payload.accepted).toBe(true);
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            skip_auto_sync: true,
        });
    });

    it('BINDING_CALENDAR_AUTOLINK_REQUESTED → BINDING_PATCHED со статусом календаря', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/bindings/b1/calendar/autolink', {
            mailbox_binding_id: 'b1',
            calendar_autolink_status: 'linked',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_CALENDAR_AUTOLINK_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_PATCHED).payload.binding).toEqual({
            mailbox_binding_id: 'b1',
            calendar_autolink_status: 'linked',
        });
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.BINDINGS_LOAD_REQUESTED)).toBe(true);
    });

    it('BINDING_CALENDAR_UNLINK_REQUESTED → BINDING_PATCHED со статусом disabled', async () => {
        fetchMock.respondJson('DELETE', '/svc/api/mail/bindings/b1/calendar', {
            mailbox_binding_id: 'b1',
            calendar_autolink_status: 'disabled',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_CALENDAR_UNLINK_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(
            dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_PATCHED).payload.binding.calendar_autolink_status,
        ).toBe('disabled');
    });

    it('BINDING_CALENDAR_AUTOLINK_REQUESTED при ошибке → BINDING_PATCH_FAILED', async () => {
        fetchMock.respondStatus('POST', '/svc/api/mail/bindings/b1/calendar/autolink', 500);
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_CALENDAR_AUTOLINK_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.BINDING_PATCH_FAILED)).toBe(true);
    });

    it('MESSAGES_SEARCH_REQUESTED → MESSAGES_LOADED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/search', {
            items: [{ uid: '7', subject: 'hit' }],
            has_more: false,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_SEARCH_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                q: 'hit',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOADED).payload.items[0].uid).toBe('7');
    });

    it('MESSAGES_LOAD_MORE_REQUESTED → MESSAGES_APPEND_LOADED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/list', {
            items: [{ uid: '2' }],
            next_cursor: null,
            has_more: false,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_LOAD_MORE_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                cursor: 'c1',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_APPEND_LOADED).payload.items).toEqual([
            { uid: '2' },
        ]);
    });

    it('MESSAGE_TRASH / ARCHIVE / STAR request complete', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/trash', {
            uid: '1',
            folder: 'INBOX',
            destination_folder: 'Trash',
        });
        fetchMock.respondJson('POST', '/svc/api/mail/messages/archive', {
            uid: '2',
            folder: 'INBOX',
            destination_folder: 'Archive',
        });
        fetchMock.respondJson('POST', '/svc/api/mail/messages/star', {
            uid: '3',
            flagged: true,
        });
        const trashDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_TRASH_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '1',
            }),
            buildCtx(() => ({ mail: {} }), trashDispatched),
        );
        expect(trashDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_TRASH_COMPLETED)).toBeTruthy();

        const archiveDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_ARCHIVE_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '2',
            }),
            buildCtx(() => ({ mail: {} }), archiveDispatched),
        );
        expect(archiveDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_ARCHIVE_COMPLETED)).toBeTruthy();

        const starDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_STAR_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '3',
                flagged: true,
            }),
            buildCtx(() => ({ mail: {} }), starDispatched),
        );
        expect(starDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_STAR_COMPLETED).payload.flagged).toBe(true);
    });

    it('MESSAGE_RAG_INDEX_REQUESTED → ACCEPTED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/rag-index', {
            accepted: true,
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            uid: '9',
            rag_index_status: 'pending',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_RAG_INDEX_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '9',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        const accepted = dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_RAG_INDEX_ACCEPTED);
        expect(accepted).toBeTruthy();
        expect(accepted.payload.rag_index_status).toBe('pending');
    });

    it('BINDING_MEMBERS_LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/mail/bindings/role1/members', {
            items: [{ user_id: 'u1', role: 'member' }],
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBERS_LOAD_REQUESTED, { mailbox_binding_id: 'role1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBERS_LOADED).payload.items).toHaveLength(1);
    });

    it('OPEN_FROM_NOTIFICATION → FOLDERS_LOAD_REQUESTED', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.OPEN_FROM_NOTIFICATION, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
        });
    });

    it('OPEN_FROM_NOTIFICATION requires mailbox_binding_id', async () => {
        await expect(
            createMailEffect({ baseUrl: '/svc' })(
                ev(MAIL_EVENTS.OPEN_FROM_NOTIFICATION, {}),
                buildCtx(() => ({ mail: {} }), []),
            ),
        ).rejects.toThrow(/mailbox_binding_id/);
    });

    it('FOLDERS_LOAD_REQUESTED empty + needs_sync → SYNC', async () => {
        fetchMock.respondJson(
            'GET',
            '/svc/api/mail/folders?mailbox_binding_id=b1',
            {
                folders: [],
                missing_standard_roles: [],
                needs_sync: true,
            },
        );
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_LOAD_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: null } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOADED).payload.needs_sync).toBe(true);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.SYNC_REQUESTED)).toBe(true);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED)).toBe(false);
    });

    it('FOLDERS_LOAD_REQUESTED → LOADED + messages (folders present, no auto-sync)', async () => {
        fetchMock.respondJson(
            'GET',
            '/svc/api/mail/folders?mailbox_binding_id=b1',
            {
                folders: [{ name: 'INBOX', role: 'inbox' }],
                missing_standard_roles: ['archive'],
                namespace_prefix: 'INBOX.',
                capabilities: ['MOVE'],
                needs_sync: false,
            },
        );
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_LOAD_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        const loaded = dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOADED);
        expect(loaded.payload.folders).toHaveLength(1);
        expect(loaded.payload.missing_standard_roles).toEqual(['archive']);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.SYNC_REQUESTED)).toBe(false);
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
        });
    });

    it('FOLDERS_LOAD_REQUESTED bad shape → FAILED', async () => {
        fetchMock.respondJson('GET', '/svc/api/mail/folders?mailbox_binding_id=b1', { folders: null });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_LOAD_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_FAILED)).toBeTruthy();
    });

    it('FOLDERS_ENSURE_REQUESTED → LOADED + messages', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/folders/ensure', {
            folders: [{ name: 'INBOX' }],
            missing_standard_roles: [],
            capabilities: [],
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(
                () => ({ mail: { folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOADED).payload.folders).toHaveLength(1);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED)).toBe(true);
    });

    it('FOLDERS_ENSURE_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/folders/ensure', new Error('ensure failed'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_ENSURE_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_ENSURE_FAILED).payload.error_code).toBe(
            'unknown',
        );
    });

    it('FOLDERS_REORDER_REQUESTED → PUT order + FOLDERS_LOADED', async () => {
        fetchMock.respondJson('PUT', '/svc/api/mail/folders/order', {
            folders: [
                { name: 'Sent', role: 'sent', sort_index: 0 },
                { name: 'INBOX', role: 'inbox', sort_index: 1 },
            ],
            missing_standard_roles: [],
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_REORDER_REQUESTED, {
                mailbox_binding_id: 'b1',
                folders: [
                    { name: 'Sent', role: 'sent' },
                    { name: 'INBOX', role: 'inbox' },
                ],
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        const loaded = dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOADED);
        expect(loaded.payload.folders.map((folder) => folder.name)).toEqual(['Sent', 'INBOX']);
        expect(fetchMock.calls.some((call) => call.method === 'PUT' && call.url.includes('/folders/order'))).toBe(true);
    });

    it('FOLDERS_REORDER_REQUESTED error → FAILED + reload', async () => {
        fetchMock.respondError('PUT', '/svc/api/mail/folders/order', new Error('reorder failed'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDERS_REORDER_REQUESTED, {
                mailbox_binding_id: 'b1',
                folders: [{ name: 'INBOX' }],
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_REORDER_FAILED)).toBeTruthy();
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            skip_auto_sync: true,
        });
    });

    it('FOLDER_SELECT → MESSAGES_LOAD_REQUESTED', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDER_SELECT, { folder: 'Sent' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'Sent' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'Sent',
        });
    });

    it('FOLDER_SELECT without active mailbox is no-op', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.FOLDER_SELECT, { folder: 'INBOX' }),
            buildCtx(() => ({ mail: { folder: 'INBOX' } }), dispatched),
        );
        expect(dispatched).toHaveLength(0);
    });

    it('MESSAGES_LOAD_REQUESTED with needs_sync and pendingOpenUid', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/list', {
            items: [{ uid: '9' }],
            next_cursor: 'c2',
            has_more: true,
            needs_sync: true,
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_LOAD_REQUESTED, { mailbox_binding_id: 'b1', folder: 'INBOX' }),
            buildCtx(
                () => ({ mail: { pendingOpenUid: '9' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOADED).payload.has_more).toBe(true);
        expect(dispatched.some((d) => d.type === MAIL_EVENTS.SYNC_REQUESTED)).toBe(true);
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload.uid).toBe('9');
    });

    it('MESSAGES_LOAD_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/list', new Error('list boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_LOAD_REQUESTED, { mailbox_binding_id: 'b1', folder: 'INBOX' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_FAILED).payload.error_code).toBe(
            'unknown',
        );
    });

    it('MESSAGES_SEARCH_REQUESTED empty q reloads folder', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_SEARCH_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                q: '   ',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
        });
    });

    it('MESSAGES_SEARCH_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/search', new Error('search boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_SEARCH_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                q: 'x',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_FAILED)).toBeTruthy();
    });

    it('MESSAGES_LOAD_MORE_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/list', new Error('more boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGES_LOAD_MORE_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                cursor: 'c1',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_FAILED)).toBeTruthy();
    });

    it('MESSAGE_SELECT → THREAD_LOAD_REQUESTED', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_SELECT, { uid: '5' }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload).toEqual({
            uid: '5',
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            thread_id: null,
        });
    });

    it('THREAD_LOAD_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/thread', new Error('thread boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.THREAD_LOAD_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_FAILED)).toBeTruthy();
    });

    it('MESSAGE_LOAD_REQUESTED → MESSAGE_LOADED', async () => {
        fetchMock.respondJson(
            'GET',
            '/svc/api/mail/messages/9?mailbox_binding_id=b1&folder=INBOX',
            { uid: '9', subject: 'Hi' },
        );
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_LOAD_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_LOADED).payload.message.uid).toBe('9');
    });

    it('MESSAGE_LOAD_REQUESTED error → FAILED', async () => {
        fetchMock.respondError(
            'GET',
            /\/svc\/api\/mail\/messages\/9\?/,
            new Error('msg boom'),
        );
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_LOAD_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_LOAD_FAILED)).toBeTruthy();
    });

    it('MESSAGE_MARK_UNSEEN_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/mark_unseen', new Error('unseen boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_MARK_UNSEEN_REQUESTED, {
                uid: '9',
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_MARK_UNSEEN_FAILED)).toBeTruthy();
    });

    it('MESSAGE_SEND_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/send', new Error('send boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_SEND_REQUESTED, {
                mailbox_binding_id: 'b1',
                to_addresses: ['a@b.c'],
                subject: 's',
                body_text: 'b',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_SEND_FAILED)).toBeTruthy();
    });

    it('MESSAGE_DELETE_REQUESTED → COMPLETED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/delete', {
            uid: '4',
            folder: 'Trash',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_DELETE_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'Trash',
                uid: '4',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_DELETE_COMPLETED).payload.uid).toBe('4');
    });

    it('MESSAGE_TRASH / ARCHIVE / STAR / DELETE errors → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/trash', new Error('trash boom'));
        fetchMock.respondError('POST', '/svc/api/mail/messages/archive', new Error('archive boom'));
        fetchMock.respondError('POST', '/svc/api/mail/messages/star', new Error('star boom'));
        fetchMock.respondError('POST', '/svc/api/mail/messages/delete', new Error('delete boom'));

        const trashDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_TRASH_REQUESTED, { mailbox_binding_id: 'b1', folder: 'INBOX', uid: '1' }),
            buildCtx(() => ({ mail: {} }), trashDispatched),
        );
        expect(trashDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_TRASH_FAILED)).toBeTruthy();

        const archiveDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_ARCHIVE_REQUESTED, { mailbox_binding_id: 'b1', folder: 'INBOX', uid: '2' }),
            buildCtx(() => ({ mail: {} }), archiveDispatched),
        );
        expect(archiveDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_ARCHIVE_FAILED)).toBeTruthy();

        const starDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_STAR_REQUESTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '3',
                flagged: true,
            }),
            buildCtx(() => ({ mail: {} }), starDispatched),
        );
        expect(starDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_STAR_FAILED)).toBeTruthy();

        const deleteDispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_DELETE_REQUESTED, { mailbox_binding_id: 'b1', folder: 'Trash', uid: '4' }),
            buildCtx(() => ({ mail: {} }), deleteDispatched),
        );
        expect(deleteDispatched.find((d) => d.type === MAIL_EVENTS.MESSAGE_DELETE_FAILED)).toBeTruthy();
    });

    it('DRAFT_SAVE_REQUESTED → DRAFT_SAVED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/messages/drafts', {
            uid: 'd1',
            folder: 'Drafts',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.DRAFT_SAVE_REQUESTED, {
                mailbox_binding_id: 'b1',
                to_addresses: ['a@b.c'],
                subject: 'draft',
                body_text: 'x',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.DRAFT_SAVED).payload.uid).toBe('d1');
    });

    it('DRAFT_SAVE_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/messages/drafts', new Error('draft boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.DRAFT_SAVE_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.DRAFT_SAVE_FAILED)).toBeTruthy();
    });

    it('BINDING_MEMBER_ADD_REQUESTED → ADDED', async () => {
        fetchMock.respondJson('POST', '/svc/api/mail/bindings/role1/members', {
            user_id: 'u2',
            role: 'member',
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBER_ADD_REQUESTED, {
                mailbox_binding_id: 'role1',
                user_id: 'u2',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBER_ADDED).payload.member.user_id).toBe(
            'u2',
        );
    });

    it('BINDING_MEMBER_ADD_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/bindings/role1/members', new Error('add boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBER_ADD_REQUESTED, {
                mailbox_binding_id: 'role1',
                user_id: 'u2',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBER_ADD_FAILED)).toBeTruthy();
    });

    it('BINDING_MEMBER_REMOVE_REQUESTED → REMOVED', async () => {
        fetchMock.respondStatus('DELETE', '/svc/api/mail/bindings/role1/members/u2', 204);
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBER_REMOVE_REQUESTED, {
                mailbox_binding_id: 'role1',
                user_id: 'u2',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBER_REMOVED).payload).toEqual({
            mailbox_binding_id: 'role1',
            user_id: 'u2',
        });
    });

    it('BINDING_MEMBER_REMOVE_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('DELETE', '/svc/api/mail/bindings/role1/members/u2', new Error('remove boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBER_REMOVE_REQUESTED, {
                mailbox_binding_id: 'role1',
                user_id: 'u2',
            }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBER_REMOVE_FAILED)).toBeTruthy();
    });

    it('BINDING_MEMBERS_LOAD_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('GET', '/svc/api/mail/bindings/role1/members', new Error('members boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDING_MEMBERS_LOAD_REQUESTED, { mailbox_binding_id: 'role1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDING_MEMBERS_LOAD_FAILED)).toBeTruthy();
    });

    it('SYNC_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/sync', new Error('sync boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.SYNC_REQUESTED, { mailbox_binding_id: 'b1' }),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.SYNC_FAILED)).toBeTruthy();
    });

    it('HEALTHCHECK_REQUESTED error → FAILED', async () => {
        fetchMock.respondError('POST', '/svc/api/mail/connection/healthcheck', new Error('hc boom'));
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.HEALTHCHECK_REQUESTED, null),
            buildCtx(() => ({ mail: {} }), dispatched),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.HEALTHCHECK_FAILED)).toBeTruthy();
    });

    it('notify ignores other mailbox and missing folder', async () => {
        const otherMailbox = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev('notify/mail/mail_new_message_received', {
                data: { mailbox_binding_id: 'other', uid: '1' },
            }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                otherMailbox,
            ),
        );
        expect(otherMailbox).toHaveLength(0);

        const noFolder = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev('notify/mail/mail_new_message_received', {
                data: { mailbox_binding_id: 'b1', uid: '1' },
            }),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1' } }),
                noFolder,
            ),
        );
        expect(noFolder).toHaveLength(0);
    });

    it('MESSAGE_UPSERTED no-op without matching selection', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_UPSERTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '99',
                thread_id: 't-other',
            }),
            buildCtx(
                () => ({
                    mail: {
                        activeMailboxBindingId: 'b1',
                        folder: 'INBOX',
                        selectedUid: '1',
                        selectedThreadId: 't1',
                    },
                }),
                dispatched,
            ),
        );
        expect(dispatched).toHaveLength(0);
    });

    it('MESSAGE_UPSERTED reloads when thread_id matches', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_UPSERTED, {
                mailbox_binding_id: 'b1',
                folder: 'INBOX',
                uid: '100',
                thread_id: 't1',
            }),
            buildCtx(
                () => ({
                    mail: {
                        activeMailboxBindingId: 'b1',
                        folder: 'INBOX',
                        selectedUid: '1',
                        selectedThreadId: 't1',
                    },
                }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            uid: '1',
        });
    });

    it('MESSAGE_UPSERTED keeps selectedUid folder across thread siblings', async () => {
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.MESSAGE_UPSERTED, {
                mailbox_binding_id: 'b1',
                folder: 'Sent',
                uid: '605',
                thread_id: 't1',
            }),
            buildCtx(
                () => ({
                    mail: {
                        activeMailboxBindingId: 'b1',
                        folder: 'INBOX',
                        selectedUid: '538',
                        selectedThreadId: 't1',
                        selectedMessage: { uid: '538', folder: 'INBOX' },
                        selectedThreadMessages: [
                            { uid: '538', folder: 'INBOX' },
                            { uid: '605', folder: 'Sent' },
                        ],
                    },
                }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.THREAD_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
            uid: '538',
        });
    });
});
