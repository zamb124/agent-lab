/**
 * platform-service-sidebar — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';

describe('platform-service-sidebar', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-service-sidebar')).to.exist;
    });
});
