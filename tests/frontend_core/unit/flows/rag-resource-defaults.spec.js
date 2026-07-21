/**
 * @vitest-environment node
 */

import { describe, expect, it } from 'vitest';
import {
    defaultResourceConfigForType,
    defaultResourceDisplayName,
} from '../../../../apps/flows/ui/_helpers/flows-resource-defaults.js';
import { mergeBranchResourceRef } from '../../../../apps/flows/ui/_helpers/flows-branch-resource.js';

describe('flows resource defaults', () => {
    it('builds valid rag default config from resource key', () => {
        const cfg = defaultResourceConfigForType('rag', 'rAb12');
        expect(cfg).toEqual({
            namespace: 'kb-rab12',
            provider: 'pgvector',
            default_top_k: 5,
        });
        expect(defaultResourceDisplayName('rag')).toBe('RAG');
    });

    it('returns empty config for unknown types', () => {
        expect(defaultResourceConfigForType('llm', 'r1')).toEqual({});
    });
});

describe('mergeBranchResourceRef permission', () => {
    it('merges permission array onto branch resource ref', () => {
        const merged = mergeBranchResourceRef(
            { type: 'rag', name: 'RAG', config: { namespace: 'kb-1' } },
            { permission: ['managers', 'admin'] },
        );
        expect(merged.permission).toEqual(['managers', 'admin']);
        expect(merged.config).toEqual({ namespace: 'kb-1' });
    });
});
