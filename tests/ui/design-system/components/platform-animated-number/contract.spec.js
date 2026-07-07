/**
 * platform-animated-number — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-animated-number.js';

describe('platform-animated-number', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-animated-number')).to.exist;
    });
});
