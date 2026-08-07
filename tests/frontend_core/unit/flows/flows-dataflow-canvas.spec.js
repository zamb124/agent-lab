import { describe, it, expect } from 'vitest';
import {
    hasControlPath,
    buildDataWires,
    buildLineageSet,
    buildLineageSetFromWireKeys,
    chipRefKey,
    chipRefKeysForWireKeys,
    chipRefsForWire,
    countNodeDataflowProblems,
    aggregateDataflowIssues,
    dataWireKey,
    dataWireChipKind,
    dataflowChipAnchor,
    dataflowChipCenterY,
    dataflowChipKind,
    dataflowNodeChipLayout,
    dataflowPathChipKind,
    resolveChipStatePaths,
    resolveDataWireEndpoints,
    dataWirePathFor,
    dataflowInputChipAnchorX,
    dataflowOutputChipAnchorX,
    wiresForChipHover,
    DATAFLOW_CHIP_INSET,
    DATAFLOW_CHIP_ZONE_W,
} from '../../../../apps/flows/ui/_helpers/flows-dataflow-canvas.js';

describe('flows-dataflow-canvas helpers', () => {
    it('hasControlPath finds direct and transitive paths', () => {
        const edges = [
            { from_node: 'a', to_node: 'b' },
            { from_node: 'b', to_node: 'c' },
        ];
        expect(hasControlPath('a', 'c', edges)).toBe(true);
        expect(hasControlPath('a', 'b', edges)).toBe(true);
        expect(hasControlPath('c', 'a', edges)).toBe(false);
        expect(hasControlPath('a', 'a', edges)).toBe(true);
    });

    it('buildDataWires deduplicates producer-consumer links', () => {
        const dataflowNodes = {
            llm_1: {
                input_mapping: [
                    {
                        target: 'topic',
                        source_kind: 'state',
                        source_path: 'topic',
                        producers: ['code_1', 'code_1'],
                    },
                ],
                canvas: {
                    inputs: [{ label: 'topic', target: 'topic' }],
                },
            },
            code_1: {
                canvas: {
                    outputs: [{ label: 'topic', type: 'string' }],
                },
            },
        };
        const graphNodes = { code_1: { pos_x: 0, pos_y: 0 }, llm_1: { pos_x: 320, pos_y: 0 } };
        const wires = buildDataWires(dataflowNodes, graphNodes);
        expect(wires).to.deep.equal([{
            from: 'code_1',
            to: 'llm_1',
            label: 'topic',
            sourceLabel: 'topic',
            targetParam: 'topic',
        }]);
    });

    it('buildDataWires includes reads with producers from incoming_state', () => {
        const dataflowNodes = {
            mcp_1: {
                reads: [{
                    source_kind: 'state',
                    source_path: 'search_effective_query',
                    config_path: 'arguments.search_effective_query',
                }],
                incoming_state: [{
                    path: 'search_effective_query',
                    producers: ['code_1'],
                }],
                canvas: {
                    inputs: [{
                        label: 'search_effective_query',
                        target: 'arguments.search_effective_query',
                    }],
                },
            },
            code_1: {
                canvas: { outputs: [{ label: 'search_effective_query', type: 'string' }] },
            },
        };
        const graphNodes = { code_1: { pos_x: 0, pos_y: 0 }, mcp_1: { pos_x: 400, pos_y: 0 } };
        const wires = buildDataWires(dataflowNodes, graphNodes);
        expect(wires).to.deep.equal([{
            from: 'code_1',
            to: 'mcp_1',
            label: 'search_effective_query',
            sourceLabel: 'search_effective_query',
            targetParam: 'arguments.search_effective_query',
        }]);
    });

    it('resolveDataWireEndpoints connects output chip right edge to input chip left edge', () => {
        const wire = {
            from: 'code_1',
            to: 'llm_1',
            label: 'topic',
            sourceLabel: 'topic',
            targetParam: 'topic',
        };
        const fromNode = { pos_x: 0, pos_y: 0 };
        const toNode = { pos_x: 320, pos_y: 0 };
        const dataflowNodes = {
            code_1: { canvas: { outputs: [{ label: 'topic', type: 'string' }], inputs: [] } },
            llm_1: { canvas: { inputs: [{ label: 'topic', target: 'topic' }], outputs: [] } },
        };
        const endpoints = resolveDataWireEndpoints(
            wire,
            fromNode,
            toNode,
            dataflowNodes,
            200,
            () => 120,
        );
        expect(endpoints).to.not.equal(null);
        const { start, end } = endpoints;
        expect(start.x).to.equal(dataflowOutputChipAnchorX(0, 200));
        expect(end.x).to.equal(dataflowInputChipAnchorX(320));
        expect(end.x).to.be.lessThan(320);
        expect(start.y).to.equal(end.y);
    });

    it('dataflowChipAnchor places input left and output right of node body', () => {
        const out = dataflowChipAnchor(0, 0, 120, 200, 'out', 0, [], [{ label: 'topic', type: 'string' }]);
        const inn = dataflowChipAnchor(320, 0, 120, 200, 'in', 0, [{ label: 'topic', target: 'topic' }], []);
        expect(out.x).to.equal(dataflowOutputChipAnchorX(0, 200));
        expect(inn.x).to.equal(dataflowInputChipAnchorX(320));
        expect(inn.x).to.equal(320 - DATAFLOW_CHIP_ZONE_W + (136 - 132));
    });

    it('resolveDataWireEndpoints matches input chip by producer and aligns Y on crowded MCP node', () => {
        const wire = {
            from: 'prepare',
            to: 'mcp_1',
            label: 'search_effective_query',
            sourceLabel: 'search_effective_query',
            targetParam: 'search_effective_query',
        };
        const outputs = [
            { label: 'search_file_count', type: 'number' },
            { label: 'search_effective_query', type: 'string' },
            { label: 'search_user_query', type: 'string' },
        ];
        const inputs = [
            { label: 'search_mode', target: 'search_mode' },
            { label: 'search_results', target: 'search_results' },
            { label: 'search_effective_query', target: 'search_effective_query', producer_node: 'prepare' },
            { label: 'search_region', target: 'search_region' },
        ];
        const dataflowNodes = {
            prepare: { canvas: { outputs, inputs: [] } },
            mcp_1: { canvas: { inputs, outputs: [] } },
        };
        const toLayout = dataflowNodeChipLayout(120, inputs, []);
        const fromLayout = dataflowNodeChipLayout(120, [], outputs);
        const expectedInY = dataflowChipCenterY(toLayout.stackY, toLayout.inputHeights, 2);
        const expectedOutY = dataflowChipCenterY(fromLayout.stackY, fromLayout.outputHeights, 1);

        const endpoints = resolveDataWireEndpoints(
            wire,
            { pos_x: 0, pos_y: 40 },
            { pos_x: 420, pos_y: 180 },
            dataflowNodes,
            200,
            () => 120,
        );
        expect(endpoints).to.not.equal(null);
        const { start, end } = endpoints;
        expect(start.x).to.equal(dataflowOutputChipAnchorX(0, 200));
        expect(end.x).to.equal(dataflowInputChipAnchorX(420));
        expect(start.y).to.equal(40 + expectedOutY);
        expect(end.y).to.equal(180 + expectedInY);
    });

    it('resolveDataWireEndpoints matches read chip by config_path target', () => {
        const wire = {
            from: 'code_1',
            to: 'mcp_1',
            label: 'search_effective_query',
            sourceLabel: 'search_effective_query',
            targetParam: 'arguments.search_effective_query',
        };
        const inputs = [{
            label: 'search_effective_query',
            target: 'arguments.search_effective_query',
        }];
        const endpoints = resolveDataWireEndpoints(
            wire,
            { pos_x: 0, pos_y: 0 },
            { pos_x: 400, pos_y: 0 },
            {
                code_1: { canvas: { outputs: [{ label: 'search_effective_query', type: 'string' }] } },
                mcp_1: { canvas: { inputs } },
            },
            200,
            () => 120,
        );
        expect(endpoints).to.not.equal(null);
        expect(endpoints.end.x).to.equal(dataflowInputChipAnchorX(400));
    });

    it('dataWirePathFor supports chip-to-chip when input left edge is left of output right edge', () => {
        const path = dataWirePathFor(340, 100, 260, 200);
        expect(path.startsWith('M 340 100 C')).toBe(true);
        expect(path.endsWith('260 200')).toBe(true);
    });

    it('shared stack layout aligns wires when input and output counts differ', () => {
        const inputs = [
            { label: 'a', target: 'a', producer_node: 'src' },
            { label: 'b', target: 'b', producer_node: 'src' },
            { label: 'c', target: 'c', producer_node: 'src' },
        ];
        const outputs = [{ label: 'topic', type: 'string' }];
        const fromLayout = dataflowNodeChipLayout(220, [], outputs);
        const toLayout = dataflowNodeChipLayout(220, inputs, []);
        const outCenter = dataflowChipCenterY(fromLayout.stackY, fromLayout.outputHeights, 0);
        const inLastCenter = dataflowChipCenterY(toLayout.stackY, toLayout.inputHeights, 2);

        const wire = {
            from: 'code_1',
            to: 'llm_1',
            label: 'topic',
            sourceLabel: 'topic',
            targetParam: 'c',
        };
        const dataflowNodes = {
            code_1: { canvas: { outputs, inputs: [] } },
            llm_1: { canvas: { inputs, outputs: [] } },
        };
        const endpoints = resolveDataWireEndpoints(
            wire,
            { pos_x: 0, pos_y: 0 },
            { pos_x: 400, pos_y: 0 },
            dataflowNodes,
            200,
            () => 220,
        );
        expect(endpoints).to.not.equal(null);
        const { start, end } = endpoints;
        expect(start.y).to.equal(outCenter);
        expect(end.y).to.equal(inLastCenter);
        expect(outCenter).to.be.lessThan(inLastCenter);
    });

    it('buildLineageSet includes hover node and wire endpoints', () => {
        const lineage = buildLineageSet('b', [
            { from: 'a', to: 'b' },
            { from: 'b', to: 'c' },
        ]);
        expect(lineage).to.not.equal(null);
        expect(lineage.has('a')).toBe(true);
        expect(lineage.has('b')).toBe(true);
        expect(lineage.has('c')).toBe(true);
    });

    it('countNodeDataflowProblems sums canvas counters', () => {
        expect(countNodeDataflowProblems({ error_count: 2, warning_count: 1 })).to.deep.equal({
            errors: 2,
            warnings: 1,
            total: 3,
        });
    });

    it('aggregateDataflowIssues sorts errors before warnings', () => {
        const issues = aggregateDataflowIssues(
            {
                n1: {
                    issues: [
                        { code: 'w', severity: 'warning', message: 'warn' },
                        { code: 'e', severity: 'error', message: 'err' },
                    ],
                },
            },
            { n1: { name: 'Node 1' } },
        );
        expect(issues).to.have.length(2);
        expect(issues[0].severity).to.equal('error');
        expect(issues[1].severity).to.equal('warning');
    });

    it('dataWireKey matches buildDataWires dedupe key', () => {
        const wire = {
            from: 'code_1',
            to: 'llm_1',
            label: 'topic',
            sourceLabel: 'topic',
            targetParam: 'topic',
        };
        expect(dataWireKey(wire)).to.equal('code_1\u0000llm_1\u0000topic\u0000topic');
    });

    it('wiresForChipHover highlights all wires for the same state path (fan-out)', () => {
        const dataflowNodes = {
            code_1: {
                canvas: {
                    outputs: [
                        { label: 'topic', type: 'string' },
                        { label: 'meta', type: 'object' },
                    ],
                    inputs: [],
                },
            },
            llm_1: {
                input_mapping: [
                    {
                        target: 'topic',
                        source_kind: 'state',
                        source_path: 'topic',
                        producers: ['code_1'],
                    },
                ],
                canvas: {
                    inputs: [{ label: 'topic', target: 'topic', producer_node: 'code_1' }],
                    outputs: [],
                },
            },
            mcp_1: {
                input_mapping: [
                    {
                        target: 'topic',
                        source_kind: 'state',
                        source_path: 'topic',
                        producers: ['code_1'],
                    },
                ],
                canvas: {
                    inputs: [{ label: 'topic', target: 'topic', producer_node: 'code_1' }],
                    outputs: [],
                },
            },
        };
        const graphNodes = { code_1: {}, llm_1: {}, mcp_1: {} };
        const wires = buildDataWires(dataflowNodes, graphNodes);
        expect(wires).to.have.length(2);

        const topicOutKeys = wiresForChipHover(wires, { nodeId: 'code_1', side: 'out', index: 0 }, dataflowNodes);
        expect(topicOutKeys.size).to.equal(2);
        expect(topicOutKeys.has(dataWireKey(wires[0]))).toBe(true);
        expect(topicOutKeys.has(dataWireKey(wires[1]))).toBe(true);

        const topicInKeys = wiresForChipHover(wires, { nodeId: 'mcp_1', side: 'in', index: 0 }, dataflowNodes);
        expect(topicInKeys).toEqual(topicOutKeys);

        const metaOutKeys = wiresForChipHover(wires, { nodeId: 'code_1', side: 'out', index: 1 }, dataflowNodes);
        expect(metaOutKeys.size).to.equal(0);

        expect(resolveChipStatePaths({ nodeId: 'llm_1', side: 'in', index: 0 }, dataflowNodes, wires)).toEqual(
            new Set(['topic']),
        );
    });

    it('wiresForChipHover returns empty set for chip without state path', () => {
        const dataflowNodes = {
            code_1: {
                canvas: {
                    outputs: [{ label: 'topic', type: 'string' }],
                    inputs: [],
                },
            },
            llm_1: {
                input_mapping: [{
                    target: 'topic',
                    source_kind: 'state',
                    source_path: 'topic',
                    producers: ['code_1'],
                }],
                canvas: {
                    inputs: [{ label: 'topic', target: 'topic', producer_node: 'code_1' }],
                    outputs: [],
                },
            },
        };
        const graphNodes = { code_1: {}, llm_1: {} };
        const wires = buildDataWires(dataflowNodes, graphNodes);
        const noWireKeys = wiresForChipHover(wires, { nodeId: 'code_1', side: 'out', index: 99 }, dataflowNodes);
        expect(noWireKeys.size).to.equal(0);
    });

    it('chipRefsForWire returns endpoint chip indices', () => {
        const wire = {
            from: 'code_1',
            to: 'llm_1',
            label: 'topic',
            sourceLabel: 'topic',
            targetParam: 'topic',
        };
        const dataflowNodes = {
            code_1: { canvas: { outputs: [{ label: 'topic', type: 'string' }], inputs: [] } },
            llm_1: { canvas: { inputs: [{ label: 'topic', target: 'topic', producer_node: 'code_1' }], outputs: [] } },
        };
        const refs = chipRefsForWire(wire, dataflowNodes);
        expect(refs).to.deep.equal([
            { nodeId: 'code_1', side: 'out', index: 0 },
            { nodeId: 'llm_1', side: 'in', index: 0 },
        ]);
        expect(chipRefKeysForWireKeys(new Set([dataWireKey(wire)]), [wire], dataflowNodes)).toEqual(
            new Set([chipRefKey(refs[0]), chipRefKey(refs[1])]),
        );
        expect(buildLineageSetFromWireKeys(new Set([dataWireKey(wire)]), [wire])?.has('llm_1')).toBe(true);
    });

    it('dataflowChipKind prefers explicit kind and falls back to path prefix', () => {
        expect(dataflowChipKind({ label: 'ui_values.email', kind: 'ui_value' })).toBe('ui_value');
        expect(dataflowChipKind({ label: 'ui_values.email' })).toBe('ui_value');
        expect(dataflowChipKind({ label: 'variables.x' })).toBe('variable');
        expect(dataflowChipKind({ label: 'triggers.tg.payload' })).toBe('trigger');
        expect(dataflowChipKind({ label: 'content' })).toBe('content');
        expect(dataWireChipKind({ sourceLabel: 'ui_values.email', label: 'email' })).toBe('ui_value');
        expect(dataflowPathChipKind('files')).toBe('files');
    });
});
