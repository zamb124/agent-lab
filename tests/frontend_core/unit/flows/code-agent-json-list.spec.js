import { describe, expect, it } from 'vitest';
import { parseJsonStringList } from '../../../../apps/flows/ui/_helpers/code-agent-json-list.js';

describe('parseJsonStringList', () => {
    it('treats empty and incomplete JSON as drafts', () => {
        expect(parseJsonStringList('')).toEqual({ status: 'empty' });
        expect(parseJsonStringList('   ')).toEqual({ status: 'empty' });
        expect(parseJsonStringList('[')).toEqual({ status: 'incomplete' });
        expect(parseJsonStringList("['")).toEqual({ status: 'incomplete' });
        expect(parseJsonStringList('["python3"')).toEqual({ status: 'incomplete' });
    });

    it('parses a complete argv array', () => {
        expect(parseJsonStringList('["python3","main.py"]')).toEqual({
            status: 'ok',
            items: ['python3', 'main.py'],
        });
    });

    it('rejects complete JSON that is not a string list', () => {
        expect(parseJsonStringList("['python3']")).toEqual({ status: 'invalid' });
        expect(parseJsonStringList('[1]')).toEqual({ status: 'invalid' });
        expect(parseJsonStringList('["python3",""]')).toEqual({ status: 'invalid' });
        expect(parseJsonStringList('{}')).toEqual({ status: 'incomplete' });
    });
});
