import { describe, it, expect } from 'vitest';
import {
    hasControlPath,
    buildDataWires,
    buildLineageSet,
    aggregateDataflowIssues,
} from '../../../../apps/flows/ui/_helpers/flows-dataflow-canvas.js';

function randomId() {
    return `n${Math.floor(Math.random() * 1000)}`;
}

function randomGraph(nodeCount = 4) {
    const ids = Array.from({ length: nodeCount }, () => randomId());
    const edges = [];
    for (let i = 0; i < nodeCount - 1; i += 1) {
        edges.push({ from_node: ids[i], to_node: ids[i + 1] });
    }
    return { ids, edges };
}

describe('flows-dataflow-canvas fuzz', () => {
    it('hasControlPath matches manual BFS on random graphs', () => {
        for (let run = 0; run < 80; run += 1) {
            const { ids, edges } = randomGraph(3 + (run % 4));
            const fromId = ids[0];
            const toId = ids[ids.length - 1];
            const found = hasControlPath(fromId, toId, edges);
            const adj = new Map();
            for (const edge of edges) {
                if (!adj.has(edge.from_node)) adj.set(edge.from_node, []);
                adj.get(edge.from_node).push(edge.to_node);
            }
            const seen = new Set([fromId]);
            const queue = [fromId];
            let manual = false;
            while (queue.length > 0) {
                const cur = queue.shift();
                for (const nxt of adj.get(cur) || []) {
                    if (nxt === toId) manual = true;
                    if (!seen.has(nxt)) {
                        seen.add(nxt);
                        queue.push(nxt);
                    }
                }
            }
            expect(found).to.equal(manual);
        }
    });

    it('buildDataWires never crashes on malformed payloads', () => {
        for (let run = 0; run < 80; run += 1) {
            const dataflowNodes = {
                a: { input_mapping: run % 2 === 0 ? null : [{ source_kind: 'state', producers: ['x'] }] },
            };
            const graphNodes = run % 3 === 0 ? null : { a: {}, x: {} };
            const wires = buildDataWires(dataflowNodes, graphNodes);
            expect(Array.isArray(wires)).toBe(true);
            const keys = new Set(wires.map((w) => `${w.from}\u0000${w.to}\u0000${w.label}`));
            expect(keys.size).to.equal(wires.length);
        }
    });

    it('buildLineageSet always contains hover id', () => {
        for (let run = 0; run < 40; run += 1) {
            const hoverId = `h${run}`;
            const wires = [{ from: 'a', to: hoverId }, { from: hoverId, to: 'c' }];
            const lineage = buildLineageSet(hoverId, wires);
            expect(lineage).to.not.equal(null);
            expect(lineage.has(hoverId)).toBe(true);
        }
    });

    it('aggregateDataflowIssues handles garbage without throwing', () => {
        for (let run = 0; run < 40; run += 1) {
            const issues = aggregateDataflowIssues(
                { n1: { issues: run % 2 === 0 ? 'bad' : [{ severity: 'error', message: 'x' }] } },
                { n1: run % 3 === 0 ? null : { name: 'N' } },
            );
            expect(Array.isArray(issues)).toBe(true);
        }
    });
});
