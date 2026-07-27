/**
 * platform-spinner — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-spinner.js';

describe('platform-spinner', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-spinner')).to.exist;
    });
});
