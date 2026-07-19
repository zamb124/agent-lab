/**
 * platform-mail-calendar-rail — L1 contract: module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-mail-calendar-rail.js';

describe('platform-mail-calendar-rail', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-mail-calendar-rail')).to.exist;
    });
});
