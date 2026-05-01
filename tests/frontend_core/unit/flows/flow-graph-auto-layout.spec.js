import { describe, it, expect } from 'vitest';
import {
    canvasNeedsAutoLayout,
    applyAutoLayoutToBranchData,
    H_GAP,
} from '../../../../apps/flows/ui/_helpers/flow-graph-auto-layout.js';
import { FLOW_NODE_W } from '../../../../apps/flows/ui/_helpers/flows-viewbox.js';

describe('flow-graph-auto-layout', () => {
    it('canvasNeedsAutoLayout: false при одной ноде', () => {
        expect(canvasNeedsAutoLayout({ nodes: { a: { type: 'code' } }, edges: [] })).toBe(false);
    });

    it('canvasNeedsAutoLayout: false если любая pos не ноль', () => {
        const data = {
            nodes: { a: { type: 'code' }, b: { type: 'code' } },
            edges: [],
        };
        expect(canvasNeedsAutoLayout(data)).toBe(true);
        expect(
            canvasNeedsAutoLayout({ ...data, nodes: { a: { type: 'code' }, b: { type: 'code', pos_x: 1, pos_y: 0 } } }),
        ).toBe(false);
    });

    it('цепочка A->B->C: слой растёт слева направо, entry начинает', () => {
        const inData = {
            nodes: {
                a: { type: 'code', name: 'A' },
                b: { type: 'code', name: 'B' },
                c: { type: 'code', name: 'C' },
            },
            edges: [
                { from: 'a', to: 'b' },
                { from: 'b', to: 'c' },
            ],
            entry: 'a',
        };
        const out = applyAutoLayoutToBranchData(inData);
        expect(out).not.toBe(inData);
        const colW = FLOW_NODE_W + H_GAP;
        expect(out.nodes.a.pos_x).toBe(0);
        expect(out.nodes.b.pos_x).toBe(colW);
        expect(out.nodes.c.pos_x).toBe(2 * colW);
    });

    it('fan-out: потомки в одном слое, разные y', () => {
        const inData = {
            nodes: {
                r: { type: 'code' },
                b: { type: 'code' },
                c: { type: 'code' },
            },
            edges: [
                { from: 'r', to: 'b' },
                { from: 'r', to: 'c' },
            ],
            entry: 'r',
        };
        const out = applyAutoLayoutToBranchData(inData);
        const colW = FLOW_NODE_W + H_GAP;
        expect(out.nodes.r.pos_x).toBe(0);
        expect(out.nodes.b.pos_x).toBe(colW);
        expect(out.nodes.c.pos_x).toBe(colW);
        expect(out.nodes.b.pos_y).not.toBe(out.nodes.c.pos_y);
    });

    it('ребро с пустым to не учитывается; недоступная нода вправо', () => {
        const inData = {
            nodes: {
                a: { type: 'code' },
                b: { type: 'code' },
                u: { type: 'code' },
            },
            edges: [
                { from: 'a', to: 'b' },
                { from: 'a', to: null },
            ],
            entry: 'a',
        };
        const out = applyAutoLayoutToBranchData(inData);
        const colW = FLOW_NODE_W + H_GAP;
        expect(out.nodes.a.pos_x).toBe(0);
        expect(out.nodes.b.pos_x).toBe(colW);
        expect(out.nodes.u.pos_x).toBe(2 * colW);
    });

    it('цикл: не меняет branchData (та же ссылка)', () => {
        const inData = {
            nodes: { a: { type: 'code' }, b: { type: 'code' } },
            edges: [
                { from: 'a', to: 'b' },
                { from: 'b', to: 'a' },
            ],
            entry: 'a',
        };
        const out = applyAutoLayoutToBranchData(inData);
        expect(out).toBe(inData);
    });

});
