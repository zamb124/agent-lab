/**
 * platform-rich-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-rich-editor.js';

describe('platform-rich-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-rich-editor')).to.exist;
    });
});
