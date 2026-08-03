import { describe, it, expect } from 'vitest';
import { buildA2aFileParts } from '@platform/lib/chat/runtime/a2a-stream.js';

describe('buildA2aFileParts', () => {
    it('maps url parts', () => {
        expect(
            buildA2aFileParts([
                {
                    url: '/frontend/api/v1/files/download/f1',
                    filename: 'a.txt',
                    mediaType: 'text/plain',
                },
            ]),
        ).toEqual([
            {
                url: '/frontend/api/v1/files/download/f1',
                filename: 'a.txt',
                mediaType: 'text/plain',
            },
        ]);
    });

    it('rejects raw', () => {
        expect(() => buildA2aFileParts([{ raw: 'YWJj', filename: 'a.txt' }])).toThrow(
            /raw forbidden/,
        );
    });

    it('rejects data', () => {
        expect(() => buildA2aFileParts([{ data: 'YWJj', name: 'a.txt' }])).toThrow(
            /data forbidden/,
        );
    });

    it('rejects file.bytes', () => {
        expect(() =>
            buildA2aFileParts([{ file: { bytes: 'YWJj', name: 'a.txt' } }]),
        ).toThrow(/file\.bytes forbidden/);
    });

    it('rejects missing url', () => {
        expect(() => buildA2aFileParts([{ filename: 'a.txt' }])).toThrow(/url required/);
    });
});
