/**
 * platform-top-bar — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-top-bar.js';

describe('platform-top-bar', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-top-bar')).to.exist;
    });
});
