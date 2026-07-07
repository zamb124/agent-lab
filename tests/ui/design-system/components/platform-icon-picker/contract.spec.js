/**
 * platform-icon-picker — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-icon-picker.js';

describe('platform-icon-picker', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-icon-picker')).to.exist;
    });
});
