/**
 * platform-json-editor — L1 contract (T2).
 */
import { fixture, html, expect } from '../../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-json-editor.js';

describe('platform-json-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders readonly value', async () => {
        const el = await fixture(html`
            <platform-json-editor readonly value='{"ok":true}'></platform-json-editor>
        `);
        expect(el.shadowRoot).to.exist;
        expect(el.value).to.equal('{"ok":true}');
    });
});
