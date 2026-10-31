/**
 * platform-code-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-code-editor.js';

describe('platform-code-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-code-editor')).to.exist;
    });
});
