import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { bootstrapFlowsEditor } from '../../helpers/flows-dataflow-fixtures.js';
import '../../../../apps/flows/ui/components/editor/flows-bottom-toolbar.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';

describe('flows-bottom-toolbar data wires toggle', () => {
    beforeEach(() => resetPlatformState());
    afterEach(() => fixtureCleanup());

    it('toggles showDataWires in editor slice', async () => {
        const { bus, getState } = bootstrapFlowsEditor();
        const el = await fixture<TestEl>(html`<flows-bottom-toolbar></flows-bottom-toolbar>`);
        await elementUpdated(el);

        const buttons = qsa(shadow(el), 'platform-button');
        const wiresBtn = [...buttons].find((btn) => {
            const icon = qs(btn!, 'platform-icon');
            return icon && icon.getAttribute('name') === 'link';
        });
        expect(wiresBtn).to.not.equal(undefined);
        expect(getState().flowsEditor.showDataWires).to.equal(false);

        (wiresBtn as TestEl).click();
        await elementUpdated(el);
        expect(getState().flowsEditor.showDataWires).to.equal(true);
    });
});
