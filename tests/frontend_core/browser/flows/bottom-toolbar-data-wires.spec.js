import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapFlowsEditor } from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/editor/flows-bottom-toolbar.js';

describe('flows-bottom-toolbar data wires toggle', () => {
    beforeEach(() => resetPlatformState());
    afterEach(() => fixtureCleanup());

    it('toggles showDataWires in editor slice', async () => {
        const { bus, getState } = bootstrapFlowsEditor();
        const el = await fixture(html`<flows-bottom-toolbar></flows-bottom-toolbar>`);
        await elementUpdated(el);

        const buttons = el.shadowRoot.querySelectorAll('platform-button');
        const wiresBtn = [...buttons].find((btn) => {
            const icon = btn.querySelector('platform-icon');
            return icon && icon.getAttribute('name') === 'link';
        });
        expect(wiresBtn).to.not.equal(undefined);
        expect(getState().flowsEditor.showDataWires).to.equal(false);

        wiresBtn.click();
        await elementUpdated(el);
        expect(getState().flowsEditor.showDataWires).to.equal(true);
    });
});
