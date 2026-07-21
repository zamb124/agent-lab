/**
 * platform-variable-input — L1 contract: registration + at-ref CM suite.
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import '@platform/lib/components/platform-variable-input.js';
import '../../../../frontend_core/browser/components/platform-variable-input.spec.js';

describe('platform-variable-input registration', () => {
    it('registers custom element', async () => {
        expect(customElements.get('platform-variable-input')).to.exist;
    });
});
