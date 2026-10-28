/**
 * Cover gradients for flow cards, presets and library tiles.
 * Values are CSS var() references to --flows-cover-gradient-* in tokens.css.
 */

export const FLOW_COVER_GRADIENT_VARS = Object.freeze([
    'var(--flows-cover-gradient-1)',
    'var(--flows-cover-gradient-2)',
    'var(--flows-cover-gradient-3)',
    'var(--flows-cover-gradient-4)',
    'var(--flows-cover-gradient-5)',
    'var(--flows-cover-gradient-6)',
    'var(--flows-cover-gradient-7)',
    'var(--flows-cover-gradient-8)',
]);

export const FLOW_PRESET_GRADIENT_BY_ID = Object.freeze({
    react: 'var(--flows-preset-react-gradient)',
    graph: 'var(--flows-preset-graph-gradient)',
    multi: 'var(--flows-preset-multi-gradient)',
    code: 'var(--flows-preset-code-gradient)',
    external: 'var(--flows-preset-external-gradient)',
});

/**
 * @param {string} flowId
 * @returns {string}
 */
export function resolveFlowCoverGradient(flowId: string) {
    if (typeof flowId !== 'string' || flowId.length === 0) {
        throw new Error('resolveFlowCoverGradient: flowId is required');
    }
    let hash = 0;
    for (let index = 0; index < flowId.length; index += 1) {
        hash += flowId.charCodeAt(index);
    }
    return FLOW_COVER_GRADIENT_VARS[hash % FLOW_COVER_GRADIENT_VARS.length];
}

/**
 * @param {string} presetId
 * @returns {string}
 */
export function resolveFlowPresetGradient(presetId: any) {
    if (typeof presetId !== 'string' || presetId.length === 0) {
        throw new Error('resolveFlowPresetGradient: presetId is required');
    }
    const gradient = (FLOW_PRESET_GRADIENT_BY_ID as any)[presetId];
    if (typeof gradient !== 'string') {
        throw new Error(`resolveFlowPresetGradient: unknown presetId ${presetId}`);
    }
    return gradient;
}
