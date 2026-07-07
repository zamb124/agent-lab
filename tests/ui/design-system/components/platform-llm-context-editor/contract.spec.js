/**
 * platform-llm-context-editor — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/llm/llm-context-editor.js';

describe('platform-llm-context-editor', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-llm-context-editor')).to.exist;
    });
});
