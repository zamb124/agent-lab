import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { bootstrapFlowsEditor, FLOW_CANVAS_FACTORIES } from '../../helpers/flows-dataflow-fixtures.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/flows-node-run-value-view.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

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
        const empty = await fixture<TestEl>(html`<flows-node-run-value-view .value=${null}></flows-node-run-value-view>`);
        expect(qs(shadow(empty), '.empty').textContent).to.equal('Empty');

        const flag = await fixture<TestEl>(html`<flows-node-run-value-view .value=${true}></flows-node-run-value-view>`);
        expect(qs(shadow(flag), '.scalar').textContent).to.equal('true');

        const number = await fixture<TestEl>(html`<flows-node-run-value-view .value=${12}></flows-node-run-value-view>`);
        expect(qs(shadow(number), '.scalar').textContent).to.equal('12');

        const text = await fixture<TestEl>(html`<flows-node-run-value-view .value=${'plain text'}></flows-node-run-value-view>`);
        expect(q(shadow(text), 'platform-code-editor')).to.not.equal(null);

        const markdown = await fixture<TestEl>(html`
            <flows-node-run-value-view .value=${'# Title\n\nSee [docs](https://example.com)'}></flows-node-run-value-view>
        `);
        expect(q(shadow(markdown), 'platform-markdown-editor')).to.not.equal(null);

        const status = await fixture<TestEl>(html`
            <flows-node-run-value-view .value=${{ index: { ok: true, latency_ms: 12 } }}></flows-node-run-value-view>
        `);
        const card = q(shadow(status), '.status-card[data-ok="true"]');
        expect(card).to.not.equal(null);
        expect(card!.textContent).to.include('index');
        expect(card!.textContent).to.include('ok');
        expect(card!.textContent).to.include('12');

        const objectView = await fixture<TestEl>(html`
            <flows-node-run-value-view .value=${{ title: 'x' }} .rootPath=${'result'}></flows-node-run-value-view>
        `);
        expect(q(shadow(objectView), 'flows-json-tree')).to.not.equal(null);
        const jsonSegment = qs(shadow(qs(shadow(objectView), 'platform-segmented-control')), 'button.segment[aria-label="JSON"]');
        (jsonSegment as TestEl).click();
        await elementUpdated(objectView);
        expect(q(shadow(objectView), 'platform-json-editor')).to.not.equal(null);
    });
});
