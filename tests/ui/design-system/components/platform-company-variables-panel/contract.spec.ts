/**
 * platform-company-variables-panel — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-company-variables-panel.js';

describe('platform-company-variables-panel', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-company-variables-panel')).to.exist;
    });
});
