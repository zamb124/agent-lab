/**
 * platform-field-string — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-string.js';

describe('platform-field-string', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-string')).to.exist;
    });
});
