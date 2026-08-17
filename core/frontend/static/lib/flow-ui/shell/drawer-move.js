export const FLOW_UI_DRAWER_MOVE_START = 'flow-ui-drawer-move-start';

const INTERACTIVE_TAGS = new Set([
    'BUTTON',
    'A',
    'INPUT',
    'TEXTAREA',
    'SELECT',
    'SUMMARY',
]);

export function isDrawerMoveInteractiveTarget(event) {
    if (event === null || typeof event !== 'object') {
        throw new Error('flow-ui-drawer-move: event is required');
    }
    if (typeof event.composedPath !== 'function') {
        throw new Error('flow-ui-drawer-move: composedPath is required');
    }
    for (const node of event.composedPath()) {
        if (!(node instanceof Element)) {
            continue;
        }
        if (INTERACTIVE_TAGS.has(node.tagName)) {
            return true;
        }
        if (node.getAttribute('role') === 'button') {
            return true;
        }
        if (node.classList.contains('top-actions')) {
            return true;
        }
        if (node.classList.contains('chrome-icon-btn')) {
            return true;
        }
        if (node.classList.contains('resize-handle')) {
            return true;
        }
        if (node.classList.contains('launcher')) {
            return true;
        }
    }
    return false;
}

export function emitDrawerMoveStart(host, event) {
    if (!(host instanceof EventTarget)) {
        throw new Error('flow-ui-drawer-move: host EventTarget is required');
    }
    if (event === null || typeof event !== 'object') {
        throw new Error('flow-ui-drawer-move: pointer event is required');
    }
    if (event.button !== 0) {
        return false;
    }
    if (isDrawerMoveInteractiveTarget(event)) {
        return false;
    }
    if (typeof event.preventDefault === 'function') {
        event.preventDefault();
    }
    host.dispatchEvent(new CustomEvent(FLOW_UI_DRAWER_MOVE_START, {
        bubbles: true,
        composed: true,
        detail: Object.freeze({
            clientX: event.clientX,
            clientY: event.clientY,
            pointerId: event.pointerId,
        }),
    }));
    return true;
}
