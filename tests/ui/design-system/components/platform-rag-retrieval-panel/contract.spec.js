/**
 * platform-rag-retrieval-panel — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/rag/platform-rag-retrieval-panel.js';

describe('platform-rag-retrieval-panel', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-rag-retrieval-panel')).to.exist;
    });
});
