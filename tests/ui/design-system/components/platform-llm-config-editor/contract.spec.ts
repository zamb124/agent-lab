/**
 * platform-llm-config-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/llm/llm-config-editor.js';

describe('platform-llm-config-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-llm-config-editor')).to.exist;
    });
});
