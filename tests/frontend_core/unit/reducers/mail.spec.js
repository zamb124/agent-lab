import { describe, it, expect } from 'vitest';
import { mailReducer, initialMailState, MAIL_EVENTS, mailSlice } from '@platform/lib/events/reducers/mail.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('mailReducer', () => {
    it('initial', () => {
        expect(initialMailState.bindings).toEqual([]);
        expect(initialMailState.folder).toBeNull();
        expect(initialMailState.messageLoading).toBe(false);
        expect(mailSlice.initial).toBe(initialMailState);
    });

    it('BINDINGS_LOADED picks default active mailbox', () => {
        const next = mailReducer(
            initialMailState,
            ev(MAIL_EVENTS.BINDINGS_LOADED, {
                items: [
                    { mailbox_binding_id: 'b1', is_default: false, email_address: 'a@x' },
                    { mailbox_binding_id: 'b2', is_default: true, email_address: 'b@x' },
                ],
            }),
        );
        expect(next.activeMailboxBindingId).toBe('b2');
        expect(next.bindings).toHaveLength(2);
    });

    it('MAILBOX_SELECT clears messages', () => {
        const seeded = {
            ...initialMailState,
            messages: [{ uid: '1' }],
            selectedUid: '1',
            activeMailboxBindingId: 'b1',
        };
        const next = mailReducer(seeded, ev(MAIL_EVENTS.MAILBOX_SELECT, { mailbox_binding_id: 'b2' }));
        expect(next.activeMailboxBindingId).toBe('b2');
        expect(next.messages).toEqual([]);
        expect(next.selectedUid).toBeNull();
    });

    it('MESSAGES_LOADED requires items', () => {
        expect(() => mailReducer(initialMailState, ev(MAIL_EVENTS.MESSAGES_LOADED, {}))).toThrow(/items/);
        const next = mailReducer(
            initialMailState,
            ev(MAIL_EVENTS.MESSAGES_LOADED, { items: [{ uid: '1' }] }),
        );
        expect(next.messages).toEqual([{ uid: '1' }]);
        expect(next.loading).toBe(false);
    });

    it('COMPOSE_DRAFT_SET merges fields', () => {
        const next = mailReducer(
            initialMailState,
            ev(MAIL_EVENTS.COMPOSE_DRAFT_SET, { to: 'a@b.c', subject: 'Hi' }),
        );
        expect(next.compose.to).toBe('a@b.c');
        expect(next.compose.subject).toBe('Hi');
        expect(next.compose.body).toBe('');
    });

    it('DEFAULT_SET updates flags', () => {
        const seeded = {
            ...initialMailState,
            bindings: [
                { mailbox_binding_id: 'b1', is_default: true },
                { mailbox_binding_id: 'b2', is_default: false },
            ],
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.DEFAULT_SET, { binding: { mailbox_binding_id: 'b2', is_default: true } }),
        );
        expect(next.activeMailboxBindingId).toBe('b2');
        expect(next.bindings.find((b) => b.mailbox_binding_id === 'b2').is_default).toBe(true);
        expect(next.bindings.find((b) => b.mailbox_binding_id === 'b1').is_default).toBe(false);
    });

    it('BINDING_CREATED appends companyBindings', () => {
        const next = mailReducer(
            initialMailState,
            ev(MAIL_EVENTS.BINDING_CREATED, { binding: { mailbox_binding_id: 'nb' } }),
        );
        expect(next.companyBindings).toEqual([{ mailbox_binding_id: 'nb' }]);
    });

    it('BINDING_DELETED removes companyBindings', () => {
        const seeded = {
            ...initialMailState,
            companyBindings: [{ mailbox_binding_id: 'nb' }],
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.BINDING_DELETED, { mailbox_binding_id: 'nb' }),
        );
        expect(next.companyBindings).toEqual([]);
    });

    it('MESSAGE_SEND_REQUESTED sets sending', () => {
        const next = mailReducer(initialMailState, ev(MAIL_EVENTS.MESSAGE_SEND_REQUESTED, {}));
        expect(next.sending).toBe(true);
        const done = mailReducer(next, ev(MAIL_EVENTS.MESSAGE_SENT, {}));
        expect(done.sending).toBe(false);
        expect(done.compose.to).toBe('');
    });

    it('FOLDER_SELECT clears selection', () => {
        const seeded = {
            ...initialMailState,
            messages: [{ uid: '1' }],
            selectedUid: '1',
            folder: 'INBOX',
        };
        const next = mailReducer(seeded, ev(MAIL_EVENTS.FOLDER_SELECT, { folder: 'Sent' }));
        expect(next.folder).toBe('Sent');
        expect(next.messages).toEqual([]);
    });

    it('THREAD_SELECT starts messageLoading and clears body', () => {
        const seeded = {
            ...initialMailState,
            selectedMessage: { uid: '1', subject: 'old' },
            selectedUid: '1',
            selectedThreadMessages: [{ uid: '1' }],
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.THREAD_SELECT, { uid: '2', thread_id: '<t>' }),
        );
        expect(next.selectedUid).toBe('2');
        expect(next.selectedThreadId).toBe('<t>');
        expect(next.selectedMessage).toBeNull();
        expect(next.selectedThreadMessages).toEqual([]);
        expect(next.messageLoading).toBe(true);
    });

    it('THREAD_LOADED clears messageLoading and marks thread unread false in list', () => {
        const seeded = {
            ...initialMailState,
            messageLoading: true,
            selectedUid: '3',
            folder: 'INBOX',
            folders: [{ name: 'INBOX', role: 'inbox', selectable: true, unseen_count: 3 }],
            messages: [
                { uid: '1', unread: true },
                { uid: '3', unread: true },
                { uid: '9', unread: true },
            ],
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.THREAD_LOADED, {
                thread: {
                    thread_id: '<root>',
                    subject: 'hi',
                    items: [
                        { folder: 'INBOX', uid: '1', subject: 'hi', unread: false },
                        { folder: 'Sent', uid: '10', subject: 'Re: hi', unread: false },
                        { folder: 'INBOX', uid: '3', subject: 'Re: hi', unread: false },
                    ],
                },
            }),
        );
        expect(next.messageLoading).toBe(false);
        expect(next.selectedThreadId).toBe('<root>');
        expect(next.selectedThreadMessages).toHaveLength(3);
        expect(next.selectedMessage.uid).toBe('3');
        expect(next.messages.find((m) => m.uid === '1').unread).toBe(false);
        expect(next.messages.find((m) => m.uid === '3').unread).toBe(false);
        expect(next.messages.find((m) => m.uid === '9').unread).toBe(true);
        expect(next.folders[0].unseen_count).toBe(1);
    });

    it('MESSAGE_MARK_UNSEEN_COMPLETED restores unread and increments folder badge', () => {
        const seeded = {
            ...initialMailState,
            folder: 'INBOX',
            folders: [{ name: 'INBOX', role: 'inbox', selectable: true, unseen_count: 1 }],
            messages: [{ uid: '2', unread: false }],
            selectedUid: '2',
            selectedMessage: { uid: '2', unread: false, subject: 'hi' },
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED, { uid: '2', unread: true }),
        );
        expect(next.messages[0].unread).toBe(true);
        expect(next.selectedMessage.unread).toBe(true);
        expect(next.folders[0].unseen_count).toBe(2);
    });

    it('FOLDERS_LOADED keeps list when folder unchanged', () => {
        const seeded = {
            ...initialMailState,
            folder: 'INBOX',
            messages: [{ uid: '1' }],
            selectedUid: '1',
            selectedMessage: { uid: '1' },
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.FOLDERS_LOADED, {
                folders: [
                    { name: 'INBOX', role: 'inbox', selectable: true, unseen_count: 2 },
                    { name: 'Sent', role: 'sent', selectable: true, unseen_count: 0 },
                ],
                missing_standard_roles: [],
            }),
        );
        expect(next.messages).toEqual([{ uid: '1' }]);
        expect(next.selectedUid).toBe('1');
        expect(next.folders[0].unseen_count).toBe(2);
    });

    it('failed events store errorMessage', () => {
        const next = mailReducer(
            { ...initialMailState, loading: true },
            ev(MAIL_EVENTS.MESSAGES_LOAD_FAILED, { message: 'boom' }),
        );
        expect(next.loading).toBe(false);
        expect(next.errorMessage).toBe('boom');
    });

    it('BINDING_PATCHED updates calendar_color on bindings', () => {
        const seeded = {
            ...initialMailState,
            bindings: [
                {
                    mailbox_binding_id: 'b1',
                    email_address: 'a@x',
                    calendar_color: 'default',
                    is_default: true,
                },
            ],
            companyBindings: [
                {
                    mailbox_binding_id: 'b1',
                    email_address: 'a@x',
                    calendar_color: 'default',
                    is_default: true,
                },
            ],
            loading: true,
        };
        const next = mailReducer(
            seeded,
            ev(MAIL_EVENTS.BINDING_PATCHED, {
                binding: {
                    mailbox_binding_id: 'b1',
                    email_address: 'a@x',
                    calendar_color: 'mint',
                    is_default: true,
                },
            }),
        );
        expect(next.loading).toBe(false);
        expect(next.bindings[0].calendar_color).toBe('mint');
        expect(next.companyBindings[0].calendar_color).toBe('mint');
    });
});
