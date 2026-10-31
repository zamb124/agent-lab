import { describe, it, expect } from 'vitest';

import {
    computeFloatingPosition,
    parsePlacement,
    resolveAnchorRect,
} from '../../../../core/frontend/static/lib/utils/floating-position.js';

const VIEWPORT = { width: 1000, height: 800 };

/** Якорь в середине экрана: места хватает со всех сторон. */
const CENTER_ANCHOR = { top: 400, left: 400, width: 200, height: 40 };

const SMALL_LAYER = { width: 160, height: 120 };

describe('parsePlacement', () => {
    it('разбирает сторону с выравниванием', () => {
        expect(parsePlacement('bottom-start')).toEqual({ side: 'bottom', align: 'start' });
        expect(parsePlacement('top-end')).toEqual({ side: 'top', align: 'end' });
    });

    it('без выравнивания подставляет center', () => {
        expect(parsePlacement('right')).toEqual({ side: 'right', align: 'center' });
    });

    it('неизвестное значение — ошибка, а не молчаливый дефолт', () => {
        expect(() => parsePlacement('diagonal')).toThrow();
        expect(() => parsePlacement('bottom-middle')).toThrow();
    });
});

describe('computeFloatingPosition: базовые размещения', () => {
    it('bottom-start ставит слой под якорь по левому краю', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            offset: 6,
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('bottom-start');
        expect(result.x).toBe(400);
        expect(result.y).toBe(446);
    });

    it('bottom-end выравнивает по правому краю якоря', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-end',
            viewport: VIEWPORT,
        });

        expect(result.x).toBe(440);
    });

    it('bottom по центру якоря', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom',
            viewport: VIEWPORT,
        });

        expect(result.x).toBe(420);
    });

    it('top ставит слой над якорем', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'top-start',
            offset: 6,
            viewport: VIEWPORT,
        });

        expect(result.y).toBe(274);
    });

    it('right-start ставит слой справа', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'right-start',
            offset: 6,
            viewport: VIEWPORT,
        });

        expect(result.x).toBe(606);
        expect(result.y).toBe(400);
    });
});

describe('computeFloatingPosition: flip', () => {
    it('переносит вверх, когда снизу не помещается', () => {
        const nearBottom = { top: 740, left: 400, width: 200, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearBottom,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('top-start');
        expect(result.y).toBe(614);
    });

    it('переносит вниз, когда сверху не помещается', () => {
        const nearTop = { top: 20, left: 400, width: 200, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearTop,
            floatingRect: SMALL_LAYER,
            placement: 'top-start',
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('bottom-start');
    });

    it('не переносит, когда предпочтительная сторона помещается', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('bottom-start');
    });

    it('flip=false оставляет сторону даже при нехватке места', () => {
        const nearBottom = { top: 740, left: 400, width: 200, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearBottom,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            flip: false,
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('bottom-start');
    });

    it('когда не помещается нигде — выбирает сторону с большим запасом', () => {
        const tallLayer = { width: 160, height: 700 };
        const anchorLowerHalf = { top: 500, left: 400, width: 200, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: anchorLowerHalf,
            floatingRect: tallLayer,
            placement: 'bottom-start',
            viewport: VIEWPORT,
        });

        expect(result.placement).toBe('top-start');
    });
});

describe('computeFloatingPosition: shift', () => {
    it('прижимает слой к правому краю с отступом', () => {
        const nearRight = { top: 400, left: 900, width: 90, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearRight,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            viewport: VIEWPORT,
            viewportPadding: 8,
        });

        expect(result.x).toBe(832);
    });

    it('прижимает слой к левому краю с отступом', () => {
        const nearLeft = { top: 400, left: 4, width: 40, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearLeft,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-end',
            viewport: VIEWPORT,
            viewportPadding: 8,
        });

        expect(result.x).toBe(8);
    });

    it('для боковых размещений сдвигает по вертикали', () => {
        const nearBottom = { top: 780, left: 400, width: 100, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearBottom,
            floatingRect: SMALL_LAYER,
            placement: 'right-start',
            viewport: VIEWPORT,
            viewportPadding: 8,
        });

        expect(result.y).toBe(672);
    });

    it('shift=false не трогает координату', () => {
        const nearRight = { top: 400, left: 900, width: 90, height: 40 };

        const result = computeFloatingPosition({
            anchorRect: nearRight,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            shift: false,
            viewport: VIEWPORT,
        });

        expect(result.x).toBe(900);
    });
});

describe('computeFloatingPosition: размеры', () => {
    it('matchWidth растягивает слой по ширине якоря', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            matchWidth: true,
            viewport: VIEWPORT,
        });

        expect(result.width).toBe(200);
        expect(result.x).toBe(400);
    });

    it('без matchWidth ширина не навязывается', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            viewport: VIEWPORT,
        });

        expect(result.width).toBeNull();
    });

    it('maxHeight ограничен местом снизу', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'bottom-start',
            offset: 6,
            viewport: VIEWPORT,
            viewportPadding: 8,
        });

        expect(result.maxHeight).toBe(346);
    });

    it('maxHeight ограничен местом сверху при размещении над якорем', () => {
        const result = computeFloatingPosition({
            anchorRect: CENTER_ANCHOR,
            floatingRect: SMALL_LAYER,
            placement: 'top-start',
            offset: 6,
            viewport: VIEWPORT,
            viewportPadding: 8,
        });

        expect(result.maxHeight).toBe(386);
    });
});

describe('computeFloatingPosition: контракт', () => {
    it('без якоря или размера — ошибка', () => {
        expect(() =>
            computeFloatingPosition({ anchorRect: undefined, floatingRect: SMALL_LAYER, viewport: VIEWPORT }),
        ).toThrow();
        expect(() =>
            computeFloatingPosition({ anchorRect: CENTER_ANCHOR, floatingRect: undefined, viewport: VIEWPORT }),
        ).toThrow();
    });

    it('координаты округляются до целых пикселей', () => {
        const oddAnchor = { top: 100.4, left: 100.7, width: 51, height: 21 };

        const result = computeFloatingPosition({
            anchorRect: oddAnchor,
            floatingRect: { width: 100.3, height: 40.2 },
            placement: 'bottom',
            viewport: VIEWPORT,
        });

        expect(Number.isInteger(result.x)).toBe(true);
        expect(Number.isInteger(result.y)).toBe(true);
    });
});

describe('resolveAnchorRect', () => {
    it('принимает готовый прямоугольник', () => {
        expect(resolveAnchorRect(CENTER_ANCHOR)).toEqual(CENTER_ANCHOR);
    });

    it('точку превращает в нулевой прямоугольник для контекстного меню', () => {
        expect(resolveAnchorRect({ x: 120, y: 240 })).toEqual({
            top: 240,
            left: 120,
            width: 0,
            height: 0,
        });
    });

    it('пустое значение даёт null', () => {
        expect(resolveAnchorRect(null)).toBeNull();
        expect(resolveAnchorRect(undefined)).toBeNull();
    });
});
