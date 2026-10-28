/**
 * Manage-список AgentToolkit: session JWT.
 * REST GET /flows/api/v1/agent/toolkits/manage и
 * WS flows/agent_toolkits/list_requested — один op_flows_agent_toolkits_list.
 * Публичный catalog GET /agent/toolkits (device JWT) остаётся HTTP.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const agentToolkitsListOp = createAsyncOp({
    name: 'flows/agent_toolkits',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'flows/agent_toolkits/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/agent/toolkits/manage' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/agent_toolkits': typeof agentToolkitsListOp;
    }
}
