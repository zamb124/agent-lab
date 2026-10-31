/**
 * Список flows для кросс-сервисного выбора (embed).
 * REST GET /flows/api/v1/flows/ и WS flows/flows/list_requested — один op_flows_list.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { OffsetPage_FlowResponse_ } from '../wire/flows.gen.js';

export const flowsListOp = createAsyncOp<OffsetPage_FlowResponse_>({
    name: 'flows/flows_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/flows/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/flows/' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/flows_list': typeof flowsListOp;
    }
}
