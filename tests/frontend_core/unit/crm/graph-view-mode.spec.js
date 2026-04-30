import { describe, it, expect } from 'vitest';
import {
    parseGraphWorkspaceQuery,
    buildGraphWorkspaceSearch,
    graphCanvasViewFromParam,
    clampGraphDepth,
} from '../../../../apps/crm/ui/utils/graph-view-mode.js';

describe('graph-view-mode', () => {
    it('parseGraphWorkspaceQuery: defaults view to mindmap', () => {
        const r = parseGraphWorkspaceQuery('');
        expect(r.view).toBe('mindmap');
        expect(r.root).toBe(null);
        expect(r.depth).toBe(null);
        expect(r.query).toBe('');
    });

    it('buildGraphWorkspaceSearch round-trip', () => {
        const s = buildGraphWorkspaceSearch({
            view: '3d',
            root: 'e1',
            depth: 3,
            query: 'hello',
        });
        const r = parseGraphWorkspaceQuery(s);
        expect(r.view).toBe('3d');
        expect(r.root).toBe('e1');
        expect(r.depth).toBe(3);
        expect(r.query).toBe('hello');
    });

    it('graphCanvasViewFromParam throws on unknown', () => {
        expect(() => graphCanvasViewFromParam('2d')).toThrow(/unknown/);
    });

    it('clampGraphDepth clamps to 1..5', () => {
        expect(clampGraphDepth(0)).toBe(1);
        expect(clampGraphDepth(10)).toBe(5);
    });
});
