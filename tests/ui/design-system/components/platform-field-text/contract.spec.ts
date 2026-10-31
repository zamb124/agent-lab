/**
 * platform-field-text — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-text.js';

describe('platform-field-text', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-text')).to.exist;
    });
});
