/**
 * Providers — список включённых backend'ов и `current_provider`
 * из `rag.default_provider`.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const providersResource = createAsyncOp({
    name: 'rag/providers',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'rag/providers/list_requested',
    restMirror: { method: 'GET', path: '/rag/api/v1/providers' },
    extraInitial: { items: [], current: null },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED) return state;
        const result = (event.payload as { result?: { items?: unknown; current_provider?: unknown } } | null)?.result;
        if (!result || !Array.isArray(result.items)) {
            throw new Error('rag/providers: result.items must be array');
        }
        if (typeof result.current_provider !== 'string') {
            throw new Error('rag/providers: result.current_provider must be string');
        }
        return { ...state, items: result.items, current: result.current_provider };
    },
});
