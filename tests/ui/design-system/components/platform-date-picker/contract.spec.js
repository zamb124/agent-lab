/**
 * platform-date-picker — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-date-picker.js';

describe('platform-date-picker', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-date-picker')).to.exist;
    });
});
