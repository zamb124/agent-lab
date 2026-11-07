import { fixture, fixtureCleanup, html, expect, elementUpdated, oneEvent } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import { collectFactories, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { bootstrapFlowsEditor, FLOW_CANVAS_FACTORIES } from '../../helpers/flows-dataflow-fixtures.js';
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import '@platform/lib/components/platform-json-tree.js';
import { q, qs, shadow, type TestEl } from '../helpers/dom.js';

/** 1×1 PNG */
const TINY_PNG_B64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

function seedPlatformTranslations() {
    const bus = getPlatformBus();
    const previous = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...previous, platform: platformEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'platform' },
        { source: 'system' },
    );
}

describe('platform-json-tree', () => {
    beforeEach(() => {
        resetPlatformState();
        for (const factory of FLOW_CANVAS_FACTORIES) registerFactory(factory);
        const collected = collectFactories(FLOW_CANVAS_FACTORIES);
        bootstrapFlowsEditor({ slices: collected.slices });
        seedPlatformTranslations();
    });
    afterEach(() => fixtureCleanup());

    it('shows leaf values, expands on click and emits select path', async () => {
        const tree = await fixture<TestEl>(html`
            <platform-json-tree
                .value=${{ nested: { b: 2 }, leaf: 'x' }}
                .rootPath=${'result'}
            ></platform-json-tree>
        `);
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="result.nested"]')).to.not.equal(null);
        const leaf = qs(shadow(tree), '.row[data-path="result.leaf"]');
        expect(leaf.textContent).to.include('x');
        expect(q(shadow(tree), '.row[data-path="result.nested.b"]')).to.equal(null);

        const pending = oneEvent(tree, 'select');
        qs(shadow(tree), '.row[data-path="result.nested"]').click();
        const selected = await pending;
        expect(selected.detail.path).to.equal('result.nested');
        await elementUpdated(tree);
        expect(qs(shadow(tree), '.row[data-path="result.nested.b"]').textContent).to.include('2');

        qs(shadow(tree), '.row[data-path="result.nested"]').click();
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="result.nested.b"]')).to.equal(null);
    });

    it('renders array indexes as [n] paths', async () => {
        const tree = await fixture<TestEl>(html`
            <platform-json-tree .value=${[{ title: 'a' }, { title: 'b' }]} .rootPath=${'hits'}></platform-json-tree>
        `);
        await elementUpdated(tree);
        expect(q(shadow(tree), '.row[data-path="hits[0]"]')).to.not.equal(null);
        expect(q(shadow(tree), '.row[data-path="hits[1]"]')).to.not.equal(null);
        qs(shadow(tree), '.row[data-path="hits[0]"]').click();
        await elementUpdated(tree);
        expect(qs(shadow(tree), '.row[data-path="hits[0].title"]').textContent).to.include('a');
    });

    it('toggles base64 image preview on image payload objects', async () => {
        const tree = await fixture<TestEl>(html`
            <platform-json-tree
                .value=${{
                    page: {
                        content_type: 'image/png',
                        bytes_b64: TINY_PNG_B64,
                        width: 1,
                    },
                }}
                .rootPath=${'result'}
            ></platform-json-tree>
        `);
        await elementUpdated(tree);
        qs(shadow(tree), '.row[data-path="result.page"]').click();
        await elementUpdated(tree);
        expect(q(shadow(tree), '.image-preview')).to.equal(null);
        const toggle = qs(shadow(tree), '.row[data-path="result.page"] .image-toggle');
        toggle.click();
        await elementUpdated(tree);
        const preview = qs(shadow(tree), '.image-preview img');
        expect(preview.getAttribute('src')).to.include('data:image/png;base64,');
    });
});
