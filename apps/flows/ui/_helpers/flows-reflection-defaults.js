/**
 * Defaults and helpers for reflection nodes: critic_policy presets + named exit ports.
 */

export const REFLECTION_EXIT_WHEN_KINDS = Object.freeze([
    'approved_true',
    'approved_false',
    'decision_eq',
    'blocked_reason_prefix',
    'always',
]);

export const REFLECTION_GATES = Object.freeze(['final_answer', 'transaction', 'quality']);
export const REFLECTION_TARGET_KINDS = Object.freeze(['response', 'result', 'validation', 'state_path']);
export const CRITIC_SEVERITIES = Object.freeze(['info', 'warning', 'error', 'critical']);
export const CRITIC_DECISIONS = Object.freeze(['approved', 'needs_revision', 'blocked']);

export const REFLECTION_POLICY_PRESET_IDS = Object.freeze([
    'final_answer',
    'transaction',
    'quality',
]);

/** @deprecated use listReflectionExits(policy); kept for dual-port callers */
export const REFLECTION_EXIT_PORTS = Object.freeze(['approved', 'blocked']);

const REFLECTION_LLM_TEMPLATE = Object.freeze({
    provider: 'humanitec_llm',
    model: 'auto',
});

const DEFAULT_PASS_FAIL_EXITS = Object.freeze([
    Object.freeze({
        exit_id: 'approved',
        label: 'Approved',
        when: Object.freeze({ kind: 'approved_true' }),
    }),
    Object.freeze({
        exit_id: 'blocked',
        label: 'Blocked',
        when: Object.freeze({ kind: 'approved_false' }),
    }),
]);

const QUALITY_THREE_EXITS = Object.freeze([
    Object.freeze({
        exit_id: 'pass',
        label: 'Pass',
        when: Object.freeze({ kind: 'approved_true' }),
    }),
    Object.freeze({
        exit_id: 'revise',
        label: 'Needs revision',
        when: Object.freeze({ kind: 'decision_eq', decision: 'needs_revision' }),
    }),
    Object.freeze({
        exit_id: 'reject',
        label: 'Reject',
        when: Object.freeze({ kind: 'always' }),
    }),
]);

const REFLECTION_POLICY_PRESETS = Object.freeze({
    final_answer: Object.freeze({
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
        exits: DEFAULT_PASS_FAIL_EXITS,
    }),
    transaction: Object.freeze({
        policy_id: 'transaction_safety_gate',
        gate: 'transaction',
        target: Object.freeze({ kind: 'result' }),
        instruction:
            'Approve only safe, reversible, explicitly requested actions. Block destructive or unconfirmed side effects.',
        criteria: Object.freeze([
            Object.freeze({
                criterion_id: 'explicit_request',
                description: 'The action matches an explicit user or workflow request.',
                severity: 'error',
            }),
            Object.freeze({
                criterion_id: 'unsafe_side_effect',
                description: 'The output must not approve unsafe or unrequested side effects.',
                severity: 'critical',
            }),
        ]),
        min_confidence: 0.85,
        block_on_severities: Object.freeze(['error', 'critical']),
        exits: DEFAULT_PASS_FAIL_EXITS,
    }),
    quality: Object.freeze({
        policy_id: 'output_quality_gate',
        gate: 'quality',
        target: Object.freeze({ kind: 'response' }),
        instruction:
            'Judge completeness, accuracy, and clarity of the output against the user request.',
        criteria: Object.freeze([
            Object.freeze({
                criterion_id: 'complete_answer',
                description: 'The output covers the requested points without critical gaps.',
                severity: 'error',
            }),
            Object.freeze({
                criterion_id: 'accurate_claims',
                description: 'Claims are supported by available context and are not invented.',
                severity: 'error',
            }),
        ]),
        min_confidence: 0.75,
        block_on_severities: Object.freeze(['error', 'critical']),
        exits: QUALITY_THREE_EXITS,
    }),
});

function cloneJson(value) {
    return JSON.parse(JSON.stringify(value));
}

export function getDefaultPassFailExits() {
    return cloneJson(DEFAULT_PASS_FAIL_EXITS);
}

export function getReflectionPolicyTemplate() {
    return cloneJson(REFLECTION_POLICY_PRESETS.final_answer);
}

export function getReflectionPolicyPreset(presetId) {
    if (typeof presetId !== 'string' || !(presetId in REFLECTION_POLICY_PRESETS)) {
        throw new Error(`getReflectionPolicyPreset: unknown preset ${presetId}`);
    }
    return cloneJson(REFLECTION_POLICY_PRESETS[presetId]);
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

/**
 * @param {unknown} policy
 * @returns {{ id: string, label: string }[]}
 */
export function listReflectionExits(policy) {
    if (!policy || typeof policy !== 'object' || Array.isArray(policy)) {
        return getDefaultPassFailExits().map((exitItem) => ({
            id: exitItem.exit_id,
            label: exitItem.label,
        }));
    }
    const typed = /** @type {Record<string, unknown>} */ (policy);
    const exits = typed.exits;
    if (!Array.isArray(exits) || exits.length === 0) {
        return getDefaultPassFailExits().map((exitItem) => ({
            id: exitItem.exit_id,
            label: exitItem.label,
        }));
    }
    const listed = [];
    for (const raw of exits) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
            continue;
        }
        const item = /** @type {Record<string, unknown>} */ (raw);
        if (typeof item.exit_id !== 'string' || item.exit_id.length === 0) {
            continue;
        }
        const label = typeof item.label === 'string' && item.label.length > 0
            ? item.label
            : item.exit_id;
        listed.push({ id: item.exit_id, label });
    }
    if (listed.length === 0) {
        return getDefaultPassFailExits().map((exitItem) => ({
            id: exitItem.exit_id,
            label: exitItem.label,
        }));
    }
    return listed;
}

/**
 * @param {string} exitId
 */
export function reflectionExitCondition(exitId) {
    if (typeof exitId !== 'string' || exitId.length === 0) {
        throw new Error('reflectionExitCondition: exitId required');
    }
    return {
        type: 'simple',
        variable: 'validation.exit_id',
        operator: '==',
        value: exitId,
    };
}

export function buildReflectionExitEdge(fromNodeId, toNodeId, exitId) {
    if (typeof fromNodeId !== 'string' || fromNodeId.length === 0) {
        throw new Error('buildReflectionExitEdge: fromNodeId required');
    }
    if (typeof toNodeId !== 'string' || toNodeId.length === 0) {
        throw new Error('buildReflectionExitEdge: toNodeId required');
    }
    if (typeof exitId !== 'string' || exitId.length === 0) {
        throw new Error('buildReflectionExitEdge: exitId required');
    }
    return {
        from_node: fromNodeId,
        to_node: toNodeId,
        from_port: exitId,
        condition: reflectionExitCondition(exitId),
    };
}

/**
 * Infer reflection from_port from a simple validation.exit_id or legacy approved condition.
 * @param {unknown} condition
 * @param {Iterable<string>|null|undefined} allowedExitIds
 * @returns {string|null}
 */
export function inferReflectionExitPortFromCondition(condition, allowedExitIds = null) {
    if (!condition || typeof condition !== 'object' || Array.isArray(condition)) {
        return null;
    }
    const typed = /** @type {Record<string, unknown>} */ (condition);
    if (typed.type !== 'simple') {
        return null;
    }
    if (typed.operator !== '==') {
        return null;
    }
    const allowed = allowedExitIds == null
        ? null
        : new Set(Array.from(allowedExitIds));
    if (typed.variable === 'validation.exit_id') {
        if (typeof typed.value !== 'string' || typed.value.length === 0) {
            return null;
        }
        if (allowed !== null && !allowed.has(typed.value)) {
            return null;
        }
        return typed.value;
    }
    if (typed.variable === 'validation.approved') {
        if (typed.value === true) {
            if (allowed !== null && !allowed.has('approved')) {
                return null;
            }
            return 'approved';
        }
        if (typed.value === false) {
            if (allowed !== null && !allowed.has('blocked')) {
                return null;
            }
            return 'blocked';
        }
    }
    return null;
}

/**
 * Sync from_port after condition edit: match known pattern or clear.
 * @param {Record<string, unknown>} edge
 * @param {unknown} condition
 * @param {Iterable<string>|null|undefined} allowedExitIds
 * @returns {Record<string, unknown>}
 */
export function syncReflectionEdgeFromPort(edge, condition, allowedExitIds = null) {
    if (!edge || typeof edge !== 'object') {
        throw new Error('syncReflectionEdgeFromPort: edge object required');
    }
    const inferred = inferReflectionExitPortFromCondition(condition, allowedExitIds);
    if (inferred === null) {
        const next = { ...edge, condition };
        if ('from_port' in next) {
            delete next.from_port;
        }
        return next;
    }
    return { ...edge, condition, from_port: inferred };
}

/**
 * Relative Y (0..1) of out port on reflection node card.
 * @param {string|null|undefined} port
 * @param {{ id: string }[]|null|undefined} exits
 * @returns {number}
 */
export function reflectionOutPortYFraction(port, exits = null) {
    const list = Array.isArray(exits) && exits.length > 0
        ? exits
        : [{ id: 'approved' }, { id: 'blocked' }];
    if (typeof port !== 'string' || port.length === 0) {
        return 0.5;
    }
    const index = list.findIndex((item) => item.id === port);
    if (index < 0) {
        return 0.5;
    }
    if (list.length === 1) {
        return 0.5;
    }
    return 0.18 + (index / (list.length - 1)) * 0.64;
}

export function newBlankCriterion() {
    return {
        criterion_id: `criterion_${Date.now().toString(36)}`,
        description: '',
        severity: 'error',
    };
}

export function newBlankExit() {
    return {
        exit_id: `exit_${Date.now().toString(36)}`,
        label: '',
        when: { kind: 'always' },
    };
}
