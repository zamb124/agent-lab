/**
 * Слайс modals.
 *
 * Поля state.modals:
 *   stack: Array<{ id, kind, props, openedAt, closing?, closingAt? }>
 *
 * UI_MODAL_OPEN.payload.replaceKinds?: string[] — мгновенно убрать эти kind из stack
 * (без closing/exit-motion) и добавить новую модалку. Для skip enter — props.skipEnterMotion.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';
import { recordField, payloadFields } from '../payload.js';

export interface ModalStackItem {
    id: string;
    kind: string;
    props: Record<string, unknown>;
    openedAt: number;
    closing?: boolean;
    closingAt?: number;
}

export interface ModalsState {
    stack: ModalStackItem[];
}

export const initialModalsState: ModalsState = Object.freeze({
    stack: [],
});

let _modalSeq = 0;
function _nextModalId() {
    _modalSeq += 1;
    return `modal_${_modalSeq.toString(36)}`;
}

function _withClosing(item: ModalStackItem, ts: number): ModalStackItem {
    if (item.closing === true) return item;
    return { ...item, closing: true, closingAt: ts };
}

function _markClosingById(state: ModalsState, id: string, ts: number): ModalsState {
    let changed = false;
    const stack = state.stack.map((item) => {
        if (item.id !== id) return item;
        const next = _withClosing(item, ts);
        if (next !== item) changed = true;
        return next;
    });
    return changed ? { ...state, stack } : state;
}

function _markClosingByKind(state: ModalsState, kind: string, ts: number): ModalsState {
    let changed = false;
    const stack = state.stack.slice();
    for (let i = stack.length - 1; i >= 0; i -= 1) {
        const item = stack[i];
        if (item === undefined) {
            throw new Error('modal stack item missing');
        }
        if (item.kind !== kind || item.closing === true) continue;
        stack[i] = _withClosing(item, ts);
        changed = true;
        break;
    }
    return changed ? { ...state, stack } : state;
}

function _markTopClosing(state: ModalsState, ts: number): ModalsState {
    const stack = state.stack.slice();
    for (let i = stack.length - 1; i >= 0; i -= 1) {
        const item = stack[i];
        if (item === undefined) {
            throw new Error('modal stack item missing');
        }
        if (item.closing === true) continue;
        stack[i] = _withClosing(item, ts);
        return { ...state, stack };
    }
    return state;
}

function _removeById(state: ModalsState, id: string): ModalsState {
    const next = state.stack.filter((m) => m.id !== id);
    if (next.length === state.stack.length) return state;
    return { ...state, stack: next };
}

function _removeByKind(state: ModalsState, kind: string): ModalsState {
    let removed = false;
    const next: ModalStackItem[] = [];
    for (let i = state.stack.length - 1; i >= 0; i -= 1) {
        const item = state.stack[i];
        if (item === undefined) {
            throw new Error('modal stack item missing');
        }
        if (!removed && item.kind === kind) {
            removed = true;
            continue;
        }
        next.unshift(item);
    }
    return removed ? { ...state, stack: next } : state;
}

interface ModalOpenPayload {
    id?: string; kind?: unknown; props?: Record<string, unknown>;
    replaceKinds?: unknown;
}

export function modalsReducer(state: ModalsState = initialModalsState, event: PlatformEvent): ModalsState {
    switch (event.type) {
        case CoreEvents.UI_MODAL_OPEN: {
            const p = payloadFields(event);
            const kind = p.kind;
            if (typeof kind !== 'string' || kind.length === 0) return state;
            const modal: ModalStackItem = {
                id: typeof p.id === 'string' && p.id ? p.id : _nextModalId(),
                kind,
                props: recordField(p.props, 'UI_MODAL_OPEN.props'),
                openedAt: event.meta.ts,
            };
            // replaceKinds — мгновенная замена без exit/enter motion (mail↔calendar).
            const replaceKinds = Array.isArray(p.replaceKinds) ? p.replaceKinds : null;
            if (replaceKinds !== null) {
                for (const replaceKind of replaceKinds) {
                    if (typeof replaceKind !== 'string' || replaceKind.length === 0) {
                        throw new Error('UI_MODAL_OPEN.replaceKinds: each kind must be a non-empty string');
                    }
                }
                const kept = state.stack.filter((item) => !replaceKinds.includes(item.kind));
                return { ...state, stack: [...kept, modal] };
            }
            return { ...state, stack: [...state.stack, modal] };
        }
        case CoreEvents.UI_MODAL_CLOSE: {
            const p = payloadFields(event);
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
        case CoreEvents.UI_MODAL_CLOSED: {
            const p = payloadFields(event);
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
