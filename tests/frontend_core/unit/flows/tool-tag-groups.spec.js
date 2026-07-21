/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import { buildToolTagGroups, tagsFromRegistryItem } from '../../../../apps/flows/ui/_helpers/flows-tool-tag-groups.js';

describe('flows-tool-tag-groups', () => {
    it('tagsFromRegistryItem filters non-strings', () => {
        expect(tagsFromRegistryItem({ tags: ['crm', '', 1, 'ai'] })).toEqual(['crm', 'ai']);
        expect(tagsFromRegistryItem({})).toEqual([]);
    });

    it('buildToolTagGroups puts tool into every tag and allows multi-membership', () => {
        const groups = buildToolTagGroups([
            { tool_id: 'a', title: 'A', tags: ['crm', 'ai'], description: 'one' },
            { tool_id: 'b', title: 'B', tags: ['crm'], description: 'two' },
        ], {
            descriptionsByTag: {
                crm: { description_ru: 'CRM группа', description_en: 'CRM group' },
            },
            locale: 'ru',
        });
        expect(groups.map((g) => g.tag)).toEqual(['ai', 'crm']);
        const crm = groups.find((g) => g.tag === 'crm');
        expect(crm.description).toBe('CRM группа');
        expect(crm.tools.map((t) => t.tool_id)).toEqual(['a', 'b']);
        const ai = groups.find((g) => g.tag === 'ai');
        expect(ai.tools.map((t) => t.tool_id)).toEqual(['a']);
    });

    it('buildToolTagGroups filters by search', () => {
        const groups = buildToolTagGroups([
            { tool_id: 'calculator', title: 'Calc', tags: ['math'], description: 'expr' },
            { tool_id: 'crm_get', title: 'Get entity', tags: ['crm'], description: 'entity' },
        ], { search: 'calc' });
        expect(groups).toHaveLength(1);
        expect(groups[0].tag).toBe('math');
    });
});
