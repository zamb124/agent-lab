/**
 * platform-work-item-board — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-work-item-board.js';

describe('platform-work-item-board', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-work-item-board')).to.exist;
    });
});
