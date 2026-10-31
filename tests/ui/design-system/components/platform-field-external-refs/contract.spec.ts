/**
 * platform-field-external-refs — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/fields/platform-field-external-refs.js';

describe('platform-field-external-refs', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-field-external-refs')).to.exist;
    });
});
