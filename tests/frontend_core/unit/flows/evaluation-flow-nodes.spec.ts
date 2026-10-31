/**
 * @vitest-environment node
 */

import { describe, expect, it } from 'vitest';
import {
    canvasNodeTypeSubtitle,
    evaluationRoleFromNode,
    isEvaluationRoleNode,
    isPortlessCanvasNode,
} from '../../../../apps/flows/ui/_helpers/evaluation-flow-nodes.js';

describe('evaluation-flow-nodes portless helpers', () => {
    it('detects tester and judge by store.evaluation_role', () => {
        expect(isEvaluationRoleNode({
            type: 'llm_node',
            store: { evaluation_role: 'tester' },
        })).toBe(true);
        expect(isEvaluationRoleNode({
            type: 'llm_node',
            store: { evaluation_role: 'judge' },
        })).toBe(true);
        expect(isEvaluationRoleNode({ type: 'llm_node', prompt: 'plain' })).toBe(false);
        expect(isEvaluationRoleNode({ type: 'resource' })).toBe(false);
        expect(evaluationRoleFromNode({ store: { evaluation_role: 'tester' } })).toBe('tester');
    });

    it('marks resource and evaluation as portless canvas nodes', () => {
        expect(isPortlessCanvasNode({ type: 'resource' })).toBe(true);
        expect(isPortlessCanvasNode({
            type: 'llm_node',
            store: { evaluation_role: 'judge' },
        })).toBe(true);
        expect(isPortlessCanvasNode({ type: 'llm_node' })).toBe(false);
        expect(isPortlessCanvasNode(null)).toBe(false);
    });

    it('shows evaluation role as canvas type subtitle', () => {
        expect(canvasNodeTypeSubtitle({
            type: 'llm_node',
            store: { evaluation_role: 'tester' },
        })).toBe('tester');
        expect(canvasNodeTypeSubtitle({
            type: 'llm_node',
            store: { evaluation_role: 'judge' },
        })).toBe('judge');
        expect(canvasNodeTypeSubtitle({ type: 'llm_node' })).toBe('llm_node');
        expect(canvasNodeTypeSubtitle({ type: 'resource' })).toBe('resource');
    });
});
