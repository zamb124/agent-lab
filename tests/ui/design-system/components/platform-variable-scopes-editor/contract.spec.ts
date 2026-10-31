/**
 * platform-variable-scopes-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-variable-scopes-editor.js';

describe('platform-variable-scopes-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-scopes-editor')).to.exist;
    });
});
