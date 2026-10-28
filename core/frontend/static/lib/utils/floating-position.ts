/**
 * Расчёт положения плавающего слоя относительно якоря.
 *
 * Чистые функции без DOM: на вход — прямоугольники и параметры, на выход —
 * координаты. Так один и тот же алгоритм используют popover, меню, тултипы и
 * подсказки редактора, а поведение у края экрана проверяется юнит-тестами.
 *
 * Система координат — viewport (как у `getBoundingClientRect`), поэтому
 * результат подставляется в `position: fixed`.
 */

import { isPlainRecord } from '../events/payload.js';

/**
 * @typedef {'top'|'bottom'|'left'|'right'} FloatingSide
 * @typedef {'start'|'center'|'end'} FloatingAlign
 * @typedef {`${FloatingSide}`|`${FloatingSide}-${FloatingAlign}`} FloatingPlacement
 */

/**
 * @typedef {object} RectLike
 * @property {number} top
 * @property {number} left
 * @property {number} width
 * @property {number} height
 */

/**
 * @typedef {object} SizeLike
 * @property {number} width
 * @property {number} height
 */

export const DEFAULT_OFFSET = 6;
export const DEFAULT_VIEWPORT_PADDING = 8;

export type FloatingSide = 'top' | 'bottom' | 'left' | 'right';
export type FloatingAlign = 'start' | 'center' | 'end';
export type FloatingPlacement = FloatingSide | `${FloatingSide}-${Exclude<FloatingAlign, 'center'>}` | FloatingSide;
export interface RectLike { top: number; left: number; width: number; height: number }
export interface SizeLike { width: number; height: number }

function isFloatingSide(value: string): value is FloatingSide {
    return value === 'top' || value === 'bottom' || value === 'left' || value === 'right';
}

function isFloatingAlign(value: string): value is FloatingAlign {
    return value === 'start' || value === 'center' || value === 'end';
}

const OPPOSITE_SIDE: Record<FloatingSide, FloatingSide> = Object.freeze({
    top: 'bottom',
    bottom: 'top',
    left: 'right',
    right: 'left',
});

/**
 * @param {FloatingPlacement} placement
 * @returns {{ side: FloatingSide, align: FloatingAlign }}
 */
export function parsePlacement(placement: string): { side: FloatingSide; align: FloatingAlign } {
    const parts = String(placement).split('-');
    const sideRaw = parts[0];
    const alignRaw = parts[1];
    if (sideRaw === undefined || !isFloatingSide(sideRaw)) {
        throw new Error(`floating-position: неизвестная сторона "${placement}"`);
    }
    if (alignRaw !== undefined && !isFloatingAlign(alignRaw)) {
        throw new Error(`floating-position: неизвестное выравнивание "${placement}"`);
    }
    return { side: sideRaw, align: alignRaw === undefined ? 'center' : alignRaw };
}

/**
 * @param {FloatingSide} side
 * @param {FloatingAlign} align
 * @returns {FloatingPlacement}
 */
function formatPlacement(side: FloatingSide, align: FloatingAlign): FloatingPlacement {
    return align === 'center' ? side : `${side}-${align}`;
}

function rectBottom(rect: { top: number; height: number }): number {
    return rect.top + rect.height;
}

function rectRight(rect: { left: number; width: number }): number {
    return rect.left + rect.width;
}

/**
 * Координаты слоя для конкретной стороны и выравнивания, без учёта границ экрана.
 *
 * @param {RectLike} anchor
 * @param {SizeLike} floating
 * @param {FloatingSide} side
 * @param {FloatingAlign} align
 * @param {number} offset
 * @returns {{ x: number, y: number }}
 */
function rawCoords(anchor: RectLike, floating: SizeLike, side: FloatingSide, align: FloatingAlign, offset: number): { x: number; y: number } {
    if (side === 'top' || side === 'bottom') {
        const y = side === 'top'
            ? anchor.top - floating.height - offset
            : rectBottom(anchor) + offset;
        if (align === 'start') {
            return { x: anchor.left, y };
        }
        if (align === 'end') {
            return { x: rectRight(anchor) - floating.width, y };
        }
        return { x: anchor.left + (anchor.width - floating.width) / 2, y };
    }

    const x = side === 'left'
        ? anchor.left - floating.width - offset
        : rectRight(anchor) + offset;
    if (align === 'start') {
        return { x, y: anchor.top };
    }
    if (align === 'end') {
        return { x, y: rectBottom(anchor) - floating.height };
    }
    return { x, y: anchor.top + (anchor.height - floating.height) / 2 };
}

/**
 * Помещается ли слой целиком при данной стороне.
 *
 * @param {RectLike} anchor
 * @param {SizeLike} floating
 * @param {FloatingSide} side
 * @param {SizeLike} viewport
 * @param {number} offset
 * @param {number} padding
 * @returns {boolean}
 */
function sideFits(anchor: RectLike, floating: SizeLike, side: FloatingSide, viewport: SizeLike, offset: number, padding: number): boolean {
    if (side === 'top') {
        return anchor.top - offset - floating.height >= padding;
    }
    if (side === 'bottom') {
        return rectBottom(anchor) + offset + floating.height <= viewport.height - padding;
    }
    if (side === 'left') {
        return anchor.left - offset - floating.width >= padding;
    }
    return rectRight(anchor) + offset + floating.width <= viewport.width - padding;
}

/**
 * Свободное место со стороны якоря — по нему выбирается лучшая сторона,
 * когда слой не помещается ни в предпочтительную, ни в противоположную.
 *
 * @param {RectLike} anchor
 * @param {FloatingSide} side
 * @param {SizeLike} viewport
 * @returns {number}
 */
function availableSpace(anchor: RectLike, side: FloatingSide, viewport: SizeLike): number {
    if (side === 'top') return anchor.top;
    if (side === 'bottom') return viewport.height - rectBottom(anchor);
    if (side === 'left') return anchor.left;
    return viewport.width - rectRight(anchor);
}

function clamp(value: number, min: number, max: number): number {
    if (max < min) {
        return min;
    }
    return Math.min(Math.max(value, min), max);
}

/**
 * Положение плавающего слоя.
 *
 * @param {object} params
 * @param {RectLike} params.anchorRect якорь в координатах viewport
 * @param {SizeLike} params.floatingRect измеренный размер слоя
 * @param {FloatingPlacement} [params.placement] предпочтительное размещение
 * @param {number} [params.offset] зазор между якорем и слоем
 * @param {boolean} [params.flip] переносить на противоположную сторону, если не помещается
 * @param {boolean} [params.shift] сдвигать вдоль поперечной оси, чтобы не выйти за экран
 * @param {boolean} [params.matchWidth] растянуть слой по ширине якоря
 * @param {SizeLike} [params.viewport] размер области видимости
 * @param {number} [params.viewportPadding] отступ от края экрана
 * @returns {{ x: number, y: number, placement: FloatingPlacement, width: number | null, maxHeight: number }}
 */
export interface ComputeFloatingPositionOptions {
    anchorRect: RectLike | null | undefined;
    floatingRect: SizeLike | null | undefined;
    placement?: FloatingPlacement;
    offset?: number;
    flip?: boolean;
    shift?: boolean;
    matchWidth?: boolean;
    viewport?: SizeLike;
    viewportPadding?: number;
}

export function computeFloatingPosition({
    anchorRect,
    floatingRect,
    placement = 'bottom-start',
    offset = DEFAULT_OFFSET,
    flip = true,
    shift = true,
    matchWidth = false,
    viewport,
    viewportPadding = DEFAULT_VIEWPORT_PADDING,
}: ComputeFloatingPositionOptions): { x: number; y: number; placement: FloatingPlacement; width: number | null; maxHeight: number } {
    if (!anchorRect || !floatingRect) {
        throw new Error('floating-position: anchorRect и floatingRect обязательны');
    }
    const view = viewport ?? readViewportSize();
    const { side: preferredSide, align } = parsePlacement(placement);

    const width = matchWidth ? anchorRect.width : null;
    const measured = {
        width: width === null ? floatingRect.width : width,
        height: floatingRect.height,
    };

    let side = preferredSide;
    if (flip && !sideFits(anchorRect, measured, side, view, offset, viewportPadding)) {
        const opposite = OPPOSITE_SIDE[side];
        if (sideFits(anchorRect, measured, opposite, view, offset, viewportPadding)) {
            side = opposite;
        } else if (
            availableSpace(anchorRect, opposite, view) > availableSpace(anchorRect, side, view)
        ) {
            // Ни одна сторона не вмещает слой целиком — выбираем ту, где места больше,
            // а высоту ограничит maxHeight ниже.
            side = opposite;
        }
    }

    const coords = rawCoords(anchorRect, measured, side, align, offset);
    let { x, y } = coords;

    if (shift) {
        if (side === 'top' || side === 'bottom') {
            x = clamp(x, viewportPadding, view.width - measured.width - viewportPadding);
        } else {
            y = clamp(y, viewportPadding, view.height - measured.height - viewportPadding);
        }
    }

    const maxHeight = side === 'top'
        ? Math.max(0, anchorRect.top - offset - viewportPadding)
        : side === 'bottom'
            ? Math.max(0, view.height - rectBottom(anchorRect) - offset - viewportPadding)
            : Math.max(0, view.height - 2 * viewportPadding);

    return {
        x: Math.round(x),
        y: Math.round(y),
        placement: formatPlacement(side, align),
        width,
        maxHeight: Math.round(maxHeight),
    };
}

/**
 * Размер области видимости с учётом экранной клавиатуры на мобильных.
 *
 * @returns {SizeLike}
 */
export function readViewportSize(): SizeLike {
    if (typeof window === 'undefined') {
        return { width: 0, height: 0 };
    }
    const visual = window.visualViewport;
    if (visual) {
        return { width: visual.width, height: visual.height };
    }
    return { width: window.innerWidth, height: window.innerHeight };
}

/**
 * Прямоугольник якоря: элемент, готовый rect или точка (для контекстного меню).
 *
 * @param {Element | RectLike | { x: number, y: number }} anchor
 * @returns {RectLike | null}
 */
export function resolveAnchorRect(anchor: Element | RectLike | { x: number; y: number } | null | undefined): RectLike | null {
    if (!anchor) {
        return null;
    }
    if (typeof Element !== 'undefined' && anchor instanceof Element) {
        const rect = anchor.getBoundingClientRect();
        return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
    }
    const record: unknown = anchor;
    if (!isPlainRecord(record)) return null;
    const top = record.top;
    const left = record.left;
    const width = record.width;
    const height = record.height;
    if (typeof width === 'number' && typeof height === 'number') {
        if (typeof top !== 'number' || typeof left !== 'number') {
            throw new Error('floating-position: rect anchor requires numeric top and left');
        }
        return { top, left, width, height };
    }
    const x = record.x;
    const y = record.y;
    if (typeof x === 'number' && typeof y === 'number') {
        return { top: y, left: x, width: 0, height: 0 };
    }
    return null;
}
