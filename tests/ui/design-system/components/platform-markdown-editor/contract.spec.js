/**
 * platform-markdown-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-markdown-editor.js';

describe('platform-markdown-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-markdown-editor')).to.exist;
    });
});
