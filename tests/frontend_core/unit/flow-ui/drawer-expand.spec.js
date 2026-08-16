import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('flow-ui-drawer expand', () => {
    it('drawer reflects expanded and uses fullscreen CSS', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/drawer.js'),
            'utf8',
        );
        expect(source).toContain('expanded: { type: Boolean, reflect: true }');
        expect(source).toContain(':host([expanded][open])');
        expect(source).toContain('flow-ui-drawer-expand-toggle');
        expect(source).toContain('flow-ui-drawer-close');
        expect(source).toContain('drawer-expanded');
        expect(source).toMatch(/100vw|100dvh|inset:\s*0/);
    });

    it('platform-flow-ui exposes Expand for display=drawer and keeps drawer chrome minimal', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/components/platform-flow-ui.js'),
            'utf8',
        );
        expect(source).toContain('_expandControl');
        expect(source).toContain('_closeControl');
        expect(source).toContain("this.display === 'drawer'");
        expect(source).toContain('flow-ui-drawer-expand-toggle');
        expect(source).toContain('flow-ui-drawer-close');
        expect(source).toContain('${filesPanel}${readonlyPill}${runControl}${expandControl}${embedMenu}${shareMenu}${closeControl}');
        expect(source).toContain("if (this.display === 'drawer') {\n            return 'minimal';");
    });
});
