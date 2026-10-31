import { describe, it, expect } from 'vitest';
import {
    bottomSheetsReducer,
    initialBottomSheetsState,
} from '@platform/lib/events/reducers/bottom_sheets.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload, ts = 1234) => ({
    id: `id_${type}`,
    type,
    payload,
    meta: { ts, source: 'local' },
});

describe('bottomSheetsReducer', () => {
    it('initial: пустой stack', () => {
        expect(initialBottomSheetsState.stack).toEqual([]);
    });

    it('OPEN_REQUESTED добавляет sheet в stack', () => {
        const next = bottomSheetsReducer(
            initialBottomSheetsState,
            ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's1', kind: 'crm.workspace_picker', props: { a: 1 } }),
        );
        expect(next.stack).toHaveLength(1);
        expect(next.stack[0].id).toBe('s1');
        expect(next.stack[0].kind).toBe('crm.workspace_picker');
        expect(next.stack[0].props).toEqual({ a: 1 });
    });

    it('CLOSE_REQUESTED с id помечает sheet closing', () => {
        let s = bottomSheetsReducer(initialBottomSheetsState, ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's1', kind: 'a.b' }));
        s = bottomSheetsReducer(s, ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's2', kind: 'a.c' }));
        const next = bottomSheetsReducer(s, ev(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { id: 's1' }));
        expect(next.stack.map((item) => item.id)).toEqual(['s1', 's2']);
        expect(next.stack[0].closing).toBe(true);
        expect(next.stack[1].closing).toBeUndefined();
    });

    it('CLOSE_REQUESTED без id/kind помечает верхний sheet closing', () => {
        let s = bottomSheetsReducer(initialBottomSheetsState, ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's1', kind: 'a.b' }));
        s = bottomSheetsReducer(s, ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's2', kind: 'a.c' }));
        const next = bottomSheetsReducer(s, ev(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, null));
        expect(next.stack).toHaveLength(2);
        expect(next.stack[0].closing).toBeUndefined();
        expect(next.stack[1].closing).toBe(true);
    });

    it('CLOSED удаляет sheet из stack', () => {
        const seeded = bottomSheetsReducer(
            initialBottomSheetsState,
            ev(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { id: 's1', kind: 'a.b' }),
        );
        const next = bottomSheetsReducer(seeded, ev(CoreEvents.UI_BOTTOM_SHEET_CLOSED, { id: 's1' }));
        expect(next.stack).toEqual([]);
    });
});
