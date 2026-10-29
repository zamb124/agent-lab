/**
 * Normalize AgentSkill API payloads for UI (strict, no fallbacks).
 */

import { isPlainRecord } from '@platform/lib/events/payload.js';

/** Fixed platform icon for Agent Skills (chips, list, picker, sidebar). */
export const AGENT_SKILL_ICON = 'scroll-text';

interface AgentSkillToolRef {
    tool_id: string;
    name?: string;
    title?: string;
    description?: string;
    parameters_schema?: Record<string, unknown>;
}

interface AgentSkillFileRef {
    original_name: string;
    content_type: string;
    file_size: number;
    file_id?: string;
    url?: string;
}

export function requireAgentSkillString(value: unknown, field: string) {
    if (typeof value !== 'string') {
        throw new Error(`agent_skill: ${field} must be string`);
    }
    return value;
}

function _normalizeToolRef(raw: unknown): AgentSkillToolRef {
    if (!isPlainRecord(raw)) {
        throw new Error('agent_skill: tool_refs[] must be object');
    }
    const toolId = requireAgentSkillString(raw.tool_id, 'tool_refs[].tool_id');
    const out: AgentSkillToolRef = { tool_id: toolId };
    if (typeof raw.name === 'string') out.name = raw.name;
    if (typeof raw.title === 'string') out.title = raw.title;
    if (typeof raw.description === 'string') out.description = raw.description;
    if (raw.parameters_schema !== undefined && raw.parameters_schema !== null) {
        if (!isPlainRecord(raw.parameters_schema)) {
            throw new Error('agent_skill: tool_refs[].parameters_schema must be object');
        }
        out.parameters_schema = raw.parameters_schema;
    }
    return out;
}

function _normalizeFileRef(raw: unknown, field: string): AgentSkillFileRef {
    if (!isPlainRecord(raw)) {
        throw new Error(`agent_skill: ${field}[] must be object`);
    }
    const out: AgentSkillFileRef = {
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

function recordCopies(value: unknown, field: string): Record<string, unknown>[] {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`agent_skill: ${field} must be an array`);
    }
    const rows: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) {
            throw new Error(`agent_skill: ${field}[] must be object`);
        }
        rows.push({ ...item });
    }
    return rows;
}

function unknownList(value: unknown, field: string): unknown[] {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`agent_skill: ${field} must be an array`);
    }
    const items: unknown[] = [];
    for (const item of value) {
        items.push(item);
    }
    return items;
}

function stringCopies(value: unknown, field: string): string[] {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error(`agent_skill: ${field} must be an array`);
    }
    const rows: string[] = [];
    for (const [index, item] of value.entries()) {
        if (typeof item !== 'string') {
            throw new Error(`agent_skill: ${field}[${index}] must be string`);
        }
        rows.push(item);
    }
    return rows;
}

const AGENT_SKILL_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidAgentSkillId(value: unknown) {
    return typeof value === 'string' && AGENT_SKILL_ID_PATTERN.test(value);
}

/**
 * Suggest a free copy id: `base-copy`, then `base-copy-2`, …
 * @param {string} sourceId
 * @param {Iterable<string>} existingIds
 */
export function suggestAgentSkillCopyId(sourceId: string, existingIds: Iterable<string>) {
    const base = typeof sourceId === 'string' ? sourceId.trim() : '';
    if (!isValidAgentSkillId(base)) {
        throw new Error('suggestAgentSkillCopyId: valid source agent_skill_id required');
    }
    const taken = new Set<string>();
    const ids = existingIds === undefined || existingIds === null ? [] : existingIds;
    for (const id of ids) {
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
export function buildAgentSkillDuplicatePayload(source: unknown, opts: unknown) {
    if (!isPlainRecord(source)) {
        throw new Error('buildAgentSkillDuplicatePayload: source required');
    }
    if (!isPlainRecord(opts)) {
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
        tool_refs: recordCopies(source.tool_refs, 'tool_refs'),
        depends_on: stringCopies(source.depends_on, 'depends_on'),
        references: recordCopies(source.references, 'references'),
        assets: recordCopies(source.assets, 'assets'),
    };
}

/**
 * Replace one attached skill id with another (dedupe). Used after duplicate from chip modal.
 * @param {string[]} attached
 * @param {string} fromId
 * @param {string} toId
 * @returns {string[]}
 */
export function replaceAttachedAgentSkillId(attached: string[], fromId: string, toId: string) {
    if (!Array.isArray(attached)) {
        throw new Error('replaceAttachedAgentSkillId: attached must be string[]');
    }
    if (typeof fromId !== 'string' || fromId.length === 0) {
        throw new Error('replaceAttachedAgentSkillId: fromId required');
    }
    if (typeof toId !== 'string' || toId.length === 0) {
        throw new Error('replaceAttachedAgentSkillId: toId required');
    }
    const next: string[] = [];
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

export function mapAgentSkillItem(raw: unknown) {
    if (!isPlainRecord(raw)) {
        throw new Error('agent_skill: item must be object');
    }
    const toolRefs = unknownList(raw.tool_refs, 'tool_refs').map((item) => _normalizeToolRef(item));
    const dependsOn = stringCopies(raw.depends_on, 'depends_on').map((id, index) => {
            if (id.trim().length === 0) {
                throw new Error(`agent_skill: depends_on[${index}] must be non-empty string`);
            }
            return id;
        });
    const references = unknownList(raw.references, 'references').map((item) => _normalizeFileRef(item, 'references'));
    const assets = unknownList(raw.assets, 'assets').map((item) => _normalizeFileRef(item, 'assets'));
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
