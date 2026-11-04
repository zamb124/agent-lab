/**
 * platform-zone-address-panel — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-zone-address-panel.js';

describe('platform-zone-address-panel', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-zone-address-panel')).to.exist;
    });
});
