/**
 * platform-field-date — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-date.js';

describe('platform-field-date', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-date')).to.exist;
    });
});
