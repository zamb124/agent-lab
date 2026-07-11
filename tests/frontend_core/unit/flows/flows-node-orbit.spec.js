import { describe, expect, it } from 'vitest';
import {
    buildNodeOrbitPath,
    nodeOrbitPerimeter,
} from '../../../../apps/flows/ui/_helpers/flows-node-orbit.js';
import { FLOW_NODE_H, getNodeCanvasHeight } from '../../../../apps/flows/ui/_helpers/flows-viewbox.js';

describe('flows-node-orbit', () => {
    it('builds closed clockwise rounded-rect path with four corner arcs', () => {
        const path = buildNodeOrbitPath(200, 72, 12);
        expect(path.startsWith('M ')).toBe(true);
        expect(path.endsWith(' Z')).toBe(true);
        const arcCount = (path.match(/ A /g) || []).length;
        expect(arcCount).toBe(4);
    });

    it('expands orbit outward when inset is negative', () => {
        const inner = buildNodeOrbitPath(200, 72, 12, 0);
        const outer = buildNodeOrbitPath(200, 72, 12, -3);
        expect(outer).not.toEqual(inner);
        expect(nodeOrbitPerimeter(200, 72, 12, -3)).toBeGreaterThan(nodeOrbitPerimeter(200, 72, 12, 0));
    });

    it('grows perimeter with taller node canvas height', () => {
        const baseH = FLOW_NODE_H;
        const tools = Array.from({ length: 4 }, (_, i) => ({
            tool_id: `tool_${i}`,
            type: 'code',
            code: 'async def run(args, state):\n    return {}',
        }));
        const tallH = getNodeCanvasHeight({ type: 'llm_node', tools });
        expect(tallH).toBeGreaterThan(baseH);
        expect(nodeOrbitPerimeter(200, tallH, 12)).toBeGreaterThan(nodeOrbitPerimeter(200, baseH, 12));
    });
});
