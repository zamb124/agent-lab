/**
 * platform-data-table-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-data-table-host.js';

describe('platform-data-table-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-data-table-host')).to.exist;
    });
});
