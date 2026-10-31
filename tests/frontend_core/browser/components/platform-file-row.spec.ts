/**
 * platform-file-row — itemKind=catalog: folder file-icon, sizeLabel, drop-target.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-file-row.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

describe('platform-file-row catalog', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders folder file-icon and sizeLabel for itemKind=catalog', async () => {
        const el = await fixture<TestEl>(html`
            <platform-file-row
                item-kind="catalog"
                item-key="catalog:inbox"
                file-name="Inbox"
                size-label="3 files"
                date-label="—"
                retention-label="—"
                type-label="Catalog"
            ></platform-file-row>
        `);
        const icon = qs(shadow(el), 'platform-icon[file-icon]');
        expect(icon).to.exist;
        expect(icon.name).to.equal('folder');
        expect(icon.getAttribute('size')).to.equal('20');
        expect(qs(shadow(el), '.cell-title-text').textContent).to.equal('Inbox');
        const cells = qsa(shadow(el), '.cell-meta');
        expect(cells[0]!.textContent).to.equal('3 files');
        expect(q(shadow(el), 'input[type="checkbox"]')).to.equal(null);
    });

    it('throws when catalog has no sizeLabel', async () => {
        const el = await fixture<TestEl>(html`
            <platform-file-row item-kind="file" file-name="a.txt"></platform-file-row>
        `);
        el.itemKind = 'catalog';
        el.sizeLabel = '';
        const failure = el.updateComplete.then(
            () => {
                throw new Error('platform-file-row: expected throw for missing sizeLabel');
            },
            (error: any) => error,
        );
        const error = await failure;
        expect(String(error.message)).to.match(/sizeLabel required for itemKind=catalog/);
    });

    it('reflects drop-target on catalog row', async () => {
        const el = await fixture<TestEl>(html`
            <platform-file-row
                item-kind="catalog"
                file-name="Inbox"
                size-label="0 files"
            ></platform-file-row>
        `);
        el.dropTarget = true;
        await el.updateComplete;
        expect(el.hasAttribute('drop-target')).to.equal(true);
        expect(qs(shadow(el), '.row')).to.exist;
    });
});
