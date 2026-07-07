/**
 * platform-island — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-island.js';

describe('platform-island', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-island')).to.exist;
    });
});
