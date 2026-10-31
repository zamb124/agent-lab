import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { bootstrapFlowsEditor, FLOW_CANVAS_FACTORIES } from '../../helpers/flows-dataflow-fixtures.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/flows-node-run-value-view.js';

function seedFlowsTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...previous, flows: flowsEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'flows' },
        { source: 'system' },
    );
}

describe('flows-node-run-value-view', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
        seedFlowsTranslations();
    });
    afterEach(() => fixtureCleanup());

    it('renders empty, scalar, string, markdown, status and object viewers', async () => {
        const empty = await fixture(html`<flows-node-run-value-view .value=${null}></flows-node-run-value-view>`);
        expect(empty.shadowRoot.querySelector('.empty').textContent).to.equal('Empty');

        const flag = await fixture(html`<flows-node-run-value-view .value=${true}></flows-node-run-value-view>`);
        expect(flag.shadowRoot.querySelector('.scalar').textContent).to.equal('true');

        const number = await fixture(html`<flows-node-run-value-view .value=${12}></flows-node-run-value-view>`);
        expect(number.shadowRoot.querySelector('.scalar').textContent).to.equal('12');

        const text = await fixture(html`<flows-node-run-value-view .value=${'plain text'}></flows-node-run-value-view>`);
        expect(text.shadowRoot.querySelector('platform-code-editor')).to.not.equal(null);

        const markdown = await fixture(html`
            <flows-node-run-value-view .value=${'# Title\n\nSee [docs](https://example.com)'}></flows-node-run-value-view>
        `);
        expect(markdown.shadowRoot.querySelector('platform-markdown-editor')).to.not.equal(null);

        const status = await fixture(html`
            <flows-node-run-value-view .value=${{ index: { ok: true, latency_ms: 12 } }}></flows-node-run-value-view>
        `);
        const card = status.shadowRoot.querySelector('.status-card[data-ok="true"]');
        expect(card).to.not.equal(null);
        expect(card.textContent).to.include('index');
        expect(card.textContent).to.include('ok');
        expect(card.textContent).to.include('12');

        const objectView = await fixture(html`
            <flows-node-run-value-view .value=${{ title: 'x' }} .rootPath=${'result'}></flows-node-run-value-view>
        `);
        expect(objectView.shadowRoot.querySelector('flows-json-tree')).to.not.equal(null);
        const jsonSegment = objectView.shadowRoot
            .querySelector('platform-segmented-control')
            .shadowRoot.querySelector('button.segment[aria-label="JSON"]');
        jsonSegment.click();
        await elementUpdated(objectView);
        expect(objectView.shadowRoot.querySelector('platform-json-editor')).to.not.equal(null);
    });
});
