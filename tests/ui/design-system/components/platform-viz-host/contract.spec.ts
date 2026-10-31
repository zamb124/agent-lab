/**
 * platform-viz-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-viz-host.js';

describe('platform-viz-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-viz-host')).to.exist;
    });
});
