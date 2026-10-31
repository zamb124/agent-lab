/**
 * platform-mermaid-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-mermaid-host.js';

describe('platform-mermaid-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-mermaid-host')).to.exist;
    });
});
