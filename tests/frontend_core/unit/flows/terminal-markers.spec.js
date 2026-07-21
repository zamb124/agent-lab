/**
 * @vitest-environment node
 */

import { describe, expect, it } from 'vitest';
import {
    FLOW_TERMINAL_GAP,
    FLOW_TERMINAL_OUTER_R,
    FLOW_TERMINAL_INNER_R,
    FLOW_TERMINAL_EXTENT,
    terminalStartCenter,
    terminalEndCenter,
    listTerminalEndPorts,
} from '../../../../apps/flows/ui/_helpers/flows-terminal-markers.js';
import { getReflectionPolicyPreset } from '../../../../apps/flows/ui/_helpers/flows-reflection-defaults.js';

describe('flows terminal markers', () => {
    it('exposes stable geometry constants', () => {
        expect(FLOW_TERMINAL_GAP).toBe(96);
        expect(FLOW_TERMINAL_OUTER_R).toBe(20);
        expect(FLOW_TERMINAL_INNER_R).toBe(14);
        expect(FLOW_TERMINAL_EXTENT).toBe(FLOW_TERMINAL_GAP + 2 * FLOW_TERMINAL_OUTER_R);
    });

    it('places start badge left of in-port and end badge right of out-port', () => {
        const start = terminalStartCenter({ x: 100, y: 50 });
        expect(start).toEqual({
            cx: 100 - FLOW_TERMINAL_GAP - FLOW_TERMINAL_OUTER_R,
            cy: 50,
        });
        const end = terminalEndCenter({ x: 300, y: 80 });
        expect(end).toEqual({
            cx: 300 + FLOW_TERMINAL_GAP + FLOW_TERMINAL_OUTER_R,
            cy: 80,
        });
    });

    it('rejects invalid port coordinates', () => {
        expect(() => terminalStartCenter(null)).toThrow(/portXY/);
        expect(() => terminalEndCenter({ x: 1 })).toThrow(/y/);
    });

    it('lists a single null port for ordinary leaf nodes', () => {
        const node = { type: 'llm_node', pos_x: 0, pos_y: 0 };
        expect(listTerminalEndPorts('a', node, [])).toEqual([null]);
        expect(listTerminalEndPorts('a', node, [
            { from_node: 'a', to_node: 'b' },
        ])).toEqual([]);
    });

    it('lists unconnected reflection exits as terminal ports', () => {
        const quality = getReflectionPolicyPreset('quality');
        const node = {
            type: 'reflection',
            critic_policy: quality,
            pos_x: 0,
            pos_y: 0,
        };
        expect(listTerminalEndPorts('r1', node, [])).toEqual(['pass', 'revise', 'reject']);
        expect(listTerminalEndPorts('r1', node, [
            { from_node: 'r1', to_node: 'next', from_port: 'pass' },
        ])).toEqual(['revise', 'reject']);
        expect(listTerminalEndPorts('r1', node, [
            { from_node: 'r1', to_node: 'ok', from_port: 'pass' },
            { from_node: 'r1', to_node: 'fix', from_port: 'revise' },
            { from_node: 'r1', to_node: 'stop', from_port: 'reject' },
        ])).toEqual([]);
    });

    it('covers single-exit reflection with legacy edge without from_port', () => {
        const node = {
            type: 'reflection',
            critic_policy: {
                exits: [{ exit_id: 'only', label: 'Only', when: { kind: 'always' } }],
            },
            pos_x: 0,
            pos_y: 0,
        };
        expect(listTerminalEndPorts('r1', node, [
            { from_node: 'r1', to_node: 'next' },
        ])).toEqual([]);
    });

    it('ignores dangling outgoing edges when nodes map is provided', () => {
        const node = { type: 'llm_node', pos_x: 0, pos_y: 0 };
        const nodes = { a: node };
        expect(listTerminalEndPorts('a', node, [
            { from_node: 'a', to_node: 'missing' },
        ], nodes)).toEqual([null]);
        expect(listTerminalEndPorts('a', node, [
            { from_node: 'a', to_node: '' },
        ], nodes)).toEqual([null]);
    });

    it('treats valid outgoing edge as covering the leaf', () => {
        const node = { type: 'llm_node', pos_x: 0, pos_y: 0 };
        const other = { type: 'code_node', pos_x: 100, pos_y: 0 };
        const nodes = { a: node, b: other };
        expect(listTerminalEndPorts('a', node, [
            { from_node: 'a', to_node: 'b' },
        ], nodes)).toEqual([]);
    });
});
