/**
 * platform-notification-manager — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-notification-manager.js';

describe('platform-notification-manager', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-notification-manager')).to.exist;
    });
});
