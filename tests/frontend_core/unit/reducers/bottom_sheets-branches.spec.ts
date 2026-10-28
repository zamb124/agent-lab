/**
 * Ветки bottomSheetsReducer: автоматический id, закрытие по kind, повторное закрытие,
 * удаление по kind и верхнего элемента, неизвестные события.
 */

import { describe, expect, it } from 'vitest';
import { CoreEvents, createEvent } from '@platform/lib/events/contract.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import {
    bottomSheetsReducer,
    initialBottomSheetsState,
} from '@platform/lib/events/reducers/bottom_sheets.js';
import type { BottomSheetsState } from '@platform/lib/events/reducers/bottom_sheets.js';

function event(type: string, payload: unknown, ts = 1000): PlatformEvent {
    return createEvent(type, payload, { ts, source: 'local' });
}

function open(state: BottomSheetsState, payload: unknown): BottomSheetsState {
    return bottomSheetsReducer(state, event(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, payload));
}

describe('bottomSheetsReducer: открытие', () => {
    it('без kind состояние не меняется', () => {
        expect(open(initialBottomSheetsState, { id: 'x' })).toBe(initialBottomSheetsState);
        expect(open(initialBottomSheetsState, null)).toBe(initialBottomSheetsState);
        expect(open(initialBottomSheetsState, { kind: '' })).toBe(initialBottomSheetsState);
    });

    it('без id генерирует уникальный id и пустые props', () => {
        const state = open(open(initialBottomSheetsState, { kind: 'a.b' }), { kind: 'a.b' });
        const [first, second] = state.stack;
        expect(first?.id).toMatch(/^bs_/);
        expect(second?.id).toMatch(/^bs_/);
        expect(first?.id).not.toBe(second?.id);
        expect(first?.props).toEqual({});
        expect(first?.openedAt).toBe(1000);
    });
});

describe('bottomSheetsReducer: закрытие по запросу', () => {
    const seeded = open(open(open(initialBottomSheetsState, { id: 's1', kind: 'a.b' }), { id: 's2', kind: 'a.c' }), { id: 's3', kind: 'a.b' });

    it('по kind закрывает верхний подходящий sheet', () => {
        const next = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { kind: 'a.b' }, 2000));
        expect(next.stack.map((item) => item.closing === true)).toEqual([false, false, true]);
        expect(next.stack[2]?.closingAt).toBe(2000);
    });

    it('по kind пропускает уже закрывающийся sheet', () => {
        const once = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { kind: 'a.b' }));
        const twice = bottomSheetsReducer(once, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { kind: 'a.b' }));
        expect(twice.stack.map((item) => item.closing === true)).toEqual([true, false, true]);
    });

    it('по несуществующему kind или id состояние то же', () => {
        expect(bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { kind: 'none' }))).toBe(seeded);
        expect(bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { id: 'none' }))).toBe(seeded);
    });

    it('повторное закрытие по id не меняет состояние', () => {
        const once = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { id: 's1' }));
        expect(bottomSheetsReducer(once, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { id: 's1' }))).toBe(once);
    });

    it('без полей закрывает верхний ещё не закрывающийся sheet', () => {
        const once = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null));
        const twice = bottomSheetsReducer(once, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null));
        expect(twice.stack.map((item) => item.closing === true)).toEqual([false, true, true]);
    });

    it('когда все закрываются, а стек не пуст, состояние то же', () => {
        let state = seeded;
        for (let i = 0; i < 3; i += 1) {
            state = bottomSheetsReducer(state, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null));
        }
        expect(bottomSheetsReducer(state, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null))).toBe(state);
    });

    it('пустой стек не меняется', () => {
        expect(bottomSheetsReducer(initialBottomSheetsState, event(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null))).toBe(
            initialBottomSheetsState,
        );
    });
});

describe('bottomSheetsReducer: CLOSED', () => {
    const seeded = open(open(open(initialBottomSheetsState, { id: 's1', kind: 'a.b' }), { id: 's2', kind: 'a.c' }), { id: 's3', kind: 'a.b' });

    it('по kind снимает верхний sheet этого kind', () => {
        const next = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSED, { kind: 'a.b' }));
        expect(next.stack.map((item) => item.id)).toEqual(['s1', 's2']);
    });

    it('без полей снимает верхний sheet', () => {
        const next = bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSED, null));
        expect(next.stack.map((item) => item.id)).toEqual(['s1', 's2']);
    });

    it('несуществующий id или kind и пустой стек не меняют состояние', () => {
        expect(bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSED, { id: 'none' }))).toBe(seeded);
        expect(bottomSheetsReducer(seeded, event(CoreEvents.UI_BOTTOM_SHEET_CLOSED, { kind: 'none' }))).toBe(seeded);
        expect(bottomSheetsReducer(initialBottomSheetsState, event(CoreEvents.UI_BOTTOM_SHEET_CLOSED, null))).toBe(
            initialBottomSheetsState,
        );
    });

    it('чужое событие не меняет состояние', () => {
        expect(bottomSheetsReducer(seeded, event('svc/other/happened', null))).toBe(seeded);
    });

    it('без состояния берётся initial', () => {
        expect(bottomSheetsReducer(undefined, event('svc/other/happened', null))).toBe(initialBottomSheetsState);
    });
});
