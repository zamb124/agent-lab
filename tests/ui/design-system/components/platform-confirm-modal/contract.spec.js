/**
 * platform-confirm-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-confirm-modal.js';

describe('platform-confirm-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-confirm-modal')).to.exist;
    });
});
