/**
 * platform-breadcrumbs — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-breadcrumbs.js';

describe('platform-breadcrumbs', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-breadcrumbs')).to.exist;
    });
});
