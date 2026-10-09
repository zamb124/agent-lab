/**
 * Ширина блока на сетке 12: span 1–12 относительно родителя ``[data-container-key]``.
 * Без Lit — считается в unit-тестах и на холсте.
 */

export const SPAN_COLUMNS = 12;
export const ALIGN_VALUES = Object.freeze(['start', 'center', 'end']);

export function clampSpan(value: unknown): number {
    const n = Number(value);
    if (!Number.isFinite(n)) return SPAN_COLUMNS;
    return Math.min(SPAN_COLUMNS, Math.max(1, Math.round(n)));
}

export function blockSpan(block: { span?: unknown } | null | undefined): number {
    return clampSpan(block && block.span != null ? block.span : SPAN_COLUMNS);
}

export function blockAlign(block: { align?: unknown } | null | undefined): string {
    const value = block && typeof block.align === 'string' ? block.align : 'start';
    return ALIGN_VALUES.includes(value) ? value : 'start';
}

/** Шаг = 1/12 ширины контейнера; тянем от исходного span, не от последнего. */
export function spanFromPointer(startSpan: unknown, startX: number, clientX: number, containerWidth: number): number {
    const base = typeof startSpan === 'number' ? startSpan : SPAN_COLUMNS;
    if (!(containerWidth > 0)) return clampSpan(startSpan);
    return clampSpan(base + Math.round((clientX - startX) / (containerWidth / SPAN_COLUMNS)));
}

export function spanContainerWidth(blockEl: { parentElement?: Element | null; closest?: (selector: string) => Element | null } | null | undefined): number {
    if (!blockEl || typeof blockEl !== 'object') return 0;
    const parent = blockEl.parentElement ?? null;
    if (parent && typeof parent.hasAttribute === 'function' && parent.hasAttribute('data-container-key')) {
        return parent.getBoundingClientRect().width;
    }
    const closest = typeof blockEl.closest === 'function' ? blockEl.closest('[data-container-key]') : null;
    if (closest) return closest.getBoundingClientRect().width;
    return parent ? parent.getBoundingClientRect().width : 0;
}

export function startSpanResize({ event, startSpan, containerWidth, onSpan }: {
    event: PointerEvent;
    startSpan: number;
    containerWidth: number;
    onSpan: (span: number) => void;
}): void {
    const handle = event.currentTarget as HTMLElement | null;
    if (!handle || typeof onSpan !== 'function') return;
    const pointerId = event.pointerId;
    const originSpan = clampSpan(startSpan);
    const startX = event.clientX;
    let last = originSpan;
    handle.setPointerCapture(pointerId);
    const apply = (clientX: number) => {
        const span = spanFromPointer(originSpan, startX, clientX, containerWidth);
        if (span === last) return;
        last = span;
        onSpan(span);
    };
    const stop = (next: PointerEvent) => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', stop);
        handle.removeEventListener('pointercancel', stop);
        if (typeof handle.hasPointerCapture === 'function' && handle.hasPointerCapture(pointerId)) {
            handle.releasePointerCapture(pointerId);
        }
        if (next.type === 'pointerup') apply(next.clientX);
    };
    const move = (next: PointerEvent) => apply(next.clientX);
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
}
