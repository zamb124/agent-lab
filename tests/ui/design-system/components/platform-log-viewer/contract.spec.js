/**
 * platform-log-viewer — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-log-viewer.js';

describe('platform-log-viewer', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-log-viewer')).to.exist;
    });
});
