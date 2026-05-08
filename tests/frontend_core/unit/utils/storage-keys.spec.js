import { describe, it, expect } from 'vitest';
import { platformStorageKey } from '../../../../core/frontend/static/lib/utils/storage-keys.js';

describe('platformStorageKey', () => {
    it('валидные scope+key', () => {
        expect(platformStorageKey('core', 'theme')).toBe('platform:core:theme');
        expect(platformStorageKey('sync', 'channel.selected')).toBe('platform:sync:channel.selected');
        expect(platformStorageKey('crm', 'last_namespace_by_company')).toBe('platform:crm:last_namespace_by_company');
    });

    it('throws на невалидный scope', () => {
        expect(() => platformStorageKey('humanitec', 'theme')).toThrow();
        expect(() => platformStorageKey('', 'theme')).toThrow();
        expect(() => platformStorageKey('CRM', 'theme')).toThrow();
    });

    it('throws на невалидный key', () => {
        expect(() => platformStorageKey('sync', '')).toThrow();
        expect(() => platformStorageKey('sync', 'Foo Bar')).toThrow();
        expect(() => platformStorageKey('sync', '_leading_underscore')).toThrow();
        expect(() => platformStorageKey('sync', '1starts_with_digit')).toThrow();
    });
});
