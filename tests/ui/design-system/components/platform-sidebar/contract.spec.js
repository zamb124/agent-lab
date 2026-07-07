/**
 * platform-sidebar — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-sidebar.js';

describe('platform-sidebar', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-sidebar')).to.exist;
    });
});
