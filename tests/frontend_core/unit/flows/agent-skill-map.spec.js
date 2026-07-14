/**
 * Pure helpers for Agent Skill duplicate / chip replace.
 */

import { describe, it, expect } from 'vitest';
import {
    buildAgentSkillDuplicatePayload,
    isValidAgentSkillId,
    replaceAttachedAgentSkillId,
    suggestAgentSkillCopyId,
} from '../../../../apps/flows/ui/_helpers/agent-skill-map.js';

const SOURCE = Object.freeze({
    agent_skill_id: 'networkle',
    name: 'Networkle',
    description: 'CRM domain root',
    body_markdown: '# Body\n',
    tool_refs: [{ tool_id: 'crm_search', description: 'search', parameters_schema: { type: 'object' } }],
    depends_on: ['crm-entities'],
    references: [],
    assets: [],
});

describe('agent-skill-map duplicate helpers', () => {
    it('isValidAgentSkillId принимает slug', () => {
        expect(isValidAgentSkillId('networkle')).toBe(true);
        expect(isValidAgentSkillId('flows-platform')).toBe(true);
        expect(isValidAgentSkillId('Bad_Id')).toBe(false);
        expect(isValidAgentSkillId('')).toBe(false);
    });

    it('suggestAgentSkillCopyId выбирает свободный id', () => {
        expect(suggestAgentSkillCopyId('networkle', [])).toBe('networkle-copy');
        expect(suggestAgentSkillCopyId('networkle', ['networkle-copy'])).toBe('networkle-copy-2');
        expect(suggestAgentSkillCopyId('networkle', ['networkle-copy', 'networkle-copy-2'])).toBe(
            'networkle-copy-3',
        );
    });

    it('buildAgentSkillDuplicatePayload клонирует поля с новым id', () => {
        const payload = buildAgentSkillDuplicatePayload(SOURCE, {
            agent_skill_id: 'networkle-copy',
            name: 'Networkle (copy)',
        });
        expect(payload).toEqual({
            agent_skill_id: 'networkle-copy',
            name: 'Networkle (copy)',
            description: 'CRM domain root',
            body_markdown: '# Body\n',
            tool_refs: [{ tool_id: 'crm_search', description: 'search', parameters_schema: { type: 'object' } }],
            depends_on: ['crm-entities'],
            references: [],
            assets: [],
        });
        expect(payload.tool_refs[0]).not.toBe(SOURCE.tool_refs[0]);
    });

    it('buildAgentSkillDuplicatePayload бросает на тот же id', () => {
        expect(() => buildAgentSkillDuplicatePayload(SOURCE, { agent_skill_id: 'networkle' })).toThrow(
            /must differ/,
        );
    });

    it('replaceAttachedAgentSkillId меняет id и дедупит', () => {
        expect(replaceAttachedAgentSkillId(['networkle', 'flows-platform'], 'networkle', 'networkle-copy')).toEqual([
            'networkle-copy',
            'flows-platform',
        ]);
        expect(
            replaceAttachedAgentSkillId(
                ['networkle', 'networkle-copy', 'flows-platform'],
                'networkle',
                'networkle-copy',
            ),
        ).toEqual(['networkle-copy', 'flows-platform']);
    });
});
