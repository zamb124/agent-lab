/**
 * platform-palette-color-picker — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-palette-color-picker.js';

describe('platform-palette-color-picker', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-palette-color-picker')).to.exist;
    });
});
