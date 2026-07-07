/**
 * platform-company-variable-editor-modal — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/variables/platform-company-variable-editor-modal.js';

describe('platform-company-variable-editor-modal', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-company-variable-editor-modal')).to.exist;
    });
});
