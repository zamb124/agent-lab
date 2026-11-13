/**
 * TsdScanInput: burst-детектор HID-сканера, ручной ввод, корнер-кейсы.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    TsdScanInput,
    TSD_SCAN_MIN_LENGTH,
    TSD_NATIVE_SCAN_EVENT,
} from '../../../apps/stock/ui/pages/tsd/scan/scan-input.js';

class FakeKeyboardTarget {
    handlers = new Map<string, EventListener>();

    addEventListener(type: string, handler: EventListener, _capture?: boolean): void {
        this.handlers.set(type, handler);
    }

    removeEventListener(type: string): void {
        this.handlers.delete(type);
    }

    private _handler(type: string): EventListener {
        const handler = this.handlers.get(type);
        if (handler === undefined) throw new Error(`handler not attached: ${type}`);
        return handler;
    }

    key(key: string, mods: Partial<Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'altKey' | 'repeat'>> = {}, eventTarget: EventTarget | null = null): void {
        (this._handler('keydown') as (event: KeyboardEvent) => void)({
            key,
            ctrlKey: mods.ctrlKey ?? false,
            metaKey: mods.metaKey ?? false,
            altKey: mods.altKey ?? false,
            repeat: mods.repeat ?? false,
            target: eventTarget,
            preventDefault: () => undefined,
            stopPropagation: () => undefined,
        } as KeyboardEvent);
    }

    nativeScan(detail: unknown): void {
        this._handler(TSD_NATIVE_SCAN_EVENT)({ detail } as unknown as Event);
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

    it('сканер без суффикса: конец пачки коммитится таймаутом', () => {
        target.typeKeys('NOSUFFIX1', 5);
        vi.advanceTimersByTime(200);
        expect(scans).toEqual(['NOSUFFIX1']);
    });

    it('пачка без терминатора короче минимума не эмитится таймаутом', () => {
        target.typeKeys('AB', 5);
        vi.advanceTimersByTime(500);
        expect(scans).toEqual([]);
    });

    it('Enter после таймаут-коммита не дублирует скан', () => {
        target.typeKeys('STALE', 5);
        vi.advanceTimersByTime(500);
        expect(scans).toEqual(['STALE']);
        target.key('Enter');
        expect(scans).toEqual(['STALE']);
    });

    it('Tab-терминатор коммитит код как Enter (Zebra/Honeywell)', () => {
        target.typeKeys('TABCODE9', 5);
        target.key('Tab');
        expect(scans).toEqual(['TABCODE9']);
    });

    it('управляющие обёртки STX/ETX не попадают в код', () => {
        target.key('\x02');
        target.typeKeys('WRAPPED3', 5);
        target.key('\x03');
        target.key('Enter');
        expect(scans).toEqual(['WRAPPED3']);
    });

    it('GS (\\x1d, FNC1) сохраняется в коде — разделитель AI GS1', () => {
        target.typeKeys('01046012345', 4);
        target.key('\x1d');
        target.typeKeys('10LOT77', 4);
        target.key('Enter');
        expect(scans).toEqual(['01046012345\x1d10LOT77']);
    });

    it('печать внутри input не уходит сканом', () => {
        const field = { tagName: 'INPUT' } as unknown as EventTarget;
        for (const ch of 'QTYFIELD') {
            target.key(ch, {}, field);
        }
        target.key('Enter', {}, field);
        expect(scans).toEqual([]);
    });

    it('печать внутри contenteditable не уходит сканом', () => {
        const field = { tagName: 'DIV', isContentEditable: true } as unknown as EventTarget;
        target.key('A', {}, field);
        target.key('B', {}, field);
        target.key('C', {}, field);
        target.key('Enter', {}, field);
        expect(scans).toEqual([]);
    });

    it('зажатая клавиша (auto-repeat) не эмитит фантомный скан', () => {
        target.key('a');
        for (let i = 0; i < 12; i += 1) {
            target.key('a', { repeat: true });
            vi.advanceTimersByTime(30);
        }
        vi.advanceTimersByTime(500);
        target.key('Enter');
        expect(scans).toEqual([]);
    });

    it('auto-repeat не ломает идущий рядом настоящий скан', () => {
        target.typeKeys('GOOD77', 5);
        target.key('x', { repeat: true });
        target.key('Enter');
        expect(scans).toEqual(['GOOD77']);
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

    it('native-мост: CustomEvent с кодом эмитит скан без пачки', () => {
        target.nativeScan({ code: '  DW-123456  ' });
        expect(scans).toEqual(['DW-123456']);
    });

    it('native-мост: код короче минимума отбрасывается', () => {
        target.nativeScan({ code: 'ab' });
        expect(scans).toEqual([]);
    });

    it('native-мост: событие без detail.code игнорируется', () => {
        target.nativeScan(null);
        target.nativeScan({ other: 'x' });
        target.nativeScan({ code: 42 });
        expect(scans).toEqual([]);
    });
});
