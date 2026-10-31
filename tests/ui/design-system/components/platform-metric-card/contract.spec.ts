/**
 * platform-metric-card — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-metric-card.js';

describe('platform-metric-card', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-metric-card')).to.exist;
    });
});
