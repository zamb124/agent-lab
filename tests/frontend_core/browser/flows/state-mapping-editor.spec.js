import { fixture, fixtureCleanup, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-state-mapping-editor.js';

describe('flows-state-mapping-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('input mapping uses segmented source switch and emits selected source type', async () => {
        const el = await fixture(html`
            <flows-state-mapping-editor
                kind="input"
                .mapping=${{ target: '@state:user.name' }}
            ></flows-state-mapping-editor>
        `);

        const control = el.shadowRoot.querySelector('platform-segmented-control.source-type-segment');
        expect(control).to.not.equal(null);

        const segments = control.shadowRoot.querySelectorAll('.segment');
        expect(segments.length).to.equal(3);
        expect(segments[0].getAttribute('data-active')).to.equal('true');
        expect(segments[0].getAttribute('aria-pressed')).to.equal('true');

        const changed = oneEvent(el, 'change');
        segments[1].click();
        const event = await changed;
        expect(event.detail.mapping).to.deep.equal({ target: '@var:user.name' });

        await elementUpdated(el);
        const updatedSegments = control.shadowRoot.querySelectorAll('.segment');
        expect(updatedSegments[1].getAttribute('data-active')).to.equal('true');
        expect(updatedSegments[1].getAttribute('aria-pressed')).to.equal('true');
    });
});
