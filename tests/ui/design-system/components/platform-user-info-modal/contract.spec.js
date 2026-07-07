/**
 * platform-user-info-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-user-info-modal.js';

describe('platform-user-info-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-user-info-modal')).to.exist;
    });
});
