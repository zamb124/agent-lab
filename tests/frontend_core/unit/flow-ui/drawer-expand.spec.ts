/// <reference types="node" />
/**
 * Drawer-оболочка Flow UI: expand/close — события хоста ``<platform-flow-ui>``, которые
 * ловит ``<flow-ui-drawer>``; fullscreen и мобильная раскладка — только CSS drawer'а.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

function read(relativePath: string) {
    return readFileSync(join(root, relativePath), 'utf8');
}

describe('flow-ui-drawer expand', () => {
    it('drawer reflects expanded and listens to host expand/close events', () => {
        const drawer = read('core/frontend/static/lib/flow-ui/shell/drawer.ts');
        expect(drawer).toContain('expanded: { type: Boolean, reflect: true }');
        expect(drawer).toContain("this.addEventListener('flow-ui-drawer-expand-toggle', this._onExpandToggle)");
        expect(drawer).toContain('flow-ui-drawer-close');
        expect(drawer).toContain('data-drawer-gestures');
        expect(drawer).toContain('flow-ui-identity-changed');
        expect(drawer).not.toContain("addEventListener('mousemove'");
    });

    it('drawer styles cover fullscreen expanded state and narrow viewports', () => {
        const styles = read('core/frontend/static/lib/flow-ui/shell/drawer.styles.ts');
        expect(styles).toContain(':host([expanded][open])');
        expect(styles).toContain('resize-handle');
        expect(styles).toContain('@media (max-width: 520px)');
        expect(styles).toMatch(/100vw|100dvh|inset:\s*0/);
    });

    it('host exposes expand and close only for display=drawer and keeps drawer chrome minimal', () => {
        const host = read('core/frontend/static/lib/flow-ui/components/platform-flow-ui.ts');
        expect(host).toContain("drawerExpanded: { type: Boolean, attribute: 'drawer-expanded', reflect: true }");
        expect(host).toContain("this._emit('flow-ui-drawer-expand-toggle', { expanded: !this.drawerExpanded })");
        expect(host).toContain("this._emit('flow-ui-drawer-close')");
        expect(host).toContain("if (this.display === 'drawer') return 'minimal';");
        expect(host).toContain('emitDrawerMoveStart(this, event)');
    });
});
