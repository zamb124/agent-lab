/**
 * platform-service-switcher-sheet — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/sheets/platform-service-switcher-sheet.js';

describe('platform-service-switcher-sheet', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-service-switcher-sheet')).to.exist;
    });
});
