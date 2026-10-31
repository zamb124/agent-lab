/**
 * platform-file-table — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-file-table.js';

describe('platform-file-table', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-file-table')).to.exist;
    });
});
