/**
 * platform-icon — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-icon.js';

describe('platform-icon', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-icon')).to.exist;
    });
});
