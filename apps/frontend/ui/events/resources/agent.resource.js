/**
 * HumanitecAgent — pairing, devices, releases status.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const AGENT_BASE = '/frontend/api/agent';

export const agentPairingCreateOp = createAsyncOp({
    name: 'frontend/agent_pairing_create',
    successToastKey: 'frontend:settings_page.agent.pairing_created',
    errorToastKey: 'frontend:settings_page.agent.pairing_failed',
    restMirror: { method: 'POST', path: '/frontend/api/agent/pairing' },
    request: async () => await httpRequest({
        method: 'POST',
        url: `${AGENT_BASE}/pairing`,
    }),
});

export const agentDevicesLoadOp = createAsyncOp({
    name: 'frontend/agent_devices_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/agent/devices' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${AGENT_BASE}/devices`,
    }),
});

export const agentDeviceRevokeOp = createAsyncOp({
    name: 'frontend/agent_device_revoke',
    successToastKey: 'frontend:settings_page.agent.device_revoked',
    errorToastKey: 'frontend:settings_page.agent.device_revoke_failed',
    restMirror: { method: 'DELETE', path: '/frontend/api/agent/devices/:device_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('agent_device_revoke: payload required');
        }
        const deviceId = payload.device_id;
        if (typeof deviceId !== 'string' || !deviceId) {
            throw new Error('agent_device_revoke: device_id required');
        }
        return await httpRequest({
            method: 'DELETE',
            url: `${AGENT_BASE}/devices/${encodeURIComponent(deviceId)}`,
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(agentDevicesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const agentReleasesStatusOp = createAsyncOp({
    name: 'frontend/agent_releases_status',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/agent/releases/status' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${AGENT_BASE}/releases/status`,
    }),
});

export const agentDevicePolicyPatchOp = createAsyncOp({
    name: 'frontend/agent_device_policy_patch',
    successToastKey: 'frontend:settings_page.agent.policy_saved',
    errorToastKey: 'frontend:settings_page.agent.policy_save_failed',
    restMirror: { method: 'PATCH', path: '/frontend/api/agent/devices/:device_id/policy' },
    request: async ({ payload }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('agent_device_policy_patch: payload required');
        }
        const deviceId = payload.device_id;
        const policy = payload.policy;
        if (typeof deviceId !== 'string' || !deviceId) {
            throw new Error('agent_device_policy_patch: device_id required');
        }
        if (!policy || typeof policy !== 'object') {
            throw new Error('agent_device_policy_patch: policy required');
        }
        return await httpRequest({
            method: 'PATCH',
            url: `${AGENT_BASE}/devices/${encodeURIComponent(deviceId)}/policy`,
            body: { policy },
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(agentDevicesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const agentAuditLoadOp = createAsyncOp({
    name: 'frontend/agent_audit_load',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/agent/audit' },
    request: async () => await httpRequest({
        method: 'GET',
        url: `${AGENT_BASE}/audit`,
    }),
});
