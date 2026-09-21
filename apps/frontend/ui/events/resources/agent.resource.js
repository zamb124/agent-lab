/**
 * LinnexAgent в консоли компании — pairing, устройства, политика, аудит
 * (команды `frontend/agent/*`, REST-зеркало `apps/frontend/api/agent.py`) и публичный статус релизов.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const WS_TIMEOUT_MS = 8_000;

export const agentPairingCreateOp = createAsyncOp({
    name: 'frontend/agent_pairing_create',
    successToastKey: 'frontend:settings_page.agent.pairing_created',
    errorToastKey: 'frontend:settings_page.agent.pairing_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/agent/pairing_create_requested',
    restMirror: { method: 'POST', path: '/frontend/api/agent/pairing' },
});

export const agentDevicesLoadOp = createAsyncOp({
    name: 'frontend/agent_devices_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/agent/devices_list_requested',
    restMirror: { method: 'GET', path: '/frontend/api/agent/devices' },
});

export const agentDeviceRevokeOp = createAsyncOp({
    name: 'frontend/agent_device_revoke',
    successToastKey: 'frontend:settings_page.agent.device_revoked',
    errorToastKey: 'frontend:settings_page.agent.device_revoke_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/agent/device_revoke_requested',
    restMirror: { method: 'DELETE', path: '/frontend/api/agent/devices/:device_id' },
    onSuccess: (ctx) => {
        ctx.dispatch(agentDevicesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

// Публичный статус релизов: anonymous route для страницы загрузки, поэтому HTTP, не команда.
export const agentReleasesStatusOp = createAsyncOp({
    name: 'frontend/agent_releases_status',
    silent: true,
    restMirror: { method: 'GET', path: '/frontend/api/agent/releases/status' },
    request: async () => await httpRequest({
        method: 'GET',
        url: '/frontend/api/agent/releases/status',
    }),
});

export const agentDevicePolicyPatchOp = createAsyncOp({
    name: 'frontend/agent_device_policy_patch',
    successToastKey: 'frontend:settings_page.agent.policy_saved',
    errorToastKey: 'frontend:settings_page.agent.policy_save_failed',
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/agent/device_policy_update_requested',
    restMirror: { method: 'PATCH', path: '/frontend/api/agent/devices/:device_id/policy' },
    onSuccess: (ctx) => {
        ctx.dispatch(agentDevicesLoadOp.events.REQUESTED, null, { source: 'local' });
    },
});

export const agentAuditLoadOp = createAsyncOp({
    name: 'frontend/agent_audit_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: WS_TIMEOUT_MS,
    commandType: 'frontend/agent/audit_list_requested',
    restMirror: { method: 'GET', path: '/frontend/api/agent/audit' },
});
