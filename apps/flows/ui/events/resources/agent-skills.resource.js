/**
 * Agent Skills — company catalog progressive procedure packs for llm_node.
 * REST: `apps/flows/src/api/v1/agent_skills.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { mapAgentSkillItem } from '../../_helpers/agent-skill-map.js';

const skillItemUrl = (id) => `/flows/api/v1/agent-skills/${encodeURIComponent(id)}`;

export { mapAgentSkillItem };

export const agentSkillsResource = createResourceCollection({
    name: 'flows/agent_skills',
    baseUrl: '/flows/api/v1/agent-skills',
    idField: 'agent_skill_id',
    buildItemUrl: skillItemUrl,
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    listFetchAllPages: true,
    listQuery: () => ({ limit: 200, offset: 0 }),
    mapItem: mapAgentSkillItem,
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/agent-skills' },
        get: { method: 'GET', path: '/flows/api/v1/agent-skills/:agent_skill_id' },
        create: { method: 'POST', path: '/flows/api/v1/agent-skills' },
        update: { method: 'PUT', path: '/flows/api/v1/agent-skills/:agent_skill_id' },
        remove: { method: 'DELETE', path: '/flows/api/v1/agent-skills/:agent_skill_id' },
    },
    toastKeys: {
        create: 'flows:toast.agent_skill_created',
        create_error: 'flows:toast.agent_skill_create_error',
        update: 'flows:toast.agent_skill_updated',
        update_error: 'flows:toast.agent_skill_update_error',
        remove: 'flows:toast.agent_skill_removed',
        remove_error: 'flows:toast.agent_skill_remove_error',
    },
});

/** Silent: preview (`persist:false`) and persist share one op; modal owns toasts. */
export const agentSkillImportOp = createAsyncOp({
    name: 'flows/agent_skill_import',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/agent_skills/import_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/agent-skills/import' },
});

/** Idempotent platform seed for existing companies (no toast). */
export const agentSkillsEnsureSeedOp = createAsyncOp({
    name: 'flows/agent_skills_ensure_seed',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/agent_skills/ensure_seed_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/agent-skills/ensure-seed' },
});
