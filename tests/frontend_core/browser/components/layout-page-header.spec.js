/**
 * page-header: title/subtitle, кнопка «меню» диспатчит UI_SIDEBAR_OPEN_REQUESTED.
 */

import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/layout/page-header.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

describe('page-header', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('рендерит title и subtitle', async () => {
        const el = await fixture(html`<page-header title="My title" subtitle="sub"></page-header>`);
        expect(el.shadowRoot.querySelector('.title').textContent).to.equal('My title');
        expect(el.shadowRoot.querySelector('.subtitle').textContent).to.equal('sub');
    });

    it('менюшная кнопка диспатчит UI_SIDEBAR_OPEN_REQUESTED', async () => {
        const el = await fixture(html`<page-header title="x"></page-header>`);
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        el._openSidebar();
        const ev = events.find((e) => e.type === CoreEvents.UI_SIDEBAR_OPEN_REQUESTED);
        expect(ev).to.exist;
    });
});
