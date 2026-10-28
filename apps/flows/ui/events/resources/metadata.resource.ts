/**
 * Node types и Resource types metadata — каталоги для палитры
 * `flows-node-types-sidebar` (drag-into-canvas).
 *
 * REST: `apps/flows/src/api/v1/metadata.py`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const nodeTypesOp = createAsyncOp({
    name: 'flows/node_types',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/metadata/node_types_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/metadata/node-types' },
});

export const resourceTypesOp = createAsyncOp({
    name: 'flows/resource_types',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/metadata/resource_types_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/metadata/resource-types' },
});

export const exceptionAbsorbAllowNamesOp = createAsyncOp({
    name: 'flows/exception_absorb_allow_names',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/metadata/exception_absorb_allow_names_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/metadata/exception-absorb-allow-names',
    },
});

export const executionLimitsOp = createAsyncOp({
    name: 'flows/execution_limits',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/metadata/execution_limits_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/metadata/execution-limits' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/node_types': typeof nodeTypesOp;
        'flows/resource_types': typeof resourceTypesOp;
        'flows/exception_absorb_allow_names': typeof exceptionAbsorbAllowNamesOp;
        'flows/execution_limits': typeof executionLimitsOp;
    }
}
