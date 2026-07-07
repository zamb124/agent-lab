/**
 * platform-searchable-combobox — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-searchable-combobox.js';

describe('platform-searchable-combobox', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-searchable-combobox')).to.exist;
    });
});
