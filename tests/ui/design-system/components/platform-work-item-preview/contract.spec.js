/**
 * platform-work-item-preview — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-work-item-preview.js';

describe('platform-work-item-preview', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-work-item-preview')).to.exist;
    });
});
