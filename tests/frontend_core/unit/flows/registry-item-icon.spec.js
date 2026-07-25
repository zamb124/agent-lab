import { describe, expect, it } from 'vitest';
import {
    registryItemIconName,
    registryItemLanguage,
    registryItemPrimaryTagIcon,
    registryItemVisualKind,
    tagGroupIconName,
} from '../../../../apps/flows/ui/_helpers/flows-registry-item-icon.js';

describe('flows registry item icon helpers', () => {
    it('classifies flow / mcp / code / tool kinds', () => {
        expect(registryItemVisualKind({ item_type: 'flow', tool_id: 'my_flow' })).toBe('flow');
        expect(registryItemVisualKind({
            tool_id: 'mcp:browser:search',
            mcp_server_id: 'browser',
            mcp_tool_name: 'search',
        })).toBe('mcp');
        expect(registryItemVisualKind({
            tool_id: 'echo',
            code: 'async def run(args, state):\n    return {}',
            language: 'python',
        })).toBe('code');
        expect(registryItemVisualKind({
            tool_id: 'ask_user',
            tags: ['misc'],
        })).toBe('tool');
    });

    it('resolves language only for code kind', () => {
        expect(registryItemLanguage({
            tool_id: 'ts_tool',
            language: 'typescript',
            code: 'async function run(args, state) { return {}; }',
        })).toBe('typescript');
        expect(registryItemLanguage({
            tool_id: 'ask_user',
            tags: ['misc'],
            language: 'python',
        })).toBe('');
        expect(registryItemLanguage({
            item_type: 'flow',
            tool_id: 'demo',
            language: 'python',
        })).toBe('');
    });

    it('maps tag group icons and primary tool tag', () => {
        expect(tagGroupIconName('web')).toBe('globe');
        expect(tagGroupIconName('files')).toBe('folder');
        expect(tagGroupIconName('knowledge')).toBe('book-open');
        expect(tagGroupIconName('unknown_tag_xyz')).toBe('layers');
        expect(registryItemPrimaryTagIcon({ tool_id: 'x', tags: ['web'] })).toBe('globe');
        expect(registryItemPrimaryTagIcon({ tool_id: 'x', tags: ['crm', 'worktracker'] })).toBe('users');
        expect(registryItemPrimaryTagIcon({ tool_id: 'x', tags: [] })).toBe('tool');
    });

    it('picks platform-icon names by kind', () => {
        expect(registryItemIconName({ item_type: 'flow', tool_id: 'f' })).toBe('workflow');
        expect(registryItemIconName({
            tool_id: 'mcp:s:t',
            mcp_server_id: 's',
        })).toBe('mcp');
        expect(registryItemIconName({
            tool_id: 'echo',
            code: 'async def run(args, state):\n    return {}',
        })).toBe('code');
        expect(registryItemIconName({
            tool_id: 'ask_user',
            tags: ['misc'],
        })).toBe('layers');
    });
});
