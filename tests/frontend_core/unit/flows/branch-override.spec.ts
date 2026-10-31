import { describe, it, expect } from 'vitest';
import { buildBranchNodeOverride } from '../../../../apps/flows/ui/_helpers/flows-resolvers.js';

describe('buildBranchNodeOverride', () => {
    it('возвращает только отличия от base (llm.model)', () => {
        const base = {
            type: 'llm_node',
            name: 'n1',
            config: { llm: { model: 'old', temperature: 0.2 } },
        };
        const eff = {
            type: 'llm_node',
            name: 'n1',
            config: { llm: { model: 'new', temperature: 0.2 } },
        };
        const o = buildBranchNodeOverride(base, eff);
        expect(o).toEqual({ config: { llm: { model: 'new' } } });
    });

    it('без base возвращает копию effective', () => {
        const eff = { type: 'x', config: { a: 1 } };
        expect(buildBranchNodeOverride(null, eff)).toEqual(eff);
    });
});
