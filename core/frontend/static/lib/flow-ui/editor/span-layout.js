/**
 * Ширина блока на сетке 12: span 1–12 относительно родителя ``[data-container-key]``.
 * Без Lit — считается в unit-тестах и на холсте.
 */

export const SPAN_COLUMNS = 12;
export const ALIGN_VALUES = Object.freeze(['start', 'center', 'end']);

export function clampSpan(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return SPAN_COLUMNS;
    return Math.min(SPAN_COLUMNS, Math.max(1, Math.round(n)));
}

export function blockSpan(block) {
    return clampSpan(block && block.span != null ? block.span : SPAN_COLUMNS);
}

export function blockAlign(block) {
    const value = block && typeof block.align === 'string' ? block.align : 'start';
    return ALIGN_VALUES.includes(value) ? value : 'start';
}

/** Шаг = 1/12 ширины контейнера; тянем от исходного span, не от последнего. */
export function spanFromPointer(startSpan, startX, clientX, containerWidth) {
    if (!(containerWidth > 0)) return clampSpan(startSpan);
    return clampSpan(startSpan + Math.round((clientX - startX) / (containerWidth / SPAN_COLUMNS)));
}

export function spanContainerWidth(blockEl) {
    if (!blockEl || typeof blockEl !== 'object') return 0;
    const parent = blockEl.parentElement;
    if (parent && typeof parent.hasAttribute === 'function' && parent.hasAttribute('data-container-key')) {
        return parent.getBoundingClientRect().width;
    }
    const closest = typeof blockEl.closest === 'function' ? blockEl.closest('[data-container-key]') : null;
    if (closest) return closest.getBoundingClientRect().width;
    return parent ? parent.getBoundingClientRect().width : 0;
}

export function startSpanResize({ event, startSpan, containerWidth, onSpan }) {
    const handle = event.currentTarget;
    if (!handle || typeof onSpan !== 'function') return;
    const pointerId = event.pointerId;
    const originSpan = clampSpan(startSpan);
    const startX = event.clientX;
    let last = originSpan;
    handle.setPointerCapture(pointerId);
    const apply = (clientX) => {
        const span = spanFromPointer(originSpan, startX, clientX, containerWidth);
        if (span === last) return;
        last = span;
        onSpan(span);
    };
    const stop = (next) => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', stop);
        handle.removeEventListener('pointercancel', stop);
        if (typeof handle.hasPointerCapture === 'function' && handle.hasPointerCapture(pointerId)) {
            handle.releasePointerCapture(pointerId);
        }
        if (next.type === 'pointerup') apply(next.clientX);
    };
    const move = (next) => apply(next.clientX);
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
}
