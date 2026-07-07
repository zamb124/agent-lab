/**
 * platform-file-row — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-file-row.js';

describe('platform-file-row', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-file-row')).to.exist;
    });
});
