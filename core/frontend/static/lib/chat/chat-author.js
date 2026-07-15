/** Canonical, transport-independent author contract for shared chat bubbles. */

export const CHAT_AUTHOR_KINDS = Object.freeze([
    'user',
    'agent',
    'subagent',
    'operator',
    'system',
]);

const AUTHOR_KIND_SET = new Set(CHAT_AUTHOR_KINDS);

function cleanString(value) {
    return typeof value === 'string' ? value.trim() : '';
}

export function authorKindForRole(role) {
    if (role === 'user') return 'user';
    if (role === 'operator') return 'operator';
    if (role === 'system') return 'system';
    return 'agent';
}

/** @returns {{kind: string, name: string, flowId: string, nodeId: string}} */
export function normalizeChatAuthor(value, role = 'assistant') {
    const raw = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const rawKind = cleanString(raw.kind);
    const kind = AUTHOR_KIND_SET.has(rawKind) ? rawKind : authorKindForRole(role);
    return {
        kind,
        name: cleanString(raw.name),
        flowId: cleanString(raw.flowId || raw.flow_id),
        nodeId: cleanString(raw.nodeId || raw.node_id),
    };
}

export function mergeChatAuthor(primary, fallback, role = 'assistant') {
    const first = normalizeChatAuthor(primary, role);
    const second = normalizeChatAuthor(fallback, role);
    const primaryKind = primary && typeof primary === 'object' && !Array.isArray(primary)
        ? cleanString(primary.kind)
        : '';
    return {
        kind: AUTHOR_KIND_SET.has(primaryKind) ? first.kind : second.kind,
        name: first.name || second.name,
        flowId: first.flowId || second.flowId,
        nodeId: first.nodeId || second.nodeId,
    };
}
