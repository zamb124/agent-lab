import { describe, it, expect } from 'vitest';
import {
    fileTypesReducer,
    initialFileTypesState,
    FILE_TYPES_EVENTS,
    selectExtensionsFor,
    selectMimesFor,
    selectAcceptStringFor,
    selectIsAllowedFile,
} from '@platform/lib/events/reducers/file-types.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

const seedState = (extra = {}) => ({
    fileTypes: {
        loaded: true,
        categories: ['image', 'document'],
        registry: [
            { extension: '.png', mime_types: ['image/png'], category: 'image' },
            { extension: '.pdf', mime_types: ['application/pdf'], category: 'document' },
            ...(extra.registry || []),
        ],
        error: null,
    },
});

describe('fileTypesReducer', () => {
    it('LOADED перезаписывает state', () => {
        const next = fileTypesReducer(initialFileTypesState, ev(FILE_TYPES_EVENTS.LOADED, {
            categories: ['image'],
            registry: [{ extension: '.jpg', mime_types: ['image/jpeg'], category: 'image' }],
        }));
        expect(next.loaded).toBe(true);
        expect(next.registry).toHaveLength(1);
    });

    it('LOAD_FAILED фиксирует error', () => {
        const next = fileTypesReducer(initialFileTypesState, ev(FILE_TYPES_EVENTS.LOAD_FAILED, { message: 'no bundle' }));
        expect(next.error).toBe('no bundle');
    });
});

describe('selectExtensionsFor', () => {
    it('возвращает расширения по категории', () => {
        const exts = selectExtensionsFor(seedState(), 'image');
        expect(exts).toEqual(['.png']);
    });

    it('пусто для неизвестной категории', () => {
        expect(selectExtensionsFor(seedState(), 'audio')).toEqual([]);
    });
});

describe('selectMimesFor', () => {
    it('возвращает уникальный список MIME', () => {
        const mimes = selectMimesFor(seedState(), 'image', 'document');
        expect(mimes.sort()).toEqual(['application/pdf', 'image/png']);
    });
});

describe('selectAcceptStringFor', () => {
    it('добавляет image/* для категории image', () => {
        const accept = selectAcceptStringFor(seedState(), 'image');
        expect(accept).toBe('image/*,.png');
    });

    it('document — только расширения', () => {
        expect(selectAcceptStringFor(seedState(), 'document')).toBe('.pdf');
    });
});

describe('selectIsAllowedFile', () => {
    it('пропускает по MIME', () => {
        const file = { type: 'image/png', name: 'x.png' };
        expect(selectIsAllowedFile(seedState(), file, 'image')).toBe(true);
    });

    it('пропускает по расширению при отсутствии MIME', () => {
        const file = { type: '', name: 'doc.pdf' };
        expect(selectIsAllowedFile(seedState(), file, 'document')).toBe(true);
    });

    it('false для чужой категории', () => {
        const file = { type: 'audio/mp3', name: 'song.mp3' };
        expect(selectIsAllowedFile(seedState(), file, 'image')).toBe(false);
    });
});
