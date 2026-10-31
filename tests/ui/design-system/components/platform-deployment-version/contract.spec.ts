/**
 * platform-deployment-version — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-deployment-version.js';

describe('platform-deployment-version', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-deployment-version')).to.exist;
    });
});
