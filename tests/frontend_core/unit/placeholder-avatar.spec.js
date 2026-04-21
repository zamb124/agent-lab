import { describe, it, expect } from 'vitest';
import {
    PLACEHOLDER_AVATAR_CDN_BASE,
    PLACEHOLDER_AVATAR_COLLECTIONS,
    DEFAULT_PLACEHOLDER_AVATAR_COLLECTION,
    PLACEHOLDER_NON_PERSON_COLLECTION,
    PLACEHOLDER_MEETING_COLLECTION,
    getPlaceholderAvatarUrl,
    resolveAvatarImageSrc,
    placeholderAvatarIndexFromSeed,
} from '@platform/lib/utils/placeholder-avatar.js';

describe('placeholder-avatar', () => {
    it('getPlaceholderAvatarUrl: одинаковый seed даёт одинаковый URL', () => {
        const a = getPlaceholderAvatarUrl('user_abc');
        const b = getPlaceholderAvatarUrl('user_abc');
        expect(a).toBe(b);
        expect(a.startsWith(PLACEHOLDER_AVATAR_CDN_BASE)).toBe(true);
    });

    it('getPlaceholderAvatarUrl: детерминированный выбор файла в коллекции', () => {
        const files = PLACEHOLDER_AVATAR_COLLECTIONS.memo;
        const idx = placeholderAvatarIndexFromSeed('stable_seed', files.length);
        expect(getPlaceholderAvatarUrl('stable_seed')).toBe(`${PLACEHOLDER_AVATAR_CDN_BASE}${files[idx]}`);
    });

    it('getPlaceholderAvatarUrl: пустой seed — throw', () => {
        expect(() => getPlaceholderAvatarUrl('')).toThrow();
    });

    it('getPlaceholderAvatarUrl: неизвестная collection — throw', () => {
        expect(() => getPlaceholderAvatarUrl('x', { collection: 'nope' })).toThrow();
    });

    it('getPlaceholderAvatarUrl: коллекции notion и vibrent', () => {
        const n = getPlaceholderAvatarUrl('u1', { collection: 'notion' });
        const v = getPlaceholderAvatarUrl('u1', { collection: 'vibrent' });
        expect(n).toContain('notion_');
        expect(v).toContain('vibrent_');
        expect(n).not.toBe(v);
    });

    it('getPlaceholderAvatarUrl: toon / 3d / upstream (не memo)', () => {
        expect(getPlaceholderAvatarUrl('c1', { collection: 'toon' })).toContain('toon_');
        expect(getPlaceholderAvatarUrl('c1', { collection: '3d' })).toContain('3d_');
        expect(getPlaceholderAvatarUrl('c1', { collection: 'upstream' })).toContain('upstream_');
        expect(PLACEHOLDER_NON_PERSON_COLLECTION).toBe('toon');
        expect(PLACEHOLDER_MEETING_COLLECTION).toBe('upstream');
        expect(PLACEHOLDER_AVATAR_COLLECTIONS['3d'].length).toBe(5);
    });

    it('DEFAULT_PLACEHOLDER_AVATAR_COLLECTION совпадает с дефолтом getPlaceholderAvatarUrl', () => {
        expect(DEFAULT_PLACEHOLDER_AVATAR_COLLECTION).toBe('memo');
    });

    it('resolveAvatarImageSrc: непустой avatarUrl после trim — remote', () => {
        const r = resolveAvatarImageSrc({ avatarUrl: '  https://example.com/a.png  ', seed: 'u' });
        expect(r.kind).toBe('remote');
        expect(r.src).toBe('https://example.com/a.png');
    });

    it('resolveAvatarImageSrc: нет URL — placeholder с seed', () => {
        const r = resolveAvatarImageSrc({ avatarUrl: null, seed: 'user_x' });
        expect(r.kind).toBe('placeholder');
        expect(r.src).toBe(getPlaceholderAvatarUrl('user_x'));
    });

    it('resolveAvatarImageSrc: пустой seed без URL — throw', () => {
        expect(() => resolveAvatarImageSrc({ avatarUrl: '', seed: '' })).toThrow();
    });

    it('resolveAvatarImageSrc: args не объект — throw', () => {
        expect(() => resolveAvatarImageSrc(null)).toThrow();
    });
});
