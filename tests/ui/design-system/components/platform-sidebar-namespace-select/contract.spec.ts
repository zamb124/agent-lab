/**
 * platform-sidebar-namespace-select — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';

describe('platform-sidebar-namespace-select', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-sidebar-namespace-select')).to.exist;
    });
});
