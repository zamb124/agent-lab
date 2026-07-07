/**
 * platform-document-binary-viewer — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-document-binary-viewer.js';

describe('platform-document-binary-viewer', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-document-binary-viewer')).to.exist;
    });
});
