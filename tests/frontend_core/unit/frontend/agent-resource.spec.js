/**
 * frontend/agent resource — restMirror contract.
 */

import { describe, it, expect } from 'vitest';
import {
    agentPairingCreateOp,
    agentDevicesLoadOp,
    agentDeviceRevokeOp,
    agentReleasesStatusOp,
    agentDevicePolicyPatchOp,
    agentAuditLoadOp,
} from '../../../../apps/frontend/ui/events/resources/agent.resource.js';

describe('frontend/agent resource restMirror', () => {
    it('pairing create mirrors POST /frontend/api/agent/pairing', () => {
        expect(agentPairingCreateOp.restMirror).toEqual({
            method: 'POST',
            path: '/frontend/api/agent/pairing',
        });
    });

    it('devices load mirrors GET /frontend/api/agent/devices', () => {
        expect(agentDevicesLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/agent/devices',
        });
    });

    it('audit load mirrors GET /frontend/api/agent/audit', () => {
        expect(agentAuditLoadOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/agent/audit',
        });
    });

    it('all ops are WS commands frontend/agent/* with REST mirror', () => {
        const expected = {
            [agentPairingCreateOp.name]: 'frontend/agent/pairing_create_requested',
            [agentDevicesLoadOp.name]: 'frontend/agent/devices_list_requested',
            [agentDeviceRevokeOp.name]: 'frontend/agent/device_revoke_requested',
            [agentDevicePolicyPatchOp.name]: 'frontend/agent/device_policy_update_requested',
            [agentAuditLoadOp.name]: 'frontend/agent/audit_list_requested',
        };
        for (const op of [
            agentPairingCreateOp,
            agentDevicesLoadOp,
            agentDeviceRevokeOp,
            agentDevicePolicyPatchOp,
            agentAuditLoadOp,
        ]) {
            expect(op.transport).toBe('ws');
            expect(op.commandType).toBe(expected[op.name]);
        }
    });

    it('revoke and policy patch mirror device routes', () => {
        expect(agentDeviceRevokeOp.restMirror).toEqual({
            method: 'DELETE',
            path: '/frontend/api/agent/devices/:device_id',
        });
        expect(agentDevicePolicyPatchOp.restMirror).toEqual({
            method: 'PATCH',
            path: '/frontend/api/agent/devices/:device_id/policy',
        });
    });

    it('releases status mirrors GET /frontend/api/agent/releases/status', () => {
        expect(agentReleasesStatusOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/agent/releases/status',
        });
    });
});
