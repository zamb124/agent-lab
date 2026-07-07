/**
 * platform-variables-panel — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-variables-panel.js';

describe('platform-variables-panel', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variables-panel')).to.exist;
    });
});
