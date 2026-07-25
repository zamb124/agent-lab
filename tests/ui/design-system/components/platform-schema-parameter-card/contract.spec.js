/**
 * platform-schema-parameter-card — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/schema/platform-schema-parameter-card.js';

describe('platform-schema-parameter-card', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-schema-parameter-card')).to.exist;
    });
});
