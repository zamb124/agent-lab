/**
 * platform-field-object — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-object.js';

describe('platform-field-object', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-object')).to.exist;
    });
});
