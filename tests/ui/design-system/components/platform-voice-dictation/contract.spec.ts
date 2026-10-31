/**
 * platform-voice-dictation — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-voice-dictation.js';

describe('platform-voice-dictation', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-voice-dictation')).to.exist;
    });
});
