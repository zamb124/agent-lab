import { describe, expect, it } from 'vitest';
import { inferToolRefLanguage } from '../../../../apps/flows/ui/_helpers/flows-tool-visual.js';

describe('flows tool visual helpers', () => {
    it('treats legacy inline code tools without language as python', () => {
        expect(inferToolRefLanguage({
            tool_id: 'search_knowledge_base',
            type: 'code',
            code: 'async def run(args, state):\n    return {}',
        })).toBe('python');
    });

    it('uses explicit language over legacy python default', () => {
        expect(inferToolRefLanguage({
            tool_id: 'ts_tool',
            language: 'typescript',
            code: 'async function run(args, state) { return {}; }',
        })).toBe('typescript');
    });
});
