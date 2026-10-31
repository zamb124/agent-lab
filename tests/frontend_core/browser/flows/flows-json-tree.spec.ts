import { fixture, fixtureCleanup, html, expect, elementUpdated, oneEvent } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { bootstrapFlowsEditor, FLOW_CANVAS_FACTORIES } from '../../helpers/flows-dataflow-fixtures.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/flows-json-tree.js';
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

describe('flows-json-tree', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
        seedFlowsTranslations();
    });
    afterEach(() => fixtureCleanup());

    it('shows first level, expands on click and emits select path', async () => {
        const tree = await fixture<TestEl>(html`
            <flows-json-tree
                .value=${{ nested: { b: 2 }, leaf: 'x' }}
                .rootPath=${'result'}
            ></flows-json-tree>
        `);
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="result.nested"]')).to.not.equal(null);
        expect(q(shadow(tree), '.row[data-path="result.leaf"]')).to.not.equal(null);
        expect(q(shadow(tree), '.row[data-path="result.nested.b"]')).to.equal(null);

        const pending = oneEvent(tree, 'select');
        qs(shadow(tree), '.row[data-path="result.nested"]').click();
        const selected = await pending;
        expect(selected.detail.path).to.equal('result.nested');
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="result.nested.b"]')).to.not.equal(null);

        qs(shadow(tree), '.row[data-path="result.nested"]').click();
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="result.nested.b"]')).to.equal(null);
    });

    it('renders array indexes as [n] paths', async () => {
        const tree = await fixture<TestEl>(html`
            <flows-json-tree .value=${[{ title: 'a' }, { title: 'b' }]} .rootPath=${'hits'}></flows-json-tree>
        `);
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="hits[0]"]')).to.not.equal(null);
        expect(q(shadow(tree), '.row[data-path="hits[1]"]')).to.not.equal(null);
        qs(shadow(tree), '.row[data-path="hits[0]"]').click();
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="hits[0].title"]')).to.not.equal(null);
    });
});
