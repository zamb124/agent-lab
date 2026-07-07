/**
 * platform-document-image-viewer — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-document-image-viewer.js';

describe('platform-document-image-viewer', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-document-image-viewer')).to.exist;
    });
});
