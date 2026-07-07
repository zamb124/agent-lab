/**
 * platform-switch — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-switch.js';

describe('platform-switch', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-switch')).to.exist;
    });
});
