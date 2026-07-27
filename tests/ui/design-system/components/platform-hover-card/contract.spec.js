/**
 * platform-hover-card — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-hover-card.js';

describe('platform-hover-card', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-hover-card')).to.exist;
    });
});
