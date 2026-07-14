/**
 * Normalize AgentSkill API payloads for UI (strict, no fallbacks).
 */

/** Fixed platform icon for Agent Skills (chips, list, picker, sidebar). */
export const AGENT_SKILL_ICON = 'sparkles';

export function requireAgentSkillString(value, field) {
    if (typeof value !== 'string') {
        throw new Error(`agent_skill: ${field} must be string`);
    }
    return value;
}

function _normalizeToolRef(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('agent_skill: tool_refs[] must be object');
    }
    const toolId = requireAgentSkillString(raw.tool_id, 'tool_refs[].tool_id');
    const out = { tool_id: toolId };
    if (typeof raw.name === 'string') out.name = raw.name;
    if (typeof raw.title === 'string') out.title = raw.title;
    if (typeof raw.description === 'string') out.description = raw.description;
    if (raw.parameters_schema && typeof raw.parameters_schema === 'object') {
        out.parameters_schema = raw.parameters_schema;
    }
    return out;
}

function _normalizeFileRef(raw, field) {
    if (!raw || typeof raw !== 'object') {
        throw new Error(`agent_skill: ${field}[] must be object`);
    }
    const out = {
        original_name: requireAgentSkillString(raw.original_name, `${field}[].original_name`),
        content_type: requireAgentSkillString(raw.content_type, `${field}[].content_type`),
        file_size: typeof raw.file_size === 'number' ? raw.file_size : 0,
    };
    if (typeof raw.file_id === 'string' && raw.file_id.length > 0) {
        out.file_id = raw.file_id;
    }
    if (typeof raw.url === 'string' && raw.url.length > 0) {
        out.url = raw.url;
    }
    return out;
}

const AGENT_SKILL_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidAgentSkillId(value) {
    return typeof value === 'string' && AGENT_SKILL_ID_PATTERN.test(value);
}

/**
 * Suggest a free copy id: `base-copy`, then `base-copy-2`, …
 * @param {string} sourceId
 * @param {Iterable<string>} existingIds
 */
export function suggestAgentSkillCopyId(sourceId, existingIds) {
    const base = typeof sourceId === 'string' ? sourceId.trim() : '';
    if (!isValidAgentSkillId(base)) {
        throw new Error('suggestAgentSkillCopyId: valid source agent_skill_id required');
    }
    const taken = new Set();
    for (const id of existingIds || []) {
        if (typeof id === 'string' && id.length > 0) {
            taken.add(id);
        }
    }
    const first = `${base}-copy`;
    if (!taken.has(first)) {
        return first;
    }
    let n = 2;
    while (taken.has(`${base}-copy-${n}`)) {
        n += 1;
        if (n > 10_000) {
            throw new Error('suggestAgentSkillCopyId: exhausted copy id space');
        }
    }
    return `${base}-copy-${n}`;
}

/**
 * Create-payload for duplicating a skill (new id + cloned fields).
 * @param {object} source — mapped AgentSkill
 * @param {{ agent_skill_id: string, name?: string }} opts
 */
export function buildAgentSkillDuplicatePayload(source, opts) {
    if (!source || typeof source !== 'object') {
        throw new Error('buildAgentSkillDuplicatePayload: source required');
    }
    if (!opts || typeof opts !== 'object') {
        throw new Error('buildAgentSkillDuplicatePayload: opts required');
    }
    const newId = typeof opts.agent_skill_id === 'string' ? opts.agent_skill_id.trim() : '';
    if (!isValidAgentSkillId(newId)) {
        throw new Error('buildAgentSkillDuplicatePayload: valid agent_skill_id required');
    }
    if (newId === source.agent_skill_id) {
        throw new Error('buildAgentSkillDuplicatePayload: new id must differ from source');
    }
    const nameRaw = typeof opts.name === 'string' ? opts.name.trim() : '';
    const name = nameRaw.length > 0
        ? nameRaw
        : `${requireAgentSkillString(source.name, 'name')} (copy)`;
    return {
        agent_skill_id: newId,
        name,
        description: requireAgentSkillString(source.description, 'description'),
        body_markdown: requireAgentSkillString(source.body_markdown, 'body_markdown'),
        tool_refs: Array.isArray(source.tool_refs)
            ? source.tool_refs.map((ref) => ({ ...ref }))
            : [],
        depends_on: Array.isArray(source.depends_on) ? [...source.depends_on] : [],
        references: Array.isArray(source.references)
            ? source.references.map((ref) => ({ ...ref }))
            : [],
        assets: Array.isArray(source.assets)
            ? source.assets.map((ref) => ({ ...ref }))
            : [],
    };
}

/**
 * Replace one attached skill id with another (dedupe). Used after duplicate from chip modal.
 * @param {string[]} attached
 * @param {string} fromId
 * @param {string} toId
 * @returns {string[]}
 */
export function replaceAttachedAgentSkillId(attached, fromId, toId) {
    if (!Array.isArray(attached)) {
        throw new Error('replaceAttachedAgentSkillId: attached must be string[]');
    }
    if (typeof fromId !== 'string' || fromId.length === 0) {
        throw new Error('replaceAttachedAgentSkillId: fromId required');
    }
    if (typeof toId !== 'string' || toId.length === 0) {
        throw new Error('replaceAttachedAgentSkillId: toId required');
    }
    const next = [];
    const seen = new Set();
    for (const sid of attached) {
        if (typeof sid !== 'string' || sid.length === 0) {
            continue;
        }
        const mapped = sid === fromId ? toId : sid;
        if (seen.has(mapped)) {
            continue;
        }
        seen.add(mapped);
        next.push(mapped);
    }
    return next;
}

export function mapAgentSkillItem(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('agent_skill: item must be object');
    }
    const toolRefs = Array.isArray(raw.tool_refs)
        ? raw.tool_refs.map((item) => _normalizeToolRef(item))
        : [];
    const dependsOn = Array.isArray(raw.depends_on)
        ? raw.depends_on.map((id, index) => {
            if (typeof id !== 'string' || id.trim().length === 0) {
                throw new Error(`agent_skill: depends_on[${index}] must be non-empty string`);
            }
            return id;
        })
        : [];
    const references = Array.isArray(raw.references)
        ? raw.references.map((item) => _normalizeFileRef(item, 'references'))
        : [];
    const assets = Array.isArray(raw.assets)
        ? raw.assets.map((item) => _normalizeFileRef(item, 'assets'))
        : [];
    return {
        agent_skill_id: requireAgentSkillString(raw.agent_skill_id, 'agent_skill_id'),
        name: requireAgentSkillString(raw.name, 'name'),
        description: requireAgentSkillString(raw.description, 'description'),
        body_markdown: requireAgentSkillString(raw.body_markdown, 'body_markdown'),
        tool_refs: toolRefs,
        depends_on: dependsOn,
        references,
        assets,
    };
}
