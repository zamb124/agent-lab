/**
 * flows-execution-panel hosts unified platform-flow-ui in Run workspace.
 */
import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';

describe('flows-execution-panel Flow UI host', () => {
    beforeEach(async () => {
        await resetPlatformState();
        bootstrapTestBus({ factories: [editorResource, executionUiSlice] });
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('execution panel module exposes platform-flow-ui host contract', async () => {
        await import('../../../../apps/flows/ui/components/editor/flows-execution-panel.js');
        const defined = customElements.get('flows-execution-panel');
        expect(defined).to.not.equal(undefined);
        const el = await fixture(html`<flows-execution-panel></flows-execution-panel>`);
        await elementUpdated(el);
        expect(el.tagName.toLowerCase()).to.equal('flows-execution-panel');
    });
});
