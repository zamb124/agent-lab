/**
 * platform-audio-message-player — L1 contract (T0 backlog): module registration smoke.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-audio-message-player.js';

describe('platform-audio-message-player', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-audio-message-player')).to.exist;
    });
});
