/**
 * platform-document-media-viewer — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-document-media-viewer.js';

describe('platform-document-media-viewer', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-document-media-viewer')).to.exist;
    });
});
