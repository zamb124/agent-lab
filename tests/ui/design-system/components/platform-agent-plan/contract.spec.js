/**
 * platform-agent-plan — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-agent-plan.js';

describe('platform-agent-plan', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-agent-plan')).to.exist;
    });
});
