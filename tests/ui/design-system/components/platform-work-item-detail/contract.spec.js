/**
 * platform-work-item-detail — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-work-item-detail.js';

describe('platform-work-item-detail', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-work-item-detail')).to.exist;
    });
});
