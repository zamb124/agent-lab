/**
 * platform-calendar-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-calendar-modal.js';

describe('platform-calendar-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-calendar-modal')).to.exist;
    });
});
