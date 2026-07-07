/**
 * platform-variable-value-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-variable-value-editor.js';

describe('platform-variable-value-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-value-editor')).to.exist;
    });
});
