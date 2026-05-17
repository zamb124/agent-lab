/**
 * Dataflow inspector — static state contract shown in the visual editor.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const dataflowInspectOp = createAsyncOp({
    name: 'flows/dataflow_inspect',
    silent: true,
    transport: 'http',
    restMirror: { method: 'POST', path: '/flows/api/v1/flows/dataflow/inspect' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('dataflowInspectOp: payload required');
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/flows/dataflow/inspect',
            body: payload,
        });
    },
});
