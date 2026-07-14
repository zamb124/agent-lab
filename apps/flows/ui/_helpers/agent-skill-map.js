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

export function mapAgentSkillItem(raw) {
    if (!raw || typeof raw !== 'object') {
        throw new Error('agent_skill: item must be object');
    }
    const activation = raw.activation === 'auto' ? 'auto' : 'explicit';
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
        activation,
    };
}
