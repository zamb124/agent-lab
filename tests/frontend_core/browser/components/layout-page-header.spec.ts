/**
 * page-header: title/subtitle в in-flow шапке страницы.
 * Mobile shell 2026: отдельной «менюшной» кнопки здесь нет (см. PageHeader).
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/layout/page-header.js';
import { qs, shadow, type TestEl } from '../helpers/dom.js';

describe('page-header', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит title и subtitle', async () => {
        const el = await fixture<TestEl>(html`<page-header title="My title" subtitle="sub"></page-header>`);
        expect(qs(shadow(el), '.title').textContent).to.equal('My title');
        expect(qs(shadow(el), '.subtitle').textContent).to.equal('sub');
    });
});
