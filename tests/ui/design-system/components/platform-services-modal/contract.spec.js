/**
 * platform-services-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-services-modal.js';

describe('platform-services-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-services-modal')).to.exist;
    });
});
