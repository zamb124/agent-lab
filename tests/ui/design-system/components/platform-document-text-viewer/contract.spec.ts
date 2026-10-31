/**
 * platform-document-text-viewer — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-document-text-viewer.js';

describe('platform-document-text-viewer', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-document-text-viewer')).to.exist;
    });
});
