/**
 * page-header: title/subtitle в in-flow шапке страницы.
 * Mobile shell 2026: отдельной «менюшной» кнопки здесь нет (см. PageHeader).
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/layout/page-header.js';

describe('page-header', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит title и subtitle', async () => {
        const el = await fixture(html`<page-header title="My title" subtitle="sub"></page-header>`);
        expect(el.shadowRoot.querySelector('.title').textContent).to.equal('My title');
        expect(el.shadowRoot.querySelector('.subtitle').textContent).to.equal('sub');
    });
});
