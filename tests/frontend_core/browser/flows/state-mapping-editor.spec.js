import { fixture, fixtureCleanup, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-state-mapping-editor.js';

describe('flows-state-mapping-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('input mapping uses icon source switch and emits selected source type', async () => {
        const el = await fixture(html`
            <flows-state-mapping-editor
                kind="input"
                .mapping=${{ target: '@state:user.name' }}
            ></flows-state-mapping-editor>
        `);

        const buttons = el.shadowRoot.querySelectorAll('.source-toggle-btn');
        expect(buttons.length).to.equal(3);
        expect(el.shadowRoot.querySelector('.source-toggle-btn[data-source="state"]').getAttribute('aria-pressed')).to.equal('true');

        const varButton = el.shadowRoot.querySelector('.source-toggle-btn[data-source="var"]');
        const changed = oneEvent(el, 'change');
        varButton.click();
        const event = await changed;
        expect(event.detail.mapping).to.deep.equal({ target: '@var:user.name' });

        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.source-toggle-btn[data-source="var"]').getAttribute('aria-pressed')).to.equal('true');
    });
});
