/**
 * platform/agent_devices_load — online LinnexAgent для Lara presence.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import {
    createPlatformAgentDevicesAuthEffect,
    platformAgentDeviceFactories,
    platformAgentDevicesLoadOp,
} from '@platform/lib/events/resources/agent-devices.resource.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    fetchMock.uninstall();
    resetFactories();
});

const emptyState = {
    busy: false,
    error: null,
    lastResult: null,
    lastRequestId: null,
    online_device_name: '',
    online_device_id: '',
};

describe('platformAgentDevicesLoadOp', () => {
    it('restMirror и factory registry', () => {
        expect(platformAgentDevicesLoadOp.name).toBe('platform/agent_devices_load');
        expect(platformAgentDevicesLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/agent/devices',
        });
        expect(platformAgentDeviceFactories).toContain(platformAgentDevicesLoadOp);
    });

    it('extraReducer выбирает самый свежий online device', () => {
        const next = platformAgentDevicesLoadOp.reducer(emptyState, {
            type: platformAgentDevicesLoadOp.events.SUCCEEDED,
            payload: {
                result: {
                    items: [
                        {
                            device_id: 'old',
                            device_name: 'Old Laptop',
                            is_active: true,
                            is_tunnel_online: true,
                            last_seen_at: '2026-01-01T00:00:00Z',
                        },
                        {
                            device_id: 'offline',
                            device_name: 'Offline',
                            is_active: true,
                            is_tunnel_online: false,
                            last_seen_at: '2026-07-01T00:00:00Z',
                        },
                        {
                            device_id: 'fresh',
                            device_name: 'Fresh Mac',
                            is_active: true,
                            is_tunnel_online: true,
                            last_seen_at: '2026-07-18T12:00:00Z',
                        },
                    ],
                },
            },
        });
        expect(next.online_device_id).toBe('fresh');
        expect(next.online_device_name).toBe('Fresh Mac');
    });

    it('extraReducer без online устройств очищает presence', () => {
        const next = platformAgentDevicesLoadOp.reducer(
            { ...emptyState, online_device_id: 'x', online_device_name: 'X' },
            {
                type: platformAgentDevicesLoadOp.events.SUCCEEDED,
                payload: {
                    result: {
                        items: [
                            {
                                device_id: 'a',
                                device_name: 'A',
                                is_active: false,
                                is_tunnel_online: true,
                                last_seen_at: '2026-07-18T12:00:00Z',
                            },
                        ],
                    },
                },
            },
        );
        expect(next.online_device_id).toBe('');
        expect(next.online_device_name).toBe('');
    });
});

describe('createPlatformAgentDevicesAuthEffect', () => {
    it('AUTH_USER_LOADED загружает devices?mine=true', async () => {
        registerFactory(platformAgentDevicesLoadOp);
        fetchMock.respondJson('GET', '/frontend/api/agent/devices?mine=true', {
            items: [],
        });
        const dispatched = [];
        await createPlatformAgentDevicesAuthEffect()(
            {
                type: CoreEvents.AUTH_USER_LOADED,
                id: 'auth1',
                payload: {},
                meta: { ts: 0, source: 'local' },
            },
            buildCtx(() => ({}), dispatched),
        );
        expect(
            fetchMock.calls.some((call) => call.url.includes('/frontend/api/agent/devices?mine=true')),
        ).toBe(true);
    });
});
