import { describe, expect, it } from 'vitest';
import {
    FLOW_COVER_GRADIENT_VARS,
    FLOW_PRESET_GRADIENT_BY_ID,
    resolveFlowCoverGradient,
    resolveFlowPresetGradient,
} from '../../../../apps/flows/ui/_helpers/flow-cover-gradients.js';

describe('flow-cover-gradients', () => {
    it('resolveFlowCoverGradient returns token var from palette', () => {
        const gradient = resolveFlowCoverGradient('demo_flow');
        expect(FLOW_COVER_GRADIENT_VARS).toContain(gradient);
        expect(gradient?.startsWith('var(--flows-cover-gradient-')).toBe(true);
    });

    it('resolveFlowCoverGradient is stable for same flowId', () => {
        expect(resolveFlowCoverGradient('alpha')).toBe(resolveFlowCoverGradient('alpha'));
    });

    it('resolveFlowCoverGradient throws without flowId', () => {
        expect(() => resolveFlowCoverGradient('')).toThrow(/flowId is required/);
    });

    it('resolveFlowPresetGradient maps known presets', () => {
        expect(resolveFlowPresetGradient('react')).toBe(FLOW_PRESET_GRADIENT_BY_ID.react);
        expect(resolveFlowPresetGradient('code')).toBe('var(--flows-preset-code-gradient)');
    });

    it('resolveFlowPresetGradient throws for unknown preset', () => {
        expect(() => resolveFlowPresetGradient('unknown')).toThrow(/unknown presetId/);
    });
});
