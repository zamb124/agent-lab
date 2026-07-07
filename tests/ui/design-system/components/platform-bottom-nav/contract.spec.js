/**
 * platform-bottom-nav — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-bottom-nav.js';

describe('platform-bottom-nav', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-bottom-nav')).to.exist;
    });
});
