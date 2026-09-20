/**
 * Dataflow inspector — статический контракт состояния, показываемый в визуальном редакторе.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const dataflowInspectOp = createAsyncOp({
    name: 'flows/dataflow_inspect',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/flows/dataflow_inspect_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/dataflow/inspect' },
});
