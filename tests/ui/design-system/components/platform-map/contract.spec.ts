/**
 * platform-map — L1 contract (T0 backlog): module registration smoke.
 * Боевое поведение — tests/frontend_core/browser/components/platform-map.spec.ts.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-map.js';

describe('platform-map', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-map')).to.exist;
    });
});
