/**
 * platform-field-array — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-array.js';

describe('platform-field-array', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-array')).to.exist;
    });
});
