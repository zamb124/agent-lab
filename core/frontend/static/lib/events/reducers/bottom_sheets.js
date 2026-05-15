/**
 * Bottom sheets slice — нижние выезжающие панели для вторичной сложности (mobile shell 2026).
 *
 * state.bottomSheets:
 *   stack: Array<{ id, kind, props, openedAt, closing?, closingAt? }>
 *
 * Открытие — UI_BOTTOM_SHEET_OPEN_REQUESTED ({ kind, props? }).
 * Закрытие — UI_BOTTOM_SHEET_CLOSE_REQUESTED ({ kind?, id? }) или
 *            UI_BOTTOM_SHEET_CLOSED (то же тело, эмитится из самого листа).
 *
 * Семантика стека: топовый элемент рендерится поверх предыдущих (как у modals.stack).
 * Без полей: при отсутствии `kind`/`id` снимается верхний элемент.
 */

import { CoreEvents } from '../contract.js';

export const initialBottomSheetsState = Object.freeze({
    stack: [],
});

let _bottomSheetSeq = 0;
function _nextBottomSheetId() {
    _bottomSheetSeq += 1;
    return `bs_${_bottomSheetSeq.toString(36)}`;
}

function _withClosing(item, ts) {
    if (item.closing === true) return item;
    return { ...item, closing: true, closingAt: ts };
}

function _markClosingById(state, id, ts) {
    let changed = false;
    const stack = state.stack.map((item) => {
        if (item.id !== id) return item;
        const next = _withClosing(item, ts);
        if (next !== item) changed = true;
        return next;
    });
    return changed ? { ...state, stack } : state;
}

function _markClosingByKind(state, kind, ts) {
    let changed = false;
    const stack = state.stack.slice();
    for (let i = stack.length - 1; i >= 0; i -= 1) {
        const item = stack[i];
        if (item.kind !== kind || item.closing === true) continue;
        stack[i] = _withClosing(item, ts);
        changed = true;
        break;
    }
    return changed ? { ...state, stack } : state;
}

function _markTopClosing(state, ts) {
    const stack = state.stack.slice();
    for (let i = stack.length - 1; i >= 0; i -= 1) {
        const item = stack[i];
        if (item.closing === true) continue;
        stack[i] = _withClosing(item, ts);
        return { ...state, stack };
    }
    return state;
}

function _removeById(state, id) {
    const next = state.stack.filter((s) => s.id !== id);
    if (next.length === state.stack.length) return state;
    return { ...state, stack: next };
}

function _removeByKind(state, kind) {
    let removed = false;
    const next = [];
    for (let i = state.stack.length - 1; i >= 0; i -= 1) {
        const item = state.stack[i];
        if (!removed && item.kind === kind) {
            removed = true;
            continue;
        }
        next.unshift(item);
    }
    return removed ? { ...state, stack: next } : state;
}

export function bottomSheetsReducer(state = initialBottomSheetsState, event) {
    switch (event.type) {
        case CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED: {
            const p = event.payload || {};
            const kind = p.kind;
            if (typeof kind !== 'string' || kind.length === 0) return state;
            const sheet = {
                id: typeof p.id === 'string' && p.id.length > 0 ? p.id : _nextBottomSheetId(),
                kind,
                props: p.props || {},
                openedAt: event.meta.ts,
            };
            return { ...state, stack: [...state.stack, sheet] };
        }
        case CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED: {
            const p = event.payload || {};
            const id = typeof p.id === 'string' && p.id.length > 0 ? p.id : null;
            const kind = typeof p.kind === 'string' && p.kind.length > 0 ? p.kind : null;
            if (id !== null) {
                return _markClosingById(state, id, event.meta.ts);
            }
            if (kind !== null) {
                return _markClosingByKind(state, kind, event.meta.ts);
            }
            if (state.stack.length === 0) return state;
            return _markTopClosing(state, event.meta.ts);
        }
        case CoreEvents.UI_BOTTOM_SHEET_CLOSED: {
            const p = event.payload || {};
            const id = typeof p.id === 'string' && p.id.length > 0 ? p.id : null;
            const kind = typeof p.kind === 'string' && p.kind.length > 0 ? p.kind : null;
            if (id !== null) return _removeById(state, id);
            if (kind !== null) return _removeByKind(state, kind);
            if (state.stack.length === 0) return state;
            return { ...state, stack: state.stack.slice(0, -1) };
        }
        default:
            return state;
    }
}

export const bottomSheetsSlice = {
    reducer: bottomSheetsReducer,
    initial: initialBottomSheetsState,
};
