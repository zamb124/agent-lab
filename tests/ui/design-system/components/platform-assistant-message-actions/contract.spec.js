/**
 * platform-assistant-message-actions — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-assistant-message-actions.js';

describe('platform-assistant-message-actions', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-assistant-message-actions')).to.exist;
    });
});
