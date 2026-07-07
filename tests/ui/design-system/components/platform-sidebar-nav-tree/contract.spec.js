/**
 * platform-sidebar-nav-tree — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-sidebar-nav-tree.js';

describe('platform-sidebar-nav-tree', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-sidebar-nav-tree')).to.exist;
    });
});
