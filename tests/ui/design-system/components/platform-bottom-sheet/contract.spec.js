/**
 * platform-bottom-sheet — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/layout/platform-bottom-sheet.js';

describe('platform-bottom-sheet', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-bottom-sheet')).to.exist;
    });
});
