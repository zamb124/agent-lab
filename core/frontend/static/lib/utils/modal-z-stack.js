/**
 * Монотонный стек z-index для модальных слоёв.
 * Каждый вызов nextModalLayerZIndex() при открытии даёт значение выше предыдущего
 * и выше статических токенов (--z-modal, --z-notification-panel и т.д.).
 */

function readCssInt(root, prop, fallback) {
    const raw = getComputedStyle(root).getPropertyValue(prop).trim();
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : fallback;
}

function stackFloor() {
    if (typeof document === 'undefined') {
        return 30000;
    }
    const root = document.documentElement;
    return Math.max(
        readCssInt(root, '--z-notification-panel', 30000),
        readCssInt(root, '--z-max', 9999),
        readCssInt(root, '--z-tooltip', 1200),
        readCssInt(root, '--z-toast', 1100),
        readCssInt(root, '--z-modal', 1000),
    );
}

let _seq = null;

/**
 * @returns {number}
 */
export function nextModalLayerZIndex() {
    if (_seq === null) {
        _seq = stackFloor();
    }
    _seq += 1;
    return _seq;
}
