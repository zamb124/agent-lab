/**
 * platform-mail-html-body — L1 contract.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-mail-html-body.js';

describe('platform-mail-html-body', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-mail-html-body')).to.exist;
    });
});
