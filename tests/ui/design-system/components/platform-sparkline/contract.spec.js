/**
 * platform-sparkline — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-sparkline.js';

describe('platform-sparkline', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-sparkline')).to.exist;
    });
});
