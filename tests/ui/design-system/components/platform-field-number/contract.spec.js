/**
 * platform-field-number — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-number.js';

describe('platform-field-number', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-number')).to.exist;
    });
});
