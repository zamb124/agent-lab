/**
 * platform-variable-resolve-preview — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-variable-resolve-preview.js';

describe('platform-variable-resolve-preview', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-resolve-preview')).to.exist;
    });
});
