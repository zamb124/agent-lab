/**
 * platform-mini-bar-chart — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-mini-bar-chart.js';

describe('platform-mini-bar-chart', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-mini-bar-chart')).to.exist;
    });
});
