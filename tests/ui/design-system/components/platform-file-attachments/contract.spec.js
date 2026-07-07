/**
 * platform-file-attachments — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-file-attachments.js';

describe('platform-file-attachments', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-file-attachments')).to.exist;
    });
});
