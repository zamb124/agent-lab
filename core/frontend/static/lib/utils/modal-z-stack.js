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
 * Z-index слоя портала тултипов CodeMirror на `document.body`. Должен быть выше любого
 * `glass-modal` (`nextModalLayerZIndex` растёт от stackFloor). Значение из `--z-editor-body-portal`
 * в tokens.css; при отсутствии вычисленного числа — stackFloor + 10000.
 *
 * @returns {number}
 */
export function editorBodyPortalZIndex() {
    if (typeof document === 'undefined') {
        return stackFloor() + 10000;
    }
    const doc = document.documentElement;
    const probe = document.createElement('div');
    probe.style.cssText =
        'position:absolute;visibility:hidden;pointer-events:none;width:0;height:0;z-index:var(--z-editor-body-portal)';
    doc.appendChild(probe);
    const computed = getComputedStyle(probe).zIndex;
    probe.remove();
    const n = parseInt(computed, 10);
    if (Number.isFinite(n)) {
        return n;
    }
    return stackFloor() + 10000;
}

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
