/**
 * platform-variable-input — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-variable-input.js';

describe('platform-variable-input', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-input')).to.exist;
    });
});
