/**
 * Фикстуры для browser/unit тестов dataflow UI.
 */

import { registerFactory, collectFactories, getPlatformBus } from '@platform/lib/events/index.js';
import { bootstrapTestBus } from '../browser/helpers/reset.js';
import {
    editorBulkDeleteOp,
    editorResource,
    stickyNoteUpsertOp,
} from '../../../apps/flows/ui/events/resources/editor.resource.js';
import { flowsDataTableCreateOp } from '../../../apps/flows/ui/events/resources/data-tables.resource.js';

/**
 * Фабрики constructor `useOp` у `<flows-flow-canvas>`.
 * Isolated fixture без полного списка падает на getFactory.
 */
export const FLOW_CANVAS_FACTORIES = [
    editorResource,
    editorBulkDeleteOp,
    stickyNoteUpsertOp,
    flowsDataTableCreateOp,
];

export const SAMPLE_DATAFLOW_NODES = {
    code_1: {
        incoming_state: [],
        input_mapping: [],
        writes: [{ path: 'topic', type: 'string', source: 'code' }],
        issues: [],
        canvas: {
            inputs: [],
            outputs: [{ label: 'topic', type: 'string', status: 'ok' }],
            has_issues: false,
            error_count: 0,
            warning_count: 0,
        },
        required_inputs: [],
    },
    llm_1: {
        incoming_state: [{ path: 'topic', type: 'string', source: 'previous' }],
        input_mapping: [
            {
                target: 'topic',
                source: '@state:topic',
                source_kind: 'state',
                source_path: 'topic',
                status: 'ok',
                producers: ['code_1'],
            },
        ],
        writes: [{ path: 'response', type: 'string', source: 'llm' }],
        issues: [],
        canvas: {
            inputs: [{ label: 'topic', type: 'string', status: 'ok', required: true, producer_node: 'code_1' }],
            outputs: [{ label: 'response', type: 'string', status: 'ok' }],
            has_issues: false,
            error_count: 0,
            warning_count: 0,
        },
        required_inputs: [{ name: 'topic', origin: 'prompt', type: 'any', satisfied: true, source: '@state:topic' }],
    },
    broken_1: {
        incoming_state: [],
        input_mapping: [],
        writes: [],
        issues: [
            { code: 'unknown_prompt_variable', severity: 'warning', message: 'Prompt uses {topic}', target: 'topic' },
            { code: 'missing_required_input', severity: 'error', message: 'Required input missing', target: 'limit' },
        ],
        canvas: {
            inputs: [{ label: 'topic', type: 'any', status: 'missing', required: true, producer_node: null }],
            outputs: [],
            has_issues: true,
            error_count: 1,
            warning_count: 1,
        },
        required_inputs: [
            { name: 'topic', origin: 'prompt', type: 'any', satisfied: false, source: null },
            { name: 'limit', origin: 'parameters_schema', type: 'integer', satisfied: false, source: null },
        ],
    },
};

export const SAMPLE_BRANCH_NODES = {
    code_1: { type: 'code', name: 'Code', language: 'python', code: 'async def run(a,s): return {}' },
    llm_1: { type: 'llm_node', name: 'LLM', prompt: '{topic}' },
    broken_1: { type: 'llm_node', name: 'Broken', prompt: '{topic}' },
};

export const SAMPLE_BRANCH_EDGES = [
    { from_node: 'code_1', to_node: 'llm_1' },
];

/**
 * @param {{ slices?: unknown[], effects?: unknown[] }} [options]
 */
export function bootstrapFlowsEditor(options = {}) {
    registerFactory(editorResource);
    const collected = collectFactories([editorResource]);
    bootstrapTestBus({
        slices: options.slices || collected.slices,
        effects: options.effects || [],
    });
    const bus = getPlatformBus();
    return {
        bus,
        getState: () => bus.getState(),
    };
}

/**
 * @param {import('@platform/lib/events/bus.js').EventBus} bus
 * @param {Record<string, unknown>} [overrides]
 */
export function seedEditorDataflow(bus, overrides = {}) {
    bus.dispatch('flows/editor/flow_loaded', {
        branchId: 'default',
        flow: {
            flow_id: 'flow_test',
            name: 'Test Flow',
            entry: 'code_1',
            nodes: SAMPLE_BRANCH_NODES,
            edges: SAMPLE_BRANCH_EDGES,
        },
    });
    bus.dispatch('flows/editor/dataflow_set', {
        dataflow: { nodes: { ...SAMPLE_DATAFLOW_NODES, ...overrides } },
    });
}

/**
 * @param {{ fromNode?: string, path?: string, type?: string }} [payload]
 * @returns {DragEvent}
 */
export function createVariableDragEvent(payload = {}) {
    const data = JSON.stringify({
        fromNode: payload.fromNode || 'code_1',
        path: payload.path || 'topic',
        type: payload.type || 'string',
    });
    return new DragEvent('drop', {
        dataTransfer: new DataTransfer(),
    });
}

/**
 * @param {DragEvent} event
 * @param {{ fromNode?: string, path?: string, type?: string }} [payload]
 */
export function setVariableDragData(event, payload = {}) {
    event.dataTransfer.setData(
        'application/x-flow-variable',
        JSON.stringify({
            fromNode: payload.fromNode || 'code_1',
            path: payload.path || 'topic',
            type: payload.type || 'string',
        }),
    );
}
