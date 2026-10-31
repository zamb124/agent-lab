/**
 * platform-mail-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-mail-modal.js';

describe('platform-mail-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-mail-modal')).to.exist;
    });
});
