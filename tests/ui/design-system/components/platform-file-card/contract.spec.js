/**
 * platform-file-card — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-file-card.js';

describe('platform-file-card', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-file-card')).to.exist;
    });
});
