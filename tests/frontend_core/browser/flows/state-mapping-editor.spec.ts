import { fixture, fixtureCleanup, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-state-mapping-editor.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

describe('flows-state-mapping-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('input mapping uses segmented source switch and emits selected source type', async () => {
        const el = await fixture<TestEl>(html`
            <flows-state-mapping-editor
                kind="input"
                .mapping=${{ target: '@state:user.name' }}
            ></flows-state-mapping-editor>
        `);

        const control = qs(shadow(el), 'platform-segmented-control.source-type-segment');
        expect(control).to.not.equal(null);

        const segments = qsa(shadow(control)!, '.segment');
        expect(segments.length).to.equal(3);
        expect(segments[0]!.getAttribute('data-active')).to.equal('true');
        expect(segments[0]!.getAttribute('aria-pressed')).to.equal('true');

        const changed = oneEvent(el, 'change');
        segments[1]!.click();
        const event = await changed;
        expect((event as CustomEvent).detail.mapping).to.deep.equal({ target: '@var:user.name' });

        await elementUpdated(el);
        const updatedSegments = qsa(shadow(control)!, '.segment');
        expect(updatedSegments[1]!.getAttribute('data-active')).to.equal('true');
        expect(updatedSegments[1]!.getAttribute('aria-pressed')).to.equal('true');
    });
});
