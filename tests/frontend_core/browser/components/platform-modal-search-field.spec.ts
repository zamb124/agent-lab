/**
 * platform-modal-search-field — compact search pill for modals/toolbars.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-help-hint.js';

describe('platform-modal-search-field', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('suffix slot: slotted content reaches platform-field suffix', async () => {
        const el = await fixture(html`
            <platform-modal-search-field layout="fill" placeholder="Search">
                <span slot="suffix" class="suffix-marker">?</span>
            </platform-modal-search-field>
        `);
        await elementUpdated(el);

        const forwardSlot = el.shadowRoot.querySelector('slot[name="suffix"]');
        const [marker] = forwardSlot.assignedElements();
        expect(marker?.classList.contains('suffix-marker')).to.equal(true);
    });

    it('suffix platform-help-hint stays inside search field', async () => {
        const el = await fixture(html`
            <platform-modal-search-field layout="fill" placeholder="Search">
                <platform-help-hint slot="suffix" label="Help"></platform-help-hint>
            </platform-modal-search-field>
        `);
        await elementUpdated(el);

        const forwardSlot = el.shadowRoot.querySelector('slot[name="suffix"]');
        const [helpHint] = forwardSlot.assignedElements();
        expect(helpHint?.localName).to.equal('platform-help-hint');
    });
});
