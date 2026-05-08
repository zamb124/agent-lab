import { describe, it, expect } from 'vitest';
import {
    EMAIL_RE,
    PHONE_DIGITS_MIN,
    isValidEmail,
    digitsOnly,
    isValidPhone,
} from '../../../../core/frontend/static/lib/utils/validators.js';

describe('isValidEmail', () => {
    it('валидные email', () => {
        expect(isValidEmail('a@b.c')).toBe(true);
        expect(isValidEmail('user@example.com')).toBe(true);
        expect(isValidEmail('  user@example.com  ')).toBe(true);
    });

    it('невалидные', () => {
        expect(isValidEmail('a@b')).toBe(false);
        expect(isValidEmail('a.b.c')).toBe(false);
        expect(isValidEmail('')).toBe(false);
        expect(isValidEmail(null)).toBe(false);
        expect(isValidEmail(undefined)).toBe(false);
    });
});

describe('digitsOnly', () => {
    it('извлекает цифры', () => {
        expect(digitsOnly('+7 (495) 123-45-67')).toBe('74951234567');
        expect(digitsOnly('abc')).toBe('');
        expect(digitsOnly(null)).toBe('');
    });
});

describe('isValidPhone', () => {
    it('минимум PHONE_DIGITS_MIN цифр', () => {
        expect(PHONE_DIGITS_MIN).toBe(10);
        expect(isValidPhone('+7 (495) 123-45-67')).toBe(true);
        expect(isValidPhone('123')).toBe(false);
        expect(isValidPhone('')).toBe(false);
    });
});

describe('EMAIL_RE', () => {
    it('экспортируется', () => {
        expect(EMAIL_RE).toBeInstanceOf(RegExp);
        expect(EMAIL_RE.test('a@b.c')).toBe(true);
    });
});
