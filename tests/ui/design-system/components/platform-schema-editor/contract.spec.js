/**
 * platform-schema-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/schema/platform-schema-editor.js';

describe('platform-schema-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-schema-editor')).to.exist;
    });
});
