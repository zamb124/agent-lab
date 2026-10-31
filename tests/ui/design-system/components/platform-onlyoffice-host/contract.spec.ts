/**
 * platform-onlyoffice-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-onlyoffice-host.js';

describe('platform-onlyoffice-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-onlyoffice-host')).to.exist;
    });
});
