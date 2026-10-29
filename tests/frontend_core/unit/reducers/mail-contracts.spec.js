import { describe, it, expect } from 'vitest';
import { mailReducer, initialMailState, MAIL_EVENTS } from '@platform/lib/events/reducers/mail.js';

const ev = (type, payload = {}) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });
const reduce = (state, type, payload) => mailReducer(state, ev(type, payload));

describe('mailReducer: валидация записей', () => {
    it.each([
        [{ uid: 1 }, /uid must be a string/],
        [{ uid: 'a', folder: 1 }, /folder must be a string/],
        [{ uid: 'a', unread: 'yes' }, /unread must be a boolean/],
        [{ uid: 'a', flagged: 'yes' }, /flagged must be a boolean/],
        [{ uid: 'a', rag_index_status: 1 }, /rag_index_status must be a string/],
        ['text', /message must be an object/],
    ])('MESSAGES_LOADED отклоняет сообщение %j', (message, error) => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.MESSAGES_LOADED, { items: [message] })).toThrow(error);
    });

    it.each([
        [{ name: 1 }, /name must be a string/],
        [{ name: 'a', role: 1 }, /role must be a string/],
        [{ name: 'a', unseen_count: 'x' }, /unseen_count must be a number/],
        [{ name: 'a', selectable: 'x' }, /selectable must be a boolean/],
        ['text', /folder must be an object/],
    ])('FOLDERS_LOADED отклоняет папку %j', (folder, error) => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.FOLDERS_LOADED, { folders: [folder] })).toThrow(error);
    });

    it.each([
        [{ mailbox_binding_id: 1 }, /mailbox_binding_id must be a string/],
        [{ mailbox_binding_id: 'a', is_default: 'x' }, /is_default must be a boolean/],
        [{ mailbox_binding_id: 'a', user_id: 1 }, /user_id must be a string/],
        ['text', /binding must be an object/],
    ])('BINDINGS_LOADED отклоняет binding %j', (binding, error) => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, { items: [binding], can_admin: true })).toThrow(error);
    });

    it('BINDINGS_LOADED требует boolean can_admin и массив items', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, { items: [] })).toThrow(/can_admin/);
        expect(() => reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, { items: 'x', can_admin: true })).toThrow(/items/);
        expect(() => reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, null)).toThrow(/items/);
    });

    it('BINDINGS_LOADED без default выбирает первый binding, пустой список даёт null', () => {
        const first = reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, {
            items: [{ mailbox_binding_id: 'b1' }, { mailbox_binding_id: 'b2' }],
            can_admin: true,
        });
        expect(first.activeMailboxBindingId).toBe('b1');
        const kept = reduce({ ...first, activeMailboxBindingId: 'b2' }, MAIL_EVENTS.BINDINGS_LOADED, {
            items: [{ mailbox_binding_id: 'b1' }, { mailbox_binding_id: 'b2' }],
            can_admin: true,
        });
        expect(kept.activeMailboxBindingId).toBe('b2');
        const empty = reduce(initialMailState, MAIL_EVENTS.BINDINGS_LOADED, { items: [], can_admin: false });
        expect(empty.activeMailboxBindingId).toBeNull();
    });
});

describe('mailReducer: запросы и ошибки', () => {
    it('load_requested события включают loading и сбрасывают ошибку', () => {
        const next = reduce({ ...initialMailState, errorMessage: 'x' }, MAIL_EVENTS.FOLDERS_LOAD_REQUESTED, {});
        expect(next.loading).toBe(true);
        expect(next.errorMessage).toBeNull();
    });

    it('MESSAGE_LOAD_REQUESTED очищает выбранное письмо', () => {
        const next = reduce(
            { ...initialMailState, selectedMessage: { uid: '1' } },
            MAIL_EVENTS.MESSAGE_LOAD_REQUESTED,
            {},
        );
        expect(next.messageLoading).toBe(true);
        expect(next.selectedMessage).toBeNull();
    });

    it('ошибка форматируется с error_params', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.SYNC_FAILED, {
            error_code: 'boom',
            error_params: { n: 1, flag: true, name: 'a' },
        });
        expect(next.syncInProgress).toBe(false);
        expect(next.errorMessage).toBe('boom');
    });

    it('ошибка без error_params допустима, non-object params игнорируются', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.SYNC_FAILED, { error_code: 'boom', error_params: 'x' });
        expect(next.errorMessage).toBe('boom');
    });

    it('ошибка требует error_code и скалярные params', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.SYNC_FAILED, {})).toThrow(/error_code required/);
        expect(() => reduce(initialMailState, MAIL_EVENTS.SYNC_FAILED, {
            error_code: 'boom',
            error_params: { nested: {} },
        })).toThrow(/error_params values/);
    });

    it('MESSAGE_LOAD_FAILED сбрасывает messageLoading', () => {
        const next = reduce(
            { ...initialMailState, messageLoading: true },
            MAIL_EVENTS.MESSAGE_LOAD_FAILED,
            { error_code: 'boom' },
        );
        expect(next.messageLoading).toBe(false);
        expect(next.errorMessage).toBe('boom');
    });

    it('THREAD_LOAD_FAILED берёт message или текст по умолчанию', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.THREAD_LOAD_FAILED, { message: 'bad' }).errorMessage).toBe('bad');
        expect(reduce(initialMailState, MAIL_EVENTS.THREAD_LOAD_FAILED, {}).errorMessage).toBe('mail thread load failed');
    });
});

describe('mailReducer: загрузка данных', () => {
    it('COMPANY_BINDINGS_LOADED сохраняет список', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.COMPANY_BINDINGS_LOADED, {
            items: [{ mailbox_binding_id: 'c1' }],
        });
        expect(next.companyBindings).toEqual([{ mailbox_binding_id: 'c1' }]);
    });

    it('CONNECTION_LOADED и CONNECTION_SAVED сохраняют connection', () => {
        const loaded = reduce(initialMailState, MAIL_EVENTS.CONNECTION_LOADED, { connection: { host: 'h' } });
        expect(loaded.connection).toEqual({ host: 'h' });
        const saved = reduce(loaded, MAIL_EVENTS.CONNECTION_SAVED, {});
        expect(saved.connection).toBeNull();
    });

    it('HEALTHCHECK_COMPLETED сохраняет health', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.HEALTHCHECK_COMPLETED, { health: { ok: true } });
        expect(next.health).toEqual({ ok: true });
        expect(reduce(next, MAIL_EVENTS.HEALTHCHECK_COMPLETED, {}).health).toBeNull();
    });

    it('ADMIN_MODE_SET переключает adminMode', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.ADMIN_MODE_SET, { open: true }).adminMode).toBe(true);
        expect(reduce(initialMailState, MAIL_EVENTS.ADMIN_MODE_SET, { open: false }).adminMode).toBe(false);
    });

    it('OPEN_FROM_NOTIFICATION выбирает ящик и письмо', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.OPEN_FROM_NOTIFICATION, {
            mailbox_binding_id: 'b1',
            uid: 'u1',
        });
        expect(next.activeMailboxBindingId).toBe('b1');
        expect(next.pendingOpenUid).toBe('u1');
        expect(next.selectedUid).toBe('u1');
        expect(next.folder).toBeNull();
    });

    it('OPEN_FROM_NOTIFICATION требует mailbox_binding_id и uid', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.OPEN_FROM_NOTIFICATION, { uid: 'u1' })).toThrow(/mailbox_binding_id/);
        expect(() => reduce(initialMailState, MAIL_EVENTS.OPEN_FROM_NOTIFICATION, { mailbox_binding_id: 'b1' })).toThrow(/uid required/);
    });

    it('MAILBOX_SELECT и FOLDER_SELECT без значения не меняют state', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.MAILBOX_SELECT, {})).toBe(initialMailState);
        expect(reduce(initialMailState, MAIL_EVENTS.FOLDER_SELECT, {})).toBe(initialMailState);
    });

    it('THREAD_SELECT и MESSAGE_SELECT без uid не меняют state, thread_id сохраняется', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.THREAD_SELECT, {})).toBe(initialMailState);
        const next = reduce(initialMailState, MAIL_EVENTS.MESSAGE_SELECT, { uid: 'u1', thread_id: 't1' });
        expect(next.selectedThreadId).toBe('t1');
        expect(next.messageLoading).toBe(true);
    });
});

describe('mailReducer: папки', () => {
    const folders = [
        { name: 'Archive', role: 'archive', selectable: true },
        { name: 'Inbox', role: 'inbox', selectable: true },
        { name: 'Hidden', role: 'inbox', selectable: false },
    ];

    it('FOLDERS_LOADED выбирает inbox и сбрасывает список при смене папки', () => {
        const next = reduce(
            { ...initialMailState, messages: [{ uid: '1' }], pendingOpenUid: 'u9' },
            MAIL_EVENTS.FOLDERS_LOADED,
            { folders, missing_standard_roles: ['trash'], needs_sync: true },
        );
        expect(next.folder).toBe('Inbox');
        expect(next.messages).toEqual([]);
        expect(next.selectedUid).toBe('u9');
        expect(next.missingStandardRoles).toEqual(['trash']);
        expect(next.needsSync).toBe(true);
    });

    it('FOLDERS_LOADED сохраняет выбранную папку, если она доступна', () => {
        const next = reduce({ ...initialMailState, folder: 'Archive' }, MAIL_EVENTS.FOLDERS_LOADED, { folders });
        expect(next.folder).toBe('Archive');
    });

    it('FOLDERS_LOADED без inbox берёт первую выбираемую папку, без папок даёт null', () => {
        const first = reduce(initialMailState, MAIL_EVENTS.FOLDERS_LOADED, {
            folders: [{ name: 'Sent', selectable: true }],
        });
        expect(first.folder).toBe('Sent');
        const none = reduce(initialMailState, MAIL_EVENTS.FOLDERS_LOADED, { folders: [] });
        expect(none.folder).toBeNull();
    });

    it('FOLDERS_LOADED требует массив folders', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.FOLDERS_LOADED, {})).toThrow(/folders must be an array/);
    });

    it('FOLDERS_REORDER_REQUESTED проверяет payload', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.FOLDERS_REORDER_REQUESTED, {})).toThrow(/folders must be an array/);
        expect(() => reduce(initialMailState, MAIL_EVENTS.FOLDERS_REORDER_REQUESTED, { folders: [] })).toThrow(/mailbox_binding_id/);
    });

    it('MESSAGE_UPSERTED с флагом обновляет flagged и не двигает счётчик без delta', () => {
        const seeded = {
            ...initialMailState,
            activeMailboxBindingId: 'b1',
            folder: 'Inbox',
            folders: [{ name: 'Inbox', unseen_count: 2 }],
            messages: [{ uid: 'u1', flagged: false }],
        };
        const flagged = reduce(seeded, MAIL_EVENTS.MESSAGE_UPSERTED, {
            mailbox_binding_id: 'b1',
            uid: 'u1',
            flagged: true,
        });
        expect(flagged.messages[0].flagged).toBe(true);
        expect(flagged.folders[0].unseen_count).toBe(2);
    });

    it('MESSAGE_UPSERTED уменьшает счётчик не ниже нуля', () => {
        const seeded = {
            ...initialMailState,
            activeMailboxBindingId: 'b1',
            folder: 'Inbox',
            folders: [{ name: 'Inbox', unseen_count: 1 }, { name: 'Other' }],
        };
        const next = reduce(seeded, MAIL_EVENTS.MESSAGE_UPSERTED, {
            mailbox_binding_id: 'b1',
            unread_delta: -5,
        });
        expect(next.folders[0].unseen_count).toBe(0);
        expect(next.folders[1]).toEqual({ name: 'Other' });
    });

    it('MESSAGE_UPSERTED требует mailbox_binding_id в пустом payload', () => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.MESSAGE_UPSERTED, null)).toThrow(/mailbox_binding_id required/);
    });
});

describe('mailReducer: письма и треды', () => {
    const seeded = {
        ...initialMailState,
        folder: 'Inbox',
        folders: [{ name: 'Inbox', unseen_count: 3 }],
        messages: [{ uid: 'u1', unread: true, folder: 'Inbox' }, { uid: 'u2', unread: false }],
        selectedUid: 'u1',
    };

    it('THREAD_LOADED помечает прочитанным и уменьшает счётчик', () => {
        const next = reduce(seeded, MAIL_EVENTS.THREAD_LOADED, {
            thread: {
                thread_id: 't1',
                items: [
                    { uid: 'u1', unread: true, folder: 'Inbox' },
                    { uid: 'u3', unread: false, folder: 'Sent' },
                ],
            },
        });
        expect(next.selectedThreadId).toBe('t1');
        expect(next.selectedMessage.uid).toBe('u1');
        expect(next.messages[0].unread).toBe(false);
        expect(next.folders[0].unseen_count).toBe(2);
        expect(next.selectedThreadMessages).toHaveLength(2);
    });

    it('THREAD_LOADED без выбранного uid фокусируется на последнем письме', () => {
        const next = reduce({ ...seeded, selectedUid: null }, MAIL_EVENTS.THREAD_LOADED, {
            thread: { items: [{ uid: 'a' }, { uid: 'b' }] },
        });
        expect(next.selectedMessage.uid).toBe('b');
        expect(next.selectedThreadId).toBeNull();
    });

    it('THREAD_LOADED с пустым тредом сбрасывает выбранное письмо', () => {
        const next = reduce(seeded, MAIL_EVENTS.THREAD_LOADED, { thread: { items: [] } });
        expect(next.selectedMessage).toBeNull();
        expect(next.selectedUid).toBe('u1');
    });

    it('THREAD_LOADED требует thread.items', () => {
        expect(() => reduce(seeded, MAIL_EVENTS.THREAD_LOADED, {})).toThrow(/thread.items/);
    });

    it('MESSAGE_LOADED отмечает письмо прочитанным и уменьшает счётчик', () => {
        const next = reduce(seeded, MAIL_EVENTS.MESSAGE_LOADED, { message: { uid: 'u1', body: 'x' } });
        expect(next.selectedMessage.uid).toBe('u1');
        expect(next.messages[0].unread).toBe(false);
        expect(next.folders[0].unseen_count).toBe(2);
        expect(next.selectedThreadMessages[0].folder).toBe('Inbox');
    });

    it('MESSAGE_LOADED без письма очищает выбор', () => {
        const next = reduce(seeded, MAIL_EVENTS.MESSAGE_LOADED, {});
        expect(next.selectedMessage).toBeNull();
        expect(next.selectedThreadMessages).toEqual([]);
        expect(next.folders).toBe(seeded.folders);
    });

    it('MESSAGE_MARK_UNSEEN_COMPLETED обновляет выбранное письмо и тред', () => {
        const state = {
            ...seeded,
            selectedMessage: { uid: 'u2', unread: false },
            selectedThreadMessages: [{ uid: 'u2', unread: false }, { uid: 'u9', unread: false }],
        };
        const next = reduce(state, MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED, { uid: 'u2' });
        expect(next.selectedMessage.unread).toBe(true);
        expect(next.selectedThreadMessages[0].unread).toBe(true);
        expect(next.selectedThreadMessages[1].unread).toBe(false);
        expect(next.folders[0].unseen_count).toBe(4);
    });

    it('MESSAGE_MARK_UNSEEN_COMPLETED для уже непрочитанного не меняет счётчик', () => {
        const next = reduce(seeded, MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED, { uid: 'u1' });
        expect(next.folders).toBe(seeded.folders);
        expect(reduce(seeded, MAIL_EVENTS.MESSAGE_MARK_UNSEEN_COMPLETED, {})).toBe(seeded);
    });

    it('MESSAGE_STAR_COMPLETED обновляет выбранное письмо', () => {
        const state = { ...seeded, selectedMessage: { uid: 'u1', flagged: false } };
        const next = reduce(state, MAIL_EVENTS.MESSAGE_STAR_COMPLETED, { uid: 'u1', flagged: true });
        expect(next.selectedMessage.flagged).toBe(true);
        expect(reduce(state, MAIL_EVENTS.MESSAGE_STAR_COMPLETED, { flagged: true })).toBe(state);
    });

    it('MESSAGE_RAG_INDEX_ACCEPTED выставляет статус индексации', () => {
        const next = reduce(seeded, MAIL_EVENTS.MESSAGE_RAG_INDEX_ACCEPTED, {
            uid: 'u2',
            rag_index_status: 'queued',
        });
        expect(next.messages[1].rag_index_status).toBe('queued');
        expect(reduce(seeded, MAIL_EVENTS.MESSAGE_RAG_INDEX_ACCEPTED, { uid: 'u2' })).toBe(seeded);
    });

    it('удаление выбранного письма сбрасывает выбор, пустой uid игнорируется', () => {
        const state = { ...seeded, selectedThreadId: 't1', selectedMessage: { uid: 'u1' } };
        const next = reduce(state, MAIL_EVENTS.MESSAGE_DELETE_COMPLETED, { uid: 'u1' });
        expect(next.selectedUid).toBeNull();
        expect(next.selectedThreadId).toBeNull();
        expect(next.selectedMessage).toBeNull();
        expect(reduce(state, MAIL_EVENTS.MESSAGE_REMOVED, {})).toBe(state);
        expect(reduce(state, MAIL_EVENTS.MESSAGE_MOVED, {})).toBe(state);
    });

    it('DRAFT_SAVED сохраняет uid черновика', () => {
        const saved = reduce(initialMailState, MAIL_EVENTS.DRAFT_SAVED, { uid: 'd1' });
        expect(saved.draftUid).toBe('d1');
        expect(reduce(saved, MAIL_EVENTS.DRAFT_SAVED, {}).draftUid).toBe('d1');
    });
});

describe('mailReducer: compose', () => {
    const attachment = { filename: 'a.txt', content_type: 'text/plain', file_id: 'f1', size: 3, url: 'u' };

    it('COMPOSE_DRAFT_SET принимает вложения, in_reply_to и references', () => {
        const next = reduce(initialMailState, MAIL_EVENTS.COMPOSE_DRAFT_SET, {
            to: 'a@x',
            subject: 's',
            body: 'b',
            body_html: '<p>b</p>',
            in_reply_to: '<m1>',
            references: '<m0>',
            attachments: [attachment, { ...attachment, url: undefined }],
        });
        expect(next.compose.in_reply_to).toBe('<m1>');
        expect(next.compose.references).toBe('<m0>');
        expect(next.compose.body_html).toBe('<p>b</p>');
        expect(next.compose.attachments[0].url).toBe('u');
        expect(next.compose.attachments[1].url).toBeNull();
    });

    it.each([
        ['x', /attachments must be an array/],
        [['x'], /attachment must be object/],
        [[{ ...attachment, filename: '' }], /filename required/],
        [[{ ...attachment, content_type: '' }], /content_type required/],
        [[{ ...attachment, file_id: '' }], /file_id required/],
        [[{ ...attachment, content_base64: 'AAA' }], /content_base64 forbidden/],
        [[{ ...attachment, size: '3' }], /size required/],
    ])('COMPOSE_DRAFT_SET отклоняет вложения %j', (attachments, error) => {
        expect(() => reduce(initialMailState, MAIL_EVENTS.COMPOSE_DRAFT_SET, { attachments })).toThrow(error);
    });

    it('MESSAGE_SENT очищает compose и sending', () => {
        const state = { ...initialMailState, sending: true, compose: { ...initialMailState.compose, to: 'a@x' } };
        const next = reduce(state, MAIL_EVENTS.MESSAGE_SENT, {});
        expect(next.sending).toBe(false);
        expect(next.compose.to).toBe('');
    });
});

describe('mailReducer: привязки ящиков', () => {
    it('DEFAULT_SET без владельца переключает default во всех привязках', () => {
        const state = {
            ...initialMailState,
            bindings: [{ mailbox_binding_id: 'b1', is_default: true }, { mailbox_binding_id: 'b2', is_default: false }],
            companyBindings: [{ mailbox_binding_id: 'b1', is_default: true }],
        };
        const next = reduce(state, MAIL_EVENTS.DEFAULT_SET, { binding: { mailbox_binding_id: 'b2' } });
        expect(next.bindings.map((item) => item.is_default)).toEqual([false, true]);
        expect(next.companyBindings[0].is_default).toBe(false);
        expect(next.activeMailboxBindingId).toBe('b2');
    });

    it('DEFAULT_SET и BINDING_CREATED без binding не меняют state', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.DEFAULT_SET, {})).toBe(initialMailState);
        expect(reduce(initialMailState, MAIL_EVENTS.BINDING_CREATED, {})).toBe(initialMailState);
    });

    it('BINDING_PATCHED заменяет существующую привязку', () => {
        const state = {
            ...initialMailState,
            bindings: [{ mailbox_binding_id: 'b1', title: 'old' }],
            companyBindings: [{ mailbox_binding_id: 'b1', title: 'old' }],
        };
        const next = reduce(state, MAIL_EVENTS.BINDING_PATCHED, { binding: { mailbox_binding_id: 'b1', title: 'new' } });
        expect(next.bindings[0].title).toBe('new');
        expect(next.companyBindings[0].title).toBe('new');
    });

    it('BINDING_DELETED без id не меняет state', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.BINDING_DELETED, {})).toBe(initialMailState);
    });

    it('участники привязки: пропуск без идентификаторов', () => {
        expect(reduce(initialMailState, MAIL_EVENTS.BINDING_MEMBERS_LOADED, { items: [] })).toBe(initialMailState);
        expect(() => reduce(initialMailState, MAIL_EVENTS.BINDING_MEMBERS_LOADED, {
            mailbox_binding_id: 'b1',
            items: ['x'],
        })).toThrow(/member must be an object/);
        expect(reduce(initialMailState, MAIL_EVENTS.BINDING_MEMBER_ADDED, {})).toBe(initialMailState);
        expect(reduce(initialMailState, MAIL_EVENTS.BINDING_MEMBER_REMOVED, {})).toBe(initialMailState);
    });
});
