import { describe, expect, it } from 'vitest';
import { CHIP_ROW_H, FLOW_NODE_H, getNodeCanvasHeight, getToolsStripH } from '../../../../apps/flows/ui/_helpers/flows-viewbox.js';

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
});
