import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createMailEffect } from '@platform/lib/events/effects/mail.effect.js';
import { MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
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
        });
        const dispatched = [];
        await createMailEffect({ baseUrl: '/svc' })(
            ev(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null),
            buildCtx(
                () => ({ mail: { activeMailboxBindingId: 'b1', folder: 'INBOX' } }),
                dispatched,
            ),
        );
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.BINDINGS_LOADED).payload.items).toHaveLength(1);
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

    it('notify/mail/mail_new_message_received reloads open inbox', async () => {
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
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.FOLDERS_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
        });
        expect(dispatched.find((d) => d.type === MAIL_EVENTS.MESSAGES_LOAD_REQUESTED).payload).toEqual({
            mailbox_binding_id: 'b1',
            folder: 'INBOX',
        });
    });
});
