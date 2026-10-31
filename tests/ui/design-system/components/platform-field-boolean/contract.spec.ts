/**
 * platform-field-boolean — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-boolean.js';

describe('platform-field-boolean', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-boolean')).to.exist;
    });
});
