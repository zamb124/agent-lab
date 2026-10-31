/**
 * platform-file-card — itemKind=catalog: folder file-icon, sizeLabel, drop-target.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-file-card.js';

describe('platform-file-card catalog', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders folder file-icon and sizeLabel for itemKind=catalog', async () => {
        const el = await fixture(html`
            <platform-file-card
                item-kind="catalog"
                item-key="catalog:inbox"
                file-name="Inbox"
                size-label="3 files"
                type-label="Catalog"
            ></platform-file-card>
        `);
        const icon = el.shadowRoot.querySelector('platform-icon[file-icon]');
        expect(icon).to.exist;
        expect(icon.name).to.equal('folder');
        expect(icon.getAttribute('size')).to.equal('32');
        expect(el.shadowRoot.querySelector('.title').textContent).to.equal('Inbox');
        expect(el.shadowRoot.querySelector('.meta').textContent).to.equal('3 files · Catalog');
    });

    it('throws when catalog has no sizeLabel', async () => {
        const el = await fixture(html`
            <platform-file-card item-kind="file" file-name="a.txt"></platform-file-card>
        `);
        el.itemKind = 'catalog';
        el.sizeLabel = '';
        const failure = el.updateComplete.then(
            () => {
                throw new Error('platform-file-card: expected throw for missing sizeLabel');
            },
            (error) => error,
        );
        const error = await failure;
        expect(String(error.message)).to.match(/sizeLabel required for itemKind=catalog/);
    });

    it('reflects drop-target on catalog card', async () => {
        const el = await fixture(html`
            <platform-file-card
                item-kind="catalog"
                file-name="Inbox"
                size-label="0 files"
                type-label="Catalog"
            ></platform-file-card>
        `);
        el.dropTarget = true;
        await el.updateComplete;
        expect(el.hasAttribute('drop-target')).to.equal(true);
    });
});
