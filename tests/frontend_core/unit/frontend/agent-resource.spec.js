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
import { buildCtx } from '../../helpers/bus-fixtures.js';

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

    it('revoke requires device_id payload', async () => {
        await expect(agentDeviceRevokeOp.run({}, buildCtx())).rejects.toThrow(
            'agent_device_revoke: device_id required',
        );
    });

    it('policy patch requires policy payload', async () => {
        await expect(
            agentDevicePolicyPatchOp.run({ device_id: 'device-1' }, buildCtx()),
        ).rejects.toThrow('agent_device_policy_patch: policy required');
    });

    it('releases status mirrors GET /frontend/api/agent/releases/status', () => {
        expect(agentReleasesStatusOp.restMirror).toEqual({
            method: 'GET',
            path: '/frontend/api/agent/releases/status',
        });
    });
});
