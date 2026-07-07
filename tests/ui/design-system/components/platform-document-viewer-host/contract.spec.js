/**
 * platform-document-viewer-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-document-viewer-host.js';

describe('platform-document-viewer-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-document-viewer-host')).to.exist;
    });
});
