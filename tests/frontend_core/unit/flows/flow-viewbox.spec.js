import { describe, expect, it } from 'vitest';
import {
    CHIP_ROW_H,
    FLOW_NODE_H,
    FLOW_NODE_W,
    FIT_VIEW_PADDING,
    getNodeCanvasHeight,
    getToolsStripH,
    computeFitViewBox,
    wheelZoomViewBoxFactor,
    WHEEL_ZOOM_DELTA_CLAMP,
    WHEEL_ZOOM_SENSITIVITY,
    zoomViewBoxAroundPoint,
} from '../../../../apps/flows/ui/_helpers/flows-viewbox.js';
import { FLOW_TERMINAL_EXTENT } from '../../../../apps/flows/ui/_helpers/flows-terminal-markers.js';

describe('flows viewbox helpers', () => {
    it('sizes llm nodes for three visual tool chips per row', () => {
        expect(getToolsStripH(0)).toBe(0);
        expect(getToolsStripH(3)).toBe(CHIP_ROW_H);
        expect(getToolsStripH(4)).toBe(CHIP_ROW_H * 2);
        expect(getToolsStripH(9)).toBe(CHIP_ROW_H * 3);
    });

    it('grows canvas node height for visible tool rows', () => {
        const tools = Array.from({ length: 9 }, (_, i) => ({
            tool_id: `tool_${i}`,
            type: 'code',
            code: 'async def run(args, state):\n    return {}',
        }));
        expect(getNodeCanvasHeight({ type: 'llm_node', tools })).toBe(FLOW_NODE_H + CHIP_ROW_H * 3);
    });

    it('wheel zoom factor scales continuously with small trackpad deltas', () => {
        expect(wheelZoomViewBoxFactor(0)).toBe(1);
        const smallOut = wheelZoomViewBoxFactor(4, 0);
        const smallIn = wheelZoomViewBoxFactor(-4, 0);
        expect(smallOut).toBeGreaterThan(1);
        expect(smallOut).toBeLessThan(1.01);
        expect(smallIn).toBeLessThan(1);
        expect(smallIn).toBeGreaterThan(0.99);
        expect(smallOut * smallIn).toBeCloseTo(1, 10);
    });

    it('wheel zoom factor clamps extreme deltas and normalizes line mode', () => {
        const clamped = wheelZoomViewBoxFactor(10_000, 0);
        expect(clamped).toBeCloseTo(Math.exp(WHEEL_ZOOM_DELTA_CLAMP * WHEEL_ZOOM_SENSITIVITY), 10);
        const lineOut = wheelZoomViewBoxFactor(3, 1);
        expect(lineOut).toBeCloseTo(Math.exp(48 * WHEEL_ZOOM_SENSITIVITY), 10);
    });

    it('zoomViewBoxAroundPoint keeps pivot fixed in viewBox space', () => {
        const vb = { x: 0, y: 0, w: 1000, h: 500 };
        const next = zoomViewBoxAroundPoint(vb, 2, 250, 125);
        expect(next.w).toBe(2000);
        expect(next.h).toBe(1000);
        expect(next.x).toBe(-250);
        expect(next.y).toBe(-125);
        const rx = (250 - next.x) / next.w;
        const ry = (125 - next.y) / next.h;
        expect(rx).toBeCloseTo(0.25, 10);
        expect(ry).toBeCloseTo(0.25, 10);
    });

    it('computeFitViewBox expands bbox for virtual START/END extent', () => {
        const nodes = [{ pos_x: 100, pos_y: 50, type: 'llm_node', tools: [] }];
        const vb = computeFitViewBox(nodes);
        expect(vb).not.toBeNull();
        const contentMinX = 100 - FLOW_TERMINAL_EXTENT - FIT_VIEW_PADDING;
        const contentMaxX = 100 + FLOW_NODE_W + FLOW_TERMINAL_EXTENT + FIT_VIEW_PADDING;
        const contentMinY = 50 - FIT_VIEW_PADDING;
        const contentMaxY = 50 + FLOW_NODE_H + FIT_VIEW_PADDING;
        const contentW = contentMaxX - contentMinX;
        const contentH = contentMaxY - contentMinY;
        const cx = contentMinX + contentW / 2;
        const cy = contentMinY + contentH / 2;
        expect(vb.w).toBeGreaterThanOrEqual(contentW);
        expect(vb.h).toBeGreaterThanOrEqual(contentH);
        expect(vb.x + vb.w / 2).toBeCloseTo(cx, 5);
        expect(vb.y + vb.h / 2).toBeCloseTo(cy, 5);
    });
});
