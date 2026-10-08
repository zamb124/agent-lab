/**
 * Online LinnexAgent devices текущего пользователя (для Lara drawer presence).
 */

import { createAsyncOp } from '../index.js';
import { httpRequest } from '../http.js';
import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';

export const platformAgentDevicesLoadOp = createAsyncOp({
    name: 'platform/agent_devices_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/agent/devices' },
    extraInitial: {
        online_device_name: '',
        online_device_id: '',
    },
    request: async () => await httpRequest({
        method: 'GET',
        url: '/frontend/api/agent/devices?mine=true',
    }),
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !event.payload || !('result' in (event.payload as object))) {
            return state;
        }
        const result = (event.payload as { result?: unknown }).result as { items?: unknown } | null;
        if (!result || typeof result !== 'object') {
            return state;
        }
        const items = Array.isArray(result.items) ? result.items : [];
        const online: Array<{ device_id: string; device_name: string; last_seen_at: string | null }> = [];
        for (const item of items) {
            if (!item || typeof item !== 'object') {
                continue;
            }
            if (item.is_active !== true || item.is_tunnel_online !== true) {
                continue;
            }
            if (typeof item.device_id !== 'string' || item.device_id.length === 0) {
                continue;
            }
            if (typeof item.device_name !== 'string' || item.device_name.length === 0) {
                continue;
            }
            online.push({
                device_id: item.device_id,
                device_name: item.device_name,
                last_seen_at: typeof item.last_seen_at === 'string' ? item.last_seen_at : null,
            });
        }
        online.sort((left, right) => {
            const leftSeen = left.last_seen_at || '';
            const rightSeen = right.last_seen_at || '';
            if (leftSeen === rightSeen) {
                return 0;
            }
            return leftSeen < rightSeen ? 1 : -1;
        });
        const best = online.length > 0 ? online[0] : null;
        return {
            ...state,
            online_device_id: best ? best.device_id : '',
            online_device_name: best ? best.device_name : '',
        };
    },
});

export const platformAgentDeviceFactories = [platformAgentDevicesLoadOp];

export function createPlatformAgentDevicesAuthEffect(): (event: PlatformEvent, ctx: EffectCtx) => void {
    return (event: PlatformEvent, ctx: EffectCtx): void => {
        if (event.type === CoreEvents.AUTH_USER_LOADED) {
            platformAgentDevicesLoadOp.run({}, ctx);
        }
    };
}
