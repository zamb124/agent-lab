/**
 * platform-help-hint — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-help-hint.js';

describe('platform-help-hint', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-help-hint')).to.exist;
    });
});
