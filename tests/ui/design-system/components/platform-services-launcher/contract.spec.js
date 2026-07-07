/**
 * platform-services-launcher — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-services-launcher.js';

describe('platform-services-launcher', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-services-launcher')).to.exist;
    });
});
