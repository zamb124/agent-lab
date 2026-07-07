/**
 * platform-user — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-user.js';

describe('platform-user', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-user')).to.exist;
    });
});
