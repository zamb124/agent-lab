const REFLECTION_LLM_TEMPLATE = Object.freeze({
    provider: 'humanitec_llm',
    model: 'auto',
});

const REFLECTION_POLICY_TEMPLATE = Object.freeze({
    policy_id: 'final_answer_quality_gate',
    gate: 'final_answer',
    target: Object.freeze({ kind: 'response' }),
    instruction: 'Review the selected output and return a structured gate decision.',
    criteria: Object.freeze([
        Object.freeze({
            criterion_id: 'task_satisfied',
            description: 'The output directly satisfies the requested task.',
            severity: 'error',
        }),
        Object.freeze({
            criterion_id: 'unsafe_side_effect',
            description: 'The output must not approve unsafe or unrequested side effects.',
            severity: 'critical',
        }),
    ]),
    min_confidence: 0.8,
    block_on_severities: Object.freeze(['error', 'critical']),
});

function cloneJson(value) {
    return JSON.parse(JSON.stringify(value));
}

export function getReflectionPolicyTemplate() {
    return cloneJson(REFLECTION_POLICY_TEMPLATE);
}

export function getReflectionLlmTemplate() {
    return cloneJson(REFLECTION_LLM_TEMPLATE);
}

export function getBlankReflectionNodeConfig() {
    return {
        llm: getReflectionLlmTemplate(),
        critic_policy: getReflectionPolicyTemplate(),
        tools: [],
        prompt: '',
        structured_output: false,
    };
}
