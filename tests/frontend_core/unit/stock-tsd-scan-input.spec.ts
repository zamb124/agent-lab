/**
 * TsdScanInput: burst-детектор HID-сканера, ручной ввод, корнер-кейсы.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TsdScanInput, TSD_SCAN_MIN_LENGTH } from '../../../apps/stock/ui/pages/tsd/scan/scan-input.js';

class FakeKeyboardTarget {
    handler: ((event: KeyboardEvent) => void) | null = null;

    addEventListener(_type: string, handler: EventListener, _capture?: boolean): void {
        this.handler = handler as (event: KeyboardEvent) => void;
    }

    removeEventListener(): void {
        this.handler = null;
    }

    key(key: string, mods: Partial<Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'altKey'>> = {}): void {
        if (this.handler === null) throw new Error('handler not attached');
        this.handler({
            key,
            ctrlKey: mods.ctrlKey ?? false,
            metaKey: mods.metaKey ?? false,
            altKey: mods.altKey ?? false,
            preventDefault: () => undefined,
            stopPropagation: () => undefined,
        } as KeyboardEvent);
    }

    typeKeys(chars: string, gapMs: number): void {
        for (const ch of chars) {
            this.key(ch);
            vi.advanceTimersByTime(gapMs);
        }
    }
}

describe('TsdScanInput', () => {
    let target: FakeKeyboardTarget;
    let scans: string[];
    let input: TsdScanInput;

    beforeEach(() => {
        vi.useFakeTimers();
        target = new FakeKeyboardTarget();
        scans = [];
        input = new TsdScanInput((code) => scans.push(code), { target: target as unknown as Window });
        input.attach();
    });

    afterEach(() => {
        input.detach();
        vi.useRealTimers();
    });

    it('аппаратный сканер: быстрая пачка + Enter эмитит код', () => {
        target.typeKeys('ABC12345', 5);
        target.key('Enter');
        expect(scans).toEqual(['ABC12345']);
    });

    it('длинный код со спецсимволами эмитится целиком', () => {
        target.typeKeys('4607012345678-X_1', 4);
        target.key('Enter');
        expect(scans).toEqual(['4607012345678-X_1']);
    });

    it('человеческий ввод (медленный) не эмитит скан по Enter', () => {
        target.typeKeys('SLOWCODE', 150);
        target.key('Enter');
        expect(scans).toEqual([]);
    });

    it('код короче минимума отбрасывается', () => {
        target.typeKeys('AB', 5);
        target.key('Enter');
        expect(scans).toEqual([]);
    });

    it('Enter без скана не трогает дальнейший ввод', () => {
        target.key('Enter');
        target.typeKeys('NEXT123', 5);
        target.key('Enter');
        expect(scans).toEqual(['NEXT123']);
    });

    it('модификаторы игнорируются (Ctrl+C не ломает буфер)', () => {
        target.key('c', { ctrlKey: true });
        target.typeKeys('OK999', 5);
        target.key('Enter');
        expect(scans).toEqual(['OK999']);
    });

    it('непечатная клавиша (Shift/F5) сбрасывает буфер', () => {
        target.typeKeys('PART', 5);
        target.key('Shift');
        target.typeKeys('IA', 5);
        target.key('Enter');
        expect(scans).toEqual([]);
    });

    it('долгая пауза обнуляет недопечатанный буфер', () => {
        target.typeKeys('STALE', 5);
        vi.advanceTimersByTime(500);
        target.key('Enter');
        expect(scans).toEqual([]);
    });

    it('два скана подряд эмитятся независимо', () => {
        target.typeKeys('FIRST01', 5);
        target.key('Enter');
        target.typeKeys('SECOND02', 5);
        target.key('Enter');
        expect(scans).toEqual(['FIRST01', 'SECOND02']);
    });

    it('после detach клавиши не обрабатываются', () => {
        input.detach();
        expect(() => target.typeKeys('NOPE1', 5)).toThrow();
    });

    it('ручной submit эмитит нормализованный код', () => {
        input.submit('  MANUAL42  ');
        expect(scans).toEqual(['MANUAL42']);
    });

    it('ручной submit короче минимума отбрасывается', () => {
        input.submit('ab');
        expect(scans).toEqual([]);
        expect(TSD_SCAN_MIN_LENGTH).toBe(3);
    });

    it('ручной submit из пробелов отбрасывается', () => {
        input.submit('   ');
        expect(scans).toEqual([]);
    });
});
