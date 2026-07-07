/**
 * platform-variable-secret-policy — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-variable-secret-policy.js';

describe('platform-variable-secret-policy', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-secret-policy')).to.exist;
    });
});
