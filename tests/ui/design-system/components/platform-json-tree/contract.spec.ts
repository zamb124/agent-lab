/**
 * platform-json-tree — L1 contract (T1).
 */
import { fixture, html, expect, elementUpdated } from '../../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-json-tree.js';
import { q, qs, shadow, type TestEl } from '../../../../frontend_core/browser/helpers/dom.js';

describe('platform-json-tree', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders leaf values and expands children', async () => {
        const el = await fixture<TestEl>(html`
            <platform-json-tree
                .value=${{ nested: { b: 2 }, leaf: 'hello' }}
                .rootPath=${'result'}
            ></platform-json-tree>
        `);
        await elementUpdated(el);
        const leaf = qs(shadow(el), '.row[data-path="result.leaf"]');
        expect(leaf.textContent).to.include('hello');
        expect(q(shadow(el), '.row[data-path="result.nested.b"]')).to.equal(null);
        qs(shadow(el), '.row[data-path="result.nested"]').click();
        await elementUpdated(el);
        expect(qs(shadow(el), '.row[data-path="result.nested.b"]').textContent).to.include('2');
    });
});
