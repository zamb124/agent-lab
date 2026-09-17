import { describe, it, expect } from 'vitest';
import {
    guestDisplayNameFromSenderId,
    isGuestSenderId,
} from '../../../apps/sync/ui/_helpers/sync-guest-sender.js';

describe('sync-guest-sender', () => {
    it('isGuestSenderId: префикс guest:', () => {
        expect(isGuestSenderId('guest:aabbccdd:артем')).toBe(true);
        expect(isGuestSenderId('guest:aabbccdd')).toBe(true);
        expect(isGuestSenderId('user_1')).toBe(false);
        expect(() => isGuestSenderId(null)).toThrow();
    });

    it('guestDisplayNameFromSenderId: имя из identity', () => {
        expect(guestDisplayNameFromSenderId('guest:aabbccdd:артем')).toBe('артем');
        expect(guestDisplayNameFromSenderId('guest:aabb:foo:bar')).toBe('foo:bar');
        expect(guestDisplayNameFromSenderId('guest:aabbccdd')).toBe(null);
        expect(guestDisplayNameFromSenderId('guest:aabbccdd:')).toBe(null);
        expect(guestDisplayNameFromSenderId('user_1')).toBe(null);
        expect(() => guestDisplayNameFromSenderId(null)).toThrow();
    });
});
