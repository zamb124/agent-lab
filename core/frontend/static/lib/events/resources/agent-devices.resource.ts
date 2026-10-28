/**
 * Online LinnexAgent devices текущего пользователя (для Lara drawer presence).
 */

import { createAsyncOp } from '../index.js';
import { httpRequest } from '../http.js';
import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { isPlainRecord } from '../payload.js';

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
        if (event.type !== events.SUCCEEDED || !isPlainRecord(event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (result == null) {
            return state;
        }
        if (!isPlainRecord(result)) {
            throw new Error(`${event.type}: result must be an object`);
        }
        const rawItems = result.items;
        if (rawItems != null && !Array.isArray(rawItems)) {
            throw new Error(`${event.type}: items must be an array`);
        }
        const items: unknown[] = [];
        if (Array.isArray(rawItems)) {
            for (const entry of rawItems) {
                items.push(entry);
            }
        }
        const online: Array<{ device_id: string; device_name: string; last_seen_at: string | null }> = [];
        for (const item of items) {
            if (!isPlainRecord(item)) {
                throw new Error(`${event.type}: device must be an object`);
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
            const leftSeen = left.last_seen_at === null ? '' : left.last_seen_at;
            const rightSeen = right.last_seen_at === null ? '' : right.last_seen_at;
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

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'platform/agent_devices_load': typeof platformAgentDevicesLoadOp;
    }
}
