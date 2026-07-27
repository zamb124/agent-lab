/**
 * platform-echarts-host — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-echarts-host.js';

describe('platform-echarts-host', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-echarts-host')).to.exist;
    });
});
