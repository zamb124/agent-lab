/**
 * Modals slice.
 *
 * Поля state.modals:
 *   stack: Array<{ id, kind, props, openedAt }>
 */

import { CoreEvents } from '../contract.js';

export const initialModalsState = Object.freeze({
    stack: [],
});

let _modalSeq = 0;
function _nextModalId() {
    _modalSeq += 1;
    return `modal_${_modalSeq.toString(36)}`;
}

export function modalsReducer(state = initialModalsState, event) {
    switch (event.type) {
        case CoreEvents.UI_MODAL_OPEN: {
            const p = event.payload || {};
            const kind = p.kind;
            if (typeof kind !== 'string' || kind.length === 0) return state;
            const modal = {
                id: p.id || _nextModalId(),
                kind,
                props: p.props || {},
                openedAt: event.meta.ts,
            };
            return { ...state, stack: [...state.stack, modal] };
        }
        case CoreEvents.UI_MODAL_CLOSE:
        case CoreEvents.UI_MODAL_CLOSED: {
            const id = event.payload && event.payload.id;
            if (id) {
                const next = state.stack.filter((m) => m.id !== id);
                if (next.length === state.stack.length) return state;
                return { ...state, stack: next };
            }
            if (state.stack.length === 0) return state;
            return { ...state, stack: state.stack.slice(0, -1) };
        }
        default:
            return state;
    }
}
