/**
 * platform-field-enum — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-enum.js';

describe('platform-field-enum', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-enum')).to.exist;
    });
});
