/**
 * @vitest-environment node
 */

import { describe, expect, it } from 'vitest';
import { prop } from '../../helpers/prop.js';
import {
    getBlankReflectionNodeConfig,
    getReflectionPolicyPreset,
    getReflectionPolicyTemplate,
    buildReflectionExitEdge,
    listReflectionExits,
    reflectionExitCondition,
    inferReflectionExitPortFromCondition,
    syncReflectionEdgeFromPort,
    reflectionOutPortYFraction,
    REFLECTION_POLICY_PRESET_IDS,
} from '../../../../apps/flows/ui/_helpers/flows-reflection-defaults.js';

describe('flows reflection defaults', () => {
    it('builds blank reflection node with critic_policy and llm', () => {
        const cfg = getBlankReflectionNodeConfig();
        expect(cfg.llm.provider).toBe('linnex_llm');
        expect(cfg.critic_policy.gate).toBe('final_answer');
        expect(cfg.critic_policy.criteria.length).toBeGreaterThanOrEqual(1);
        expect(cfg.critic_policy.exits.map((item: { exit_id: string }) => item.exit_id)).toEqual([
            'approved',
            'blocked',
        ]);
        expect(cfg.tools).toEqual([]);
    });

    it('exposes three policy presets with distinct policy_id', () => {
        const ids = REFLECTION_POLICY_PRESET_IDS.map(
            (presetId) => getReflectionPolicyPreset(presetId).policy_id,
        );
        expect(new Set(ids).size).toBe(3);
        expect(getReflectionPolicyTemplate().policy_id).toBe(
            getReflectionPolicyPreset('final_answer').policy_id,
        );
        expect(listReflectionExits(getReflectionPolicyPreset('quality')).map((e) => e.id)).toEqual([
            'pass',
            'revise',
            'reject',
        ]);
    });

    it('builds exit edges with from_port and validation.exit_id condition', () => {
        const approved = buildReflectionExitEdge('r1', 'ok', 'approved');
        expect(approved).toEqual({
            from_node: 'r1',
            to_node: 'ok',
            from_port: 'approved',
            condition: {
                type: 'simple',
                variable: 'validation.exit_id',
                operator: '==',
                value: 'approved',
            },
        });
        const blocked = buildReflectionExitEdge('r1', 'fail', 'blocked');
        expect(blocked.from_port).toBe('blocked');
        expect(blocked.condition.value).toBe('blocked');
    });

    it('infers and syncs from_port from condition edits', () => {
        expect(inferReflectionExitPortFromCondition(reflectionExitCondition('approved'))).toBe(
            'approved',
        );
        expect(inferReflectionExitPortFromCondition(reflectionExitCondition('revise'))).toBe(
            'revise',
        );
        expect(
            inferReflectionExitPortFromCondition({
                type: 'simple',
                variable: 'validation.approved',
                operator: '==',
                value: false,
            }),
        ).toBe('blocked');
        const synced = syncReflectionEdgeFromPort(
            { from_node: 'r1', to_node: 'n2', from_port: 'approved' },
            reflectionExitCondition('blocked'),
        );
        expect(prop(synced, 'from_port')).toBe('blocked');
        const cleared = syncReflectionEdgeFromPort(
            { from_node: 'r1', to_node: 'n2', from_port: 'approved' },
            { type: 'simple', variable: 'result', operator: '==', value: 1 },
        );
        expect('from_port' in cleared ? prop(cleared, 'from_port') : undefined).toBeUndefined();
        expect(prop(prop(cleared, 'condition'), 'variable')).toBe('result');
    });

    it('maps out-port Y fractions for N exits', () => {
        const dual = [
            { id: 'approved', label: 'Approved' },
            { id: 'blocked', label: 'Blocked' },
        ];
        expect(reflectionOutPortYFraction('approved', dual)).toBeLessThan(
            reflectionOutPortYFraction('blocked', dual),
        );
        const triple = [
            { id: 'pass', label: 'Pass' },
            { id: 'revise', label: 'Revise' },
            { id: 'reject', label: 'Reject' },
        ];
        expect(reflectionOutPortYFraction('pass', triple)).toBeLessThan(
            reflectionOutPortYFraction('revise', triple),
        );
        expect(reflectionOutPortYFraction('revise', triple)).toBeLessThan(
            reflectionOutPortYFraction('reject', triple),
        );
        expect(reflectionOutPortYFraction(null, triple)).toBe(0.5);
    });
});
