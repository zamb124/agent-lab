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

const OPPOSITE_SIDE = Object.freeze({
    top: 'bottom',
    bottom: 'top',
    left: 'right',
    right: 'left',
});

/**
 * @param {FloatingPlacement} placement
 * @returns {{ side: FloatingSide, align: FloatingAlign }}
 */
export function parsePlacement(placement) {
    const [side, align] = String(placement).split('-');
    if (side !== 'top' && side !== 'bottom' && side !== 'left' && side !== 'right') {
        throw new Error(`floating-position: неизвестная сторона "${placement}"`);
    }
    if (align !== undefined && align !== 'start' && align !== 'center' && align !== 'end') {
        throw new Error(`floating-position: неизвестное выравнивание "${placement}"`);
    }
    return { side, align: align === undefined ? 'center' : align };
}

/**
 * @param {FloatingSide} side
 * @param {FloatingAlign} align
 * @returns {FloatingPlacement}
 */
function formatPlacement(side, align) {
    return align === 'center' ? side : `${side}-${align}`;
}

function rectBottom(rect) {
    return rect.top + rect.height;
}

function rectRight(rect) {
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
function rawCoords(anchor, floating, side, align, offset) {
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
function sideFits(anchor, floating, side, viewport, offset, padding) {
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
function availableSpace(anchor, side, viewport) {
    if (side === 'top') return anchor.top;
    if (side === 'bottom') return viewport.height - rectBottom(anchor);
    if (side === 'left') return anchor.left;
    return viewport.width - rectRight(anchor);
}

function clamp(value, min, max) {
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
}) {
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
export function readViewportSize() {
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
export function resolveAnchorRect(anchor) {
    if (!anchor) {
        return null;
    }
    if (typeof Element !== 'undefined' && anchor instanceof Element) {
        const rect = anchor.getBoundingClientRect();
        return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
    }
    if (typeof anchor.width === 'number' && typeof anchor.height === 'number') {
        return { top: anchor.top, left: anchor.left, width: anchor.width, height: anchor.height };
    }
    if (typeof anchor.x === 'number' && typeof anchor.y === 'number') {
        return { top: anchor.y, left: anchor.x, width: 0, height: 0 };
    }
    return null;
}
