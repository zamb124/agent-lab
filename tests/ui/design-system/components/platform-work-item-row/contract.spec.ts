/**
 * platform-work-item-row — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-work-item-row.js';

describe('platform-work-item-row', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-work-item-row')).to.exist;
    });
});
