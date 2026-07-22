import { describe, it, expect } from 'vitest';
import { decodeImapModifiedUtf7 } from '@platform/lib/utils/imap-utf7.js';
import { reorderByInsertIndex } from '@platform/lib/utils/reorder-by-insert-index.js';

describe('decodeImapModifiedUtf7', () => {
    it('leaves plain ASCII unchanged', () => {
        expect(decodeImapModifiedUtf7('INBOX')).toBe('INBOX');
        expect(decodeImapModifiedUtf7('Sent')).toBe('Sent');
    });

    it('decodes IMAP modified UTF-7 Cyrillic label', () => {
        // "&BCEEPwQwBDw-" — IMAP modified UTF-7 для «Спам»
        expect(decodeImapModifiedUtf7('&BCEEPwQwBDw-')).toBe('Спам');
    });

    it('decodes escaped ampersand', () => {
        expect(decodeImapModifiedUtf7('A-&-B')).toBe('A-&B');
    });
});

describe('reorderByInsertIndex', () => {
    it('moves item across insert gap', () => {
        expect(reorderByInsertIndex(['a', 'b', 'c'], 0, 3)).toEqual(['b', 'c', 'a']);
        expect(reorderByInsertIndex(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b']);
    });

    it('no-ops adjacent insert', () => {
        expect(reorderByInsertIndex(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'b', 'c']);
        expect(reorderByInsertIndex(['a', 'b', 'c'], 1, 2)).toEqual(['a', 'b', 'c']);
    });
});
