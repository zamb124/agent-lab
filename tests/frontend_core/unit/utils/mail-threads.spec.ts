import { describe, it, expect } from 'vitest';
import {
    findThreadByUid,
    findThreadMessageByMessageId,
    groupMailThreads,
    mailReplyPreviewText,
    normalizeMailSubject,
    threadRootId,
} from '@platform/lib/utils/mail-threads.js';

describe('mail-threads', () => {
    it('normalizeMailSubject strips reply prefixes', () => {
        expect(normalizeMailSubject('Re: Re: Hello')).toBe('hello');
        expect(normalizeMailSubject('Fwd: Hello')).toBe('hello');
    });

    it('threadRootId prefers references root', () => {
        expect(threadRootId({
            uid: '9',
            message_id: '<c@x>',
            in_reply_to: '<b@x>',
            references: '<a@x> <b@x>',
        })).toBe('<a@x>');
    });

    it('groupMailThreads merges reply chain and sorts newest thread first', () => {
        const threads = groupMailThreads([
            {
                uid: '2',
                message_id: '<b@x>',
                in_reply_to: '<a@x>',
                references: '<a@x>',
                subject: 'Re: topic',
                from_address: 'b@x',
                snippet: 'reply',
                unread: true,
                date: '2026-07-19T12:00:00Z',
                attachment_count: 0,
            },
            {
                uid: '1',
                message_id: '<a@x>',
                subject: 'topic',
                from_address: 'a@x',
                snippet: 'hello',
                unread: false,
                date: '2026-07-19T11:00:00Z',
                attachment_count: 1,
            },
            {
                uid: '9',
                message_id: '<solo@x>',
                subject: 'other',
                from_address: 'c@x',
                snippet: 'solo',
                unread: true,
                date: '2026-07-19T13:00:00Z',
                attachment_count: 0,
            },
        ]);
        expect(threads).toHaveLength(2);
        expect(threads[0]?.threadId).toBe('<solo@x>');
        expect(threads[1]?.threadId).toBe('<a@x>');
        expect(threads[1]?.messages.map((m) => m.uid)).toEqual(['1', '2']);
        expect(threads[1]?.unreadCount).toBe(1);
        expect(threads[1]?.attachmentCount).toBe(1);
        expect(threads[1]?.participants).toEqual(['a@x', 'b@x']);
        expect(findThreadByUid(threads, '2')?.threadId).toBe('<a@x>');
    });

    it('groupMailThreads falls back to normalized subject', () => {
        const threads = groupMailThreads([
            {
                uid: '1',
                subject: 'Ping',
                from_address: 'a@x',
                date: '2026-07-19T11:00:00Z',
            },
            {
                uid: '2',
                subject: 'Re: Ping',
                from_address: 'b@x',
                date: '2026-07-19T12:00:00Z',
            },
        ]);
        expect(threads).toHaveLength(1);
        expect(threads[0]?.threadId).toBe('subject:ping');
        expect(threads[0]?.messages).toHaveLength(2);
    });

    it('findThreadMessageByMessageId matches normalized Message-ID', () => {
        const messages = [
            { uid: '1', message_id: '<a@x>', body_text: 'root' },
            { uid: '2', message_id: 'b@x', body_text: 'child' },
        ];
        expect(findThreadMessageByMessageId(messages, '<a@x>')?.uid).toBe('1');
        expect(findThreadMessageByMessageId(messages, 'a@x')?.uid).toBe('1');
        expect(findThreadMessageByMessageId(messages, '<b@x>')?.uid).toBe('2');
        expect(findThreadMessageByMessageId(messages, '<missing@x>')).toBeNull();
        expect(findThreadMessageByMessageId(messages, '')).toBeNull();
        expect(findThreadMessageByMessageId(messages, null)).toBeNull();
    });

    it('mailReplyPreviewText prefers snippet and truncates', () => {
        expect(mailReplyPreviewText({
            snippet: '  short note  ',
            body_text: 'longer body ignored',
        })).toBe('short note');
        expect(mailReplyPreviewText({
            body_text: 'first line\n\nsecond',
        })).toBe('first line second');
        const long = 'x'.repeat(100);
        const preview = mailReplyPreviewText({ body_text: long }, 80);
        expect(preview.length).toBe(80);
        expect(preview.endsWith('…')).toBe(true);
        expect(mailReplyPreviewText(null)).toBe('');
        expect(mailReplyPreviewText({})).toBe('');
    });
});
