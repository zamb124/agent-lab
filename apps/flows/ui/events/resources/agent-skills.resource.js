/**
 * Agent Skills — company catalog progressive procedure packs for llm_node.
 * REST: `apps/flows/src/api/v1/agent_skills.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { mapAgentSkillItem } from '../../_helpers/agent-skill-map.js';

const skillItemUrl = (id) => `/flows/api/v1/agent-skills/${encodeURIComponent(id)}`;

export { mapAgentSkillItem };

export const agentSkillsResource = createResourceCollection({
    name: 'flows/agent_skills',
    baseUrl: '/flows/api/v1/agent-skills',
    idField: 'agent_skill_id',
    buildItemUrl: skillItemUrl,
    operations: ['list', 'get', 'create', 'remove'],
    listFetchAllPages: true,
    listQuery: () => ({ limit: 200, offset: 0 }),
    mapItem: mapAgentSkillItem,
    toastKeys: {
        create: 'flows:toast.agent_skill_created',
        create_error: 'flows:toast.agent_skill_create_error',
        remove: 'flows:toast.agent_skill_removed',
        remove_error: 'flows:toast.agent_skill_remove_error',
    },
});

/** Backend requires PUT (resource-collection update is PATCH). */
export const agentSkillUpdateOp = createAsyncOp({
    name: 'flows/agent_skill_update',
    successToastKey: 'flows:toast.agent_skill_updated',
    errorToastKey: 'flows:toast.agent_skill_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/agent-skills/{agent_skill_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.agent_skill_id !== 'string' || !payload.body) {
            throw new Error('agentSkillUpdateOp: { agent_skill_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: skillItemUrl(payload.agent_skill_id),
            body: payload.body,
        });
    },
});

/** Silent: preview (`persist:false`) and persist share one op; modal owns toasts. */
export const agentSkillImportOp = createAsyncOp({
    name: 'flows/agent_skill_import',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/agent-skills/import' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.markdown !== 'string') {
            throw new Error('agentSkillImportOp: { markdown } required');
        }
        const body = {
            markdown: payload.markdown,
            persist: payload.persist !== false,
        };
        if (typeof payload.agent_skill_id === 'string' && payload.agent_skill_id.length > 0) {
            body.agent_skill_id = payload.agent_skill_id;
        }
        return httpRequest({
            method: 'POST',
            url: '/flows/api/v1/agent-skills/import',
            body,
        });
    },
});

/** Idempotent platform seed for existing companies (no toast). */
export const agentSkillsEnsureSeedOp = createAsyncOp({
    name: 'flows/agent_skills_ensure_seed',
    silent: true,
    restMirror: { method: 'POST', path: '/flows/api/v1/agent-skills/ensure-seed' },
    request: async () => httpRequest({
        method: 'POST',
        url: '/flows/api/v1/agent-skills/ensure-seed',
        body: {},
    }),
});
